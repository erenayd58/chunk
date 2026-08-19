from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from amsc.checkpoint_adapter import (
    CanonicalUnitWriter,
    CheckpointLayoutUnavailableError,
    ExtractedPage,
    ExtractionManifestWriter,
    ExtractionResult,
    LayoutBox,
    LayoutBackend,
    MarkdownAtomicUnitParser,
    PageSelectionParser,
    PyMuPDF4LLMExtractor,
    SectionHierarchyBuilder,
    VisualProvenanceWriter,
    load_layout_backend,
    prepare_checkpoint,
)
from amsc.io import load_jsonl_units
from amsc.models import UnitType


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, (1, 2, 3, 4, 5)),
        ("2", (2,)),
        ("2-4", (2, 3, 4)),
        ("4,1-2", (1, 2, 4)),
    ],
)
def test_page_selection_is_one_based_inclusive_and_sorted(
    value: str | None, expected: tuple[int, ...]
) -> None:
    assert PageSelectionParser.parse(value, page_count=5) == expected


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("", "cannot be empty"),
        ("0", "1-based"),
        ("4-2", "Descending"),
        ("2,2", "Duplicate"),
        ("5-6", "page count"),
        ("one", "Invalid page selection"),
    ],
)
def test_page_selection_rejects_invalid_ranges(value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        PageSelectionParser.parse(value, page_count=5)


def test_layout_loader_imports_layout_before_pymupdf4llm() -> None:
    calls: list[str] = []
    layout = ModuleType("pymupdf.layout")
    pymupdf = ModuleType("pymupdf")
    pymupdf._get_layout = object()  # type: ignore[attr-defined]
    pymupdf4llm = ModuleType("pymupdf4llm")
    pymupdf4llm.__version__ = "0.3.4"
    pymupdf4llm.document_layout = object()  # type: ignore[attr-defined]

    def to_markdown() -> None:
        return None

    to_markdown.__module__ = "pymupdf4llm"
    pymupdf4llm.to_markdown = to_markdown  # type: ignore[attr-defined]
    modules = {
        "pymupdf.layout": layout,
        "pymupdf4llm": pymupdf4llm,
        "pymupdf": pymupdf,
    }

    def fake_import(name: str) -> ModuleType:
        calls.append(name)
        return modules[name]

    backend = load_layout_backend(fake_import)
    assert calls == ["pymupdf.layout", "pymupdf4llm", "pymupdf"]
    assert backend.pymupdf4llm is pymupdf4llm


def test_layout_loader_rejects_legacy_backend_without_fallback() -> None:
    layout = ModuleType("pymupdf.layout")
    pymupdf = ModuleType("pymupdf")
    pymupdf._get_layout = None  # type: ignore[attr-defined]
    pymupdf4llm = ModuleType("pymupdf4llm")
    pymupdf4llm.__version__ = "0.3.4"
    pymupdf4llm.IdentifyHeaders = object()  # type: ignore[attr-defined]

    def legacy_to_markdown() -> None:
        return None

    legacy_to_markdown.__module__ = "pymupdf4llm.helpers.pymupdf_rag"
    pymupdf4llm.to_markdown = legacy_to_markdown  # type: ignore[attr-defined]
    modules = {
        "pymupdf.layout": layout,
        "pymupdf4llm": pymupdf4llm,
        "pymupdf": pymupdf,
    }

    with pytest.raises(
        CheckpointLayoutUnavailableError, match="Legacy extraction is not permitted"
    ):
        load_layout_backend(lambda name: modules[name])


def test_layout_loader_reports_missing_layout_dependency() -> None:
    def missing_layout(name: str) -> ModuleType:
        raise ModuleNotFoundError(name)

    with pytest.raises(
        CheckpointLayoutUnavailableError, match="checkpoint"
    ):
        load_layout_backend(missing_layout)


def test_extractor_uses_exact_layout_parameters_and_physical_pages(tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    source.write_bytes(b"fake-pdf")
    calls: list[tuple[object, dict[str, object]]] = []

    class FakeRect:
        width = 600
        height = 800

    class FakeSourcePage:
        rect = FakeRect()

    class FakeSourceDocument:
        page_count = 4

        def __enter__(self) -> "FakeSourceDocument":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def __getitem__(self, index: int) -> FakeSourcePage:
            return FakeSourcePage()

    class FakeExtractedPage:
        def set_cropbox(self, rect: object) -> None:
            raise AssertionError("Portrait pages must not be cropped")

    class FakeExtractionDocument:
        def __init__(self) -> None:
            self.pages: list[FakeExtractedPage] = []

        def insert_pdf(self, *args: object, **kwargs: object) -> None:
            self.pages.append(FakeExtractedPage())

        def __getitem__(self, index: int) -> FakeExtractedPage:
            return self.pages[index]

        def close(self) -> None:
            return None

    extraction_document = FakeExtractionDocument()

    def fake_open(path: str | None = None) -> object:
        return FakeSourceDocument() if path is not None else extraction_document

    fake_pymupdf = SimpleNamespace(open=fake_open, Rect=lambda *args: args)

    def fake_to_markdown(
        document: object, **kwargs: object
    ) -> list[dict[str, object]]:
        calls.append((document, kwargs))
        return [
            {"metadata": {"page_number": 1}, "page_boxes": [], "text": "Page two"},
            {"metadata": {"page_number": 2}, "page_boxes": [], "text": "Page three"},
        ]

    fake_pymupdf4llm = SimpleNamespace(
        __version__="0.3.4", to_markdown=fake_to_markdown
    )
    backend = LayoutBackend(
        pymupdf=fake_pymupdf,  # type: ignore[arg-type]
        pymupdf4llm=fake_pymupdf4llm,  # type: ignore[arg-type]
    )

    result = PyMuPDF4LLMExtractor(lambda: backend).extract(source, pages="2-3")

    assert result.selected_pages == (2, 3)
    assert [page.page for page in result.pages] == [2, 3]
    assert [page.logical_page_side for page in result.pages] == ["single", "single"]
    assert calls == [
        (
            extraction_document,
            {
                "page_chunks": True,
                "header": False,
                "footer": False,
                "pages": None,
                "force_ocr": False,
            },
        )
    ]


def test_markdown_atomization_and_section_hierarchy_are_deterministic() -> None:
    parser = MarkdownAtomicUnitParser()
    page_one = ExtractedPage(
        page=40,
        markdown=(
            "Preamble.\n\n"
            "## Risk Yönetimi\n\n"
            "Ana paragraf.\n\n"
            "### Kredi Riski\n\n"
            "- Birinci\n- İkinci\n\n"
            "| Alan | Değer |\n| --- | ---: |\n| A | 1 |\n"
        ),
    )
    page_two = ExtractedPage(page=41, markdown="Devam paragrafı.\n")
    blocks = parser.parse_page(page_one) + parser.parse_page(page_two)
    units = SectionHierarchyBuilder().build(blocks, document_id="kkb-2024")

    assert [unit.type for unit in units] == [
        UnitType.PARAGRAPH,
        UnitType.HEADING,
        UnitType.PARAGRAPH,
        UnitType.HEADING,
        UnitType.LIST,
        UnitType.TABLE,
        UnitType.PARAGRAPH,
    ]
    assert [unit.unit_id for unit in units] == [
        "p-00001",
        "h-00002",
        "p-00003",
        "h-00004",
        "l-00005",
        "t-00006",
        "p-00007",
    ]
    assert units[0].section_path == []
    assert units[1].section_path == ["Risk Yönetimi"]
    assert units[4].section_path == ["Risk Yönetimi", "Kredi Riski"]
    assert units[-1].section_path == ["Risk Yönetimi", "Kredi Riski"]
    assert [unit.source.block for unit in units] == [1, 2, 3, 4, 5, 6, 1]
    assert [unit.source.page for unit in units] == [40, 40, 40, 40, 40, 40, 41]


def test_heading_markers_inside_fenced_code_are_not_structural() -> None:
    blocks = MarkdownAtomicUnitParser().parse_page(
        ExtractedPage(page=1, markdown="```text\n# not heading\n```\n")
    )
    assert len(blocks) == 1
    assert blocks[0].unit_type == UnitType.PARAGRAPH


def test_picture_box_becomes_one_visual_atomic_unit_with_raw_numeric_text() -> None:
    heading = "## FTE Planı\n\n"
    picture = (
        "**==> picture [400 x 200] intentionally omitted <==**\n\n"
        "**----- Start of picture text -----**<br>\n"
        "Planlanan FTE<br>12,5<br>Gerçekleşen FTE<br>11,75<br>\n"
        "**----- End of picture text -----**<br>\n"
    )
    paragraph = "Takip eden paragraf.\n"
    markdown = heading + picture + paragraph
    page = ExtractedPage(
        page=43,
        markdown=markdown,
        logical_page_side="right",
        physical_page_width=1200,
        physical_page_height=842,
        layout_boxes=(
            LayoutBox(0, "section-header", (650, 70, 900, 100), 0, len(heading)),
            LayoutBox(
                1,
                "picture",
                (650, 120, 1100, 500),
                len(heading),
                len(heading) + len(picture),
            ),
            LayoutBox(
                2,
                "text",
                (650, 520, 900, 600),
                len(heading) + len(picture),
                len(markdown),
            ),
        ),
    )

    blocks = MarkdownAtomicUnitParser().parse_page(page)

    assert len(blocks) == 3
    visual = blocks[1]
    assert visual.unit_id_prefix == "v"
    assert visual.unit_type == UnitType.PARAGRAPH
    assert visual.content_origin == "visual"
    assert visual.raw_layout_class == "picture"
    assert visual.extraction_method == "layout_text"
    assert visual.picture_bbox == (650, 120, 1100, 500)
    assert visual.has_extracted_picture_text is True
    assert visual.raw_extracted_picture_text == (
        "Planlanan FTE<br>12,5<br>Gerçekleşen FTE<br>11,75<br>"
    )
    assert visual.text == "Planlanan FTE\n12,5\nGerçekleşen FTE\n11,75"
    assert "intentionally omitted" not in visual.text
    assert "Start of picture text" not in visual.text


def test_picture_without_layout_text_is_one_non_factual_visual_surrogate() -> None:
    markdown = "**==> picture [400 x 200] intentionally omitted <==**\n"
    page = ExtractedPage(
        page=1,
        markdown=markdown,
        layout_boxes=(
            LayoutBox(0, "picture", (0, 0, 400, 200), 0, len(markdown)),
        ),
    )

    blocks = MarkdownAtomicUnitParser().parse_page(page)

    assert len(blocks) == 1
    assert blocks[0].text == "[visual-content-no-layout-text]"
    assert blocks[0].has_extracted_picture_text is False
    assert "intentionally omitted" not in blocks[0].text


def test_canonical_and_manifest_writers_are_byte_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "report.pdf"
    source.write_bytes(b"deterministic-source")
    blocks = MarkdownAtomicUnitParser().parse_page(
        ExtractedPage(page=2, markdown="## Başlık\n\nİçerik.\n")
    )
    units = SectionHierarchyBuilder().build(blocks, document_id="kkb-2024")
    canonical = tmp_path / "kkb-2024.units.jsonl"
    writer = CanonicalUnitWriter()
    manifest_writer = ExtractionManifestWriter()
    visual_writer = VisualProvenanceWriter()

    writer.write(units, canonical)
    manifest = manifest_writer.write(
        canonical_path=canonical,
        source_pdf=source,
        document_id="kkb-2024",
        selected_pages=[2],
        pymupdf4llm_version="0.3.4",
    )
    first_canonical = canonical.read_bytes()
    first_manifest = manifest.read_bytes()
    visual = visual_writer.write(
        canonical_path=canonical,
        blocks=blocks,
        units=units,
        document_id="kkb-2024",
    )
    first_visual = visual.read_bytes()
    writer.write(units, canonical)
    manifest_writer.write(
        canonical_path=canonical,
        source_pdf=source,
        document_id="kkb-2024",
        selected_pages=[2],
        pymupdf4llm_version="0.3.4",
    )
    visual_writer.write(
        canonical_path=canonical,
        blocks=blocks,
        units=units,
        document_id="kkb-2024",
    )

    assert canonical.read_bytes() == first_canonical
    assert manifest.read_bytes() == first_manifest
    assert visual.read_bytes() == first_visual == b""
    assert len(load_jsonl_units(canonical)) == 2
    canonical_rows = [
        json.loads(line) for line in canonical.read_text(encoding="utf-8").splitlines()
    ]
    assert canonical_rows[1]["heading_level"] is None
    assert canonical_rows[1]["source"] == {
        "page": 2,
        "physical_page": 2,
        "block": 2,
        "logical_page_side": "single",
    }
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["source_pdf"] == "report.pdf"
    assert payload["source_pdf_sha256"] == hashlib.sha256(
        b"deterministic-source"
    ).hexdigest()
    assert payload["selected_pages"] == [2]
    assert payload["extraction_parameters"] == {
        "footer": False,
        "force_ocr": False,
        "header": False,
        "layout": True,
        "layout_backend": "pymupdf.layout",
        "page_chunks": True,
        "spread_aware": True,
        "spread_detection": "physical_page_width_gt_height",
        "spread_logical_page_order": "left_then_right",
    }
    assert "not a PyMuPDF layout block ID" in payload["provenance_semantics"][
        "source.block"
    ]


def test_prepare_checkpoint_writes_canonical_and_manifest(tmp_path: Path) -> None:
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf")
    output = tmp_path / "kkb-2024.units.jsonl"

    class FakeExtractor:
        def extract(self, input_path: str | Path, *, pages: str | None) -> ExtractionResult:
            assert Path(input_path) == source
            assert pages == "2"
            return ExtractionResult(
                pages=(ExtractedPage(page=2, markdown="## Başlık\n\nİçerik."),),
                selected_pages=(2,),
                page_count=3,
                pymupdf4llm_version="0.3.4",
            )

    result = prepare_checkpoint(
        input_path=source,
        output_path=output,
        pages="2",
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )

    assert output.is_file()
    assert result.manifest_path == tmp_path / "kkb-2024.units.manifest.json"
    assert result.manifest_path.is_file()
    assert result.visual_provenance_path == (
        tmp_path / "kkb-2024.units.visual-provenance.jsonl"
    )
    assert result.visual_provenance_path.read_bytes() == b""
    assert result.picture_count == result.visual_atomic_unit_count == 0
    assert [unit.unit_id for unit in result.units] == ["h-00001", "p-00002"]


def test_prepare_checkpoint_writes_one_sidecar_record_per_picture(tmp_path: Path) -> None:
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf")
    output = tmp_path / "kkb-2024.units.jsonl"
    picture = (
        "**==> picture [200 x 100] intentionally omitted <==**\n\n"
        "**----- Start of picture text -----**<br>\nToplam Çalışan<br>908<br>"
        "**----- End of picture text -----**<br>\n"
    )

    class FakeExtractor:
        def extract(self, input_path: str | Path, *, pages: str | None) -> ExtractionResult:
            return ExtractionResult(
                pages=(
                    ExtractedPage(
                        page=48,
                        markdown=picture,
                        logical_page_side="left",
                        layout_boxes=(
                            LayoutBox(
                                7,
                                "picture",
                                (50, 100, 500, 400),
                                0,
                                len(picture),
                            ),
                        ),
                    ),
                ),
                selected_pages=(48,),
                page_count=85,
                pymupdf4llm_version="0.3.4",
            )

    result = prepare_checkpoint(
        input_path=source,
        output_path=output,
        pages="48",
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )

    assert result.picture_count == result.visual_atomic_unit_count == 1
    assert len(result.units) == 1
    unit = result.units[0]
    assert unit.unit_id == "v-00001"
    assert unit.type == UnitType.PARAGRAPH
    assert unit.text == "Toplam Çalışan\n908"
    assert unit.source.model_dump(exclude_none=True) == {
        "page": 48,
        "block": 1,
        "physical_page": 48,
        "logical_page_side": "left",
        "picture_bbox": [50.0, 100.0, 500.0, 400.0],
        "raw_layout_class": "picture",
        "content_origin": "visual",
        "extraction_method": "layout_text",
        "visual_provenance_id": "picture-p00048-left-007",
    }
    sidecar_rows = [
        json.loads(line)
        for line in result.visual_provenance_path.read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert len(sidecar_rows) == 1
    assert sidecar_rows[0]["canonical_unit_id"] == "v-00001"
    assert sidecar_rows[0]["raw_extracted_picture_text"] == (
        "Toplam Çalışan<br>908<br>"
    )
    assert "intentionally omitted" not in sidecar_rows[0]["textual_surrogate"]


def test_picture_without_layout_text_is_sidecar_only_not_canonical(
    tmp_path: Path,
) -> None:
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf")
    output = tmp_path / "kkb-2024.units.jsonl"
    paragraph = "Canonical paragraph.\n\n"
    picture = "**==> picture [200 x 100] intentionally omitted <==**\n"
    markdown = paragraph + picture

    class FakeExtractor:
        def extract(self, input_path: str | Path, *, pages: str | None) -> ExtractionResult:
            return ExtractionResult(
                pages=(
                    ExtractedPage(
                        page=48,
                        markdown=markdown,
                        logical_page_side="right",
                        layout_boxes=(
                            LayoutBox(
                                1,
                                "text",
                                (650, 100, 900, 180),
                                0,
                                len(paragraph),
                            ),
                            LayoutBox(
                                2,
                                "picture",
                                (650, 200, 1100, 500),
                                len(paragraph),
                                len(markdown),
                            ),
                        ),
                    ),
                ),
                selected_pages=(48,),
                page_count=85,
                pymupdf4llm_version="0.3.4",
            )

    result = prepare_checkpoint(
        input_path=source,
        output_path=output,
        pages="48",
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )

    assert result.picture_count == 1
    assert result.visual_atomic_unit_count == 0
    assert [unit.text for unit in result.units] == ["Canonical paragraph."]
    assert all("visual-content-no-layout-text" not in unit.text for unit in result.units)
    sidecar_rows = [
        json.loads(line)
        for line in result.visual_provenance_path.read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert len(sidecar_rows) == 1
    assert sidecar_rows[0]["has_extracted_picture_text"] is False
    assert sidecar_rows[0]["canonical_unit_id"] is None
    assert sidecar_rows[0]["textual_surrogate"] is None
    assert sidecar_rows[0]["raw_layout_class"] == "picture"


def test_prepare_checkpoint_rejects_empty_selected_pages(tmp_path: Path) -> None:
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf")

    class EmptyExtractor:
        def extract(self, input_path: str | Path, *, pages: str | None) -> ExtractionResult:
            return ExtractionResult(
                pages=(ExtractedPage(page=1, markdown="\n"),),
                selected_pages=(1,),
                page_count=1,
                pymupdf4llm_version="0.3.4",
            )

    with pytest.raises(ValueError, match="no canonical atomic units"):
        prepare_checkpoint(
            input_path=source,
            output_path=tmp_path / "out.jsonl",
            extractor=EmptyExtractor(),  # type: ignore[arg-type]
        )
