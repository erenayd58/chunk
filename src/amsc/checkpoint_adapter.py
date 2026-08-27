from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import hashlib
import importlib
import json
from pathlib import Path
import re
from types import ModuleType
from typing import Any

from .checkpoint_layout import (
    CheckpointLayoutProfile,
    ExplicitLogicalPageColumnOrderer,
    LayoutBox,
    load_checkpoint_layout_profile,
)
from .io import validate_document_units
from .models import RawDocumentUnit, SemanticRole, SourceSpan, UnitType
from .visual_grid import (
    BBox,
    PictureGeometry,
    VisualTextLine,
    reconstruct_card_grid,
)


PYMUPDF4LLM_VERSION = "0.3.4"


class CheckpointLayoutUnavailableError(RuntimeError):
    """Raised instead of silently using PyMuPDF4LLM's legacy backend."""


@dataclass(frozen=True)
class LayoutBackend:
    pymupdf: ModuleType
    pymupdf4llm: ModuleType


@dataclass(frozen=True)
class ExtractedPage:
    page: int
    markdown: str
    logical_page_side: str = "single"
    physical_page_width: float | None = None
    physical_page_height: float | None = None
    logical_page_width: float | None = None
    layout_boxes: tuple[LayoutBox, ...] = ()


@dataclass(frozen=True)
class ExtractionResult:
    pages: tuple[ExtractedPage, ...]
    selected_pages: tuple[int, ...]
    page_count: int
    pymupdf4llm_version: str
    layout_profile: CheckpointLayoutProfile | None = None


@dataclass(frozen=True)
class AtomicBlock:
    page: int
    block: int
    text: str
    unit_type: UnitType
    heading_level: int | None = None
    logical_page_side: str = "single"
    unit_id_prefix: str | None = None
    picture_bbox: tuple[float, float, float, float] | None = None
    raw_layout_class: str | None = None
    content_origin: str | None = None
    extraction_method: str | None = None
    visual_provenance_id: str | None = None
    raw_extracted_picture_text: str | None = None
    has_extracted_picture_text: bool | None = None
    layout_box_index: int | None = None
    logical_bbox: tuple[float, float, float, float] | None = None
    physical_bbox: tuple[float, float, float, float] | None = None
    logical_column: str | None = None
    layout_band: int | None = None
    layout_reading_order_index: int | None = None
    reading_order_policy: str | None = None
    # Largest type size printed inside this block's layout box. Present only
    # when the extractor was asked to measure prominence.
    font_size: float | None = None
    # What this heading is, as opposed to what it looks like. Present only when
    # the semantic-role pass ran; see :mod:`amsc.semantic_roles`.
    semantic_role: SemanticRole | None = None
    opens_section: bool | None = None
    role_reason: str | None = None


@dataclass(frozen=True)
class CanonicalExtraction:
    """In-memory canonical units plus the provenance needed to persist them."""

    units: tuple[RawDocumentUnit, ...]
    blocks: tuple[AtomicBlock, ...]
    selected_pages: tuple[int, ...]
    pymupdf4llm_version: str
    picture_count: int
    layout_profile: CheckpointLayoutProfile | None = None
    page_count: int | None = None
    portrait_single_pages: tuple[int, ...] = ()
    landscape_spread_pages: tuple[int, ...] = ()


@dataclass(frozen=True)
class PreparationResult:
    units: tuple[RawDocumentUnit, ...]
    manifest_path: Path
    visual_provenance_path: Path
    selected_pages: tuple[int, ...]
    pymupdf4llm_version: str
    picture_count: int
    visual_atomic_unit_count: int
    layout_profile: CheckpointLayoutProfile | None = None


@dataclass(frozen=True)
class _LogicalPageSpec:
    physical_page: int
    logical_page_side: str
    physical_page_width: float
    physical_page_height: float
    crop_x_offset: float
    logical_page_width: float


def _logical_bbox(
    spec: _LogicalPageSpec,
    bbox: Sequence[float],
) -> BBox:
    """Clamp a layout box to the cropped logical page it was reported on."""
    return (
        min(spec.logical_page_width, max(0.0, float(bbox[0]))),
        min(spec.physical_page_height, max(0.0, float(bbox[1]))),
        min(spec.logical_page_width, max(0.0, float(bbox[2]))),
        min(spec.physical_page_height, max(0.0, float(bbox[3]))),
    )


def _physical_bbox(
    spec: _LogicalPageSpec,
    logical_bbox: BBox,
) -> BBox:
    """Move a logical-page box back into physical PDF page coordinates."""
    return (
        min(
            spec.physical_page_width,
            max(0.0, logical_bbox[0] + spec.crop_x_offset),
        ),
        logical_bbox[1],
        min(
            spec.physical_page_width,
            max(0.0, logical_bbox[2] + spec.crop_x_offset),
        ),
        logical_bbox[3],
    )


def _page_text_lines(page: Any) -> tuple[VisualTextLine, ...]:
    """Every text line on a physical page with its box and largest font size."""
    lines: list[VisualTextLine] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            spans = [
                span
                for span in line.get("spans", [])
                if str(span.get("text", "")).strip()
            ]
            if not spans:
                continue
            box = line.get("bbox")
            if not isinstance(box, (list, tuple)) or len(box) != 4:
                continue
            lines.append(
                VisualTextLine(
                    text=" ".join(str(span["text"]).strip() for span in spans),
                    bbox=tuple(float(value) for value in box),
                    font_size=max(float(span.get("size", 0.0)) for span in spans),
                )
            )
    return tuple(lines)


def _page_container_rects(page: Any) -> tuple[BBox, ...]:
    """Bounding rectangles of every vector drawing on a physical page."""
    rects: list[BBox] = []
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect is None:
            continue
        rects.append(
            (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))
        )
    return tuple(rects)


def _capture_picture_geometry(
    source_document: Any,
    logical_pages: Sequence[_LogicalPageSpec],
    chunks: Sequence[Any],
) -> dict[tuple[int, int], PictureGeometry]:
    """Collect text and container geometry for every picture region.

    Runs while the source PDF is still open, keyed by ``(logical page index,
    layout box index)`` so the caller can attach it without a second pass.
    Only pages that actually contain a picture are read.
    """
    if len(chunks) != len(logical_pages):
        return {}
    geometry: dict[tuple[int, int], PictureGeometry] = {}
    per_page: dict[int, tuple[tuple[VisualTextLine, ...], tuple[BBox, ...]]] = {}
    for logical_index, (spec, chunk) in enumerate(
        zip(logical_pages, chunks), start=1
    ):
        if not isinstance(chunk, dict):
            continue
        for raw_box in chunk.get("page_boxes") or []:
            if not isinstance(raw_box, dict) or raw_box.get("class") != "picture":
                continue
            bbox = raw_box.get("bbox")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            region = _physical_bbox(spec, _logical_bbox(spec, bbox))
            if spec.physical_page not in per_page:
                page = source_document[spec.physical_page - 1]
                per_page[spec.physical_page] = (
                    _page_text_lines(page),
                    _page_container_rects(page),
                )
            lines, rects = per_page[spec.physical_page]
            geometry[(logical_index, int(raw_box.get("index", -1)))] = (
                PictureGeometry(
                    region=region,
                    lines=tuple(
                        line
                        for line in lines
                        if _box_centre_inside(line.bbox, region)
                    ),
                    containers=tuple(
                        rect for rect in rects if _boxes_intersect(rect, region)
                    ),
                )
            )
    return geometry


def _capture_box_prominence(
    source_document: Any,
    logical_pages: Sequence[_LogicalPageSpec],
    chunks: Sequence[Any],
) -> dict[tuple[int, int], float]:
    """Largest type size printed inside every non-picture layout box.

    Runs while the source PDF is still open, keyed by ``(logical page index,
    layout box index)`` exactly like :func:`_capture_picture_geometry`, and
    reuses the same line reader. Only the pages that carry a layout box are
    read.
    """
    if len(chunks) != len(logical_pages):
        return {}
    sizes: dict[tuple[int, int], float] = {}
    per_page: dict[int, tuple[VisualTextLine, ...]] = {}
    for logical_index, (spec, chunk) in enumerate(
        zip(logical_pages, chunks), start=1
    ):
        if not isinstance(chunk, dict):
            continue
        for raw_box in chunk.get("page_boxes") or []:
            if not isinstance(raw_box, dict) or raw_box.get("class") == "picture":
                continue
            bbox = raw_box.get("bbox")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            region = _physical_bbox(spec, _logical_bbox(spec, bbox))
            if spec.physical_page not in per_page:
                per_page[spec.physical_page] = _page_text_lines(
                    source_document[spec.physical_page - 1]
                )
            inside = [
                line.font_size
                for line in per_page[spec.physical_page]
                if _box_centre_inside(line.bbox, region)
            ]
            if inside:
                sizes[(logical_index, int(raw_box.get("index", -1)))] = max(inside)
    return sizes


def _box_centre_inside(box: BBox, region: BBox) -> bool:
    x = (box[0] + box[2]) / 2.0
    y = (box[1] + box[3]) / 2.0
    return region[0] <= x <= region[2] and region[1] <= y <= region[3]


def _boxes_intersect(box: BBox, region: BBox) -> bool:
    return (
        box[0] < region[2]
        and box[2] > region[0]
        and box[1] < region[3]
        and box[3] > region[1]
    )


def load_layout_backend(
    import_module: Callable[[str], ModuleType] = importlib.import_module,
) -> LayoutBackend:
    """Load the 0.3.4 layout backend without allowing legacy fallback.

    PyMuPDF4LLM 0.3.4 selects its implementation at import time by checking
    ``pymupdf._get_layout``. Importing ``pymupdf.layout`` first is therefore a
    correctness requirement, not a cosmetic ordering preference.
    """

    install_hint = 'py -3.11 -m pip install -e ".[checkpoint]"'
    try:
        import_module("pymupdf.layout")
    except Exception as exc:
        raise CheckpointLayoutUnavailableError(
            "PyMuPDF layout dependency is unavailable; install it with: "
            f"{install_hint}"
        ) from exc

    try:
        pymupdf4llm = import_module("pymupdf4llm")
        pymupdf = import_module("pymupdf")
    except Exception as exc:
        raise CheckpointLayoutUnavailableError(
            "PyMuPDF4LLM checkpoint dependency is unavailable; install it with: "
            f"{install_hint}"
        ) from exc

    version = getattr(pymupdf4llm, "__version__", None)
    layout_dispatch_active = (
        getattr(pymupdf, "_get_layout", None) is not None
        and hasattr(pymupdf4llm, "document_layout")
        and getattr(getattr(pymupdf4llm, "to_markdown", None), "__module__", None)
        == "pymupdf4llm"
        and not hasattr(pymupdf4llm, "IdentifyHeaders")
    )
    if version != PYMUPDF4LLM_VERSION:
        raise CheckpointLayoutUnavailableError(
            "Checkpoint extraction requires pymupdf4llm=="
            f"{PYMUPDF4LLM_VERSION}; found {version!r}"
        )
    if not layout_dispatch_active:
        raise CheckpointLayoutUnavailableError(
            "PyMuPDF4LLM layout backend is not active. Legacy extraction is "
            "not permitted; start a fresh process after installing the "
            f"checkpoint extra with: {install_hint}"
        )
    return LayoutBackend(pymupdf=pymupdf, pymupdf4llm=pymupdf4llm)


class PageSelectionParser:
    _ITEM = re.compile(r"^(\d+)(?:-(\d+))?$")

    @classmethod
    def parse(cls, value: str | None, *, page_count: int) -> tuple[int, ...]:
        if page_count < 1:
            raise ValueError("PDF must contain at least one page")
        if value is None:
            return tuple(range(1, page_count + 1))
        if not value.strip():
            raise ValueError("--pages cannot be empty")

        selected: list[int] = []
        seen: set[int] = set()
        for raw_item in value.split(","):
            item = raw_item.strip()
            match = cls._ITEM.fullmatch(item)
            if match is None:
                raise ValueError(
                    f"Invalid page selection {item!r}; use values like 40-55,61"
                )
            start = int(match.group(1))
            end = int(match.group(2) or start)
            if start < 1 or end < 1:
                raise ValueError("Page numbers are 1-based and must be positive")
            if end < start:
                raise ValueError(f"Descending page range is not allowed: {item}")
            if end > page_count:
                raise ValueError(
                    f"Page selection {item} exceeds PDF page count {page_count}"
                )
            for page in range(start, end + 1):
                if page in seen:
                    raise ValueError(f"Duplicate page selection: {page}")
                seen.add(page)
                selected.append(page)
        return tuple(sorted(selected))


class PyMuPDF4LLMExtractor:
    def __init__(
        self,
        backend_loader: Callable[[], LayoutBackend] = load_layout_backend,
        *,
        layout_profile: CheckpointLayoutProfile | None = None,
        capture_picture_geometry: bool = False,
        capture_heading_prominence: bool = False,
    ) -> None:
        self.backend_loader = backend_loader
        self.layout_profile = layout_profile
        # Opt-in. Off by default so the frozen research extraction keeps
        # producing byte-identical canonical units.
        self.capture_picture_geometry = capture_picture_geometry
        # Opt-in for the same reason: measuring type size costs one text read
        # per page and is only needed when heading levels are recovered.
        self.capture_heading_prominence = capture_heading_prominence

    def extract(
        self,
        input_path: str | Path,
        *,
        pages: str | None,
    ) -> ExtractionResult:
        source = Path(input_path)
        if not source.is_file():
            raise ValueError(f"Input PDF does not exist: {source}")

        backend = self.backend_loader()
        try:
            with backend.pymupdf.open(str(source)) as source_document:
                page_count = int(source_document.page_count)
                selected = PageSelectionParser.parse(pages, page_count=page_count)
                extraction_document = backend.pymupdf.open()
                logical_pages: list[_LogicalPageSpec] = []
                try:
                    for physical_page in selected:
                        source_page = source_document[physical_page - 1]
                        width = float(source_page.rect.width)
                        height = float(source_page.rect.height)
                        if self.layout_profile is not None:
                            if width <= height:
                                raise ValueError(
                                    "The explicit left-right spread profile requires "
                                    f"a landscape physical page; page {physical_page} "
                                    f"is {width} x {height}"
                                )
                            midpoint = width / 2.0
                            crops = (
                                ("left", 0.0, midpoint),
                                ("right", midpoint, width),
                            )
                        elif width > height:
                            midpoint = width / 2.0
                            crops = (
                                ("left", 0.0, midpoint),
                                ("right", midpoint, width),
                            )
                        else:
                            crops = (("single", 0.0, width),)

                        for side, x0, x1 in crops:
                            extraction_document.insert_pdf(
                                source_document,
                                from_page=physical_page - 1,
                                to_page=physical_page - 1,
                            )
                            extracted_page = extraction_document[-1]
                            if side != "single":
                                extracted_page.set_cropbox(
                                    backend.pymupdf.Rect(x0, 0.0, x1, height)
                                )
                            logical_pages.append(
                                _LogicalPageSpec(
                                    physical_page=physical_page,
                                    logical_page_side=side,
                                    physical_page_width=width,
                                    physical_page_height=height,
                                    crop_x_offset=x0,
                                    logical_page_width=x1 - x0,
                                )
                            )

                    chunks = backend.pymupdf4llm.to_markdown(
                        extraction_document,
                        page_chunks=True,
                        header=False,
                        footer=False,
                        pages=None,
                        force_ocr=False,
                    )
                finally:
                    extraction_document.close()

                picture_geometry = (
                    _capture_picture_geometry(
                        source_document, logical_pages, chunks
                    )
                    if self.capture_picture_geometry
                    else {}
                )
                box_prominence = (
                    _capture_box_prominence(
                        source_document, logical_pages, chunks
                    )
                    if self.capture_heading_prominence
                    else {}
                )
        except Exception as exc:
            raise ValueError(f"Unable to open input PDF {source}: {exc}") from exc

        if not isinstance(chunks, list):
            raise ValueError("PyMuPDF4LLM page_chunks=True did not return a list")
        if len(chunks) != len(logical_pages):
            raise ValueError(
                "PyMuPDF4LLM returned a logical page count that does not match "
                f"the spread-aware plan: {len(chunks)} != {len(logical_pages)}"
            )

        extracted: list[ExtractedPage] = []
        for logical_index, (spec, chunk) in enumerate(
            zip(logical_pages, chunks, strict=True), start=1
        ):
            if not isinstance(chunk, dict):
                raise ValueError("PyMuPDF4LLM page chunk must be a dictionary")
            metadata = chunk.get("metadata")
            actual_page = (
                metadata.get("page_number") if isinstance(metadata, dict) else None
            )
            if actual_page != logical_index:
                raise ValueError(
                    "PyMuPDF4LLM page metadata does not match the generated "
                    f"logical page: {actual_page!r} != {logical_index}"
                )
            markdown = chunk.get("text", "")
            if not isinstance(markdown, str):
                raise ValueError("PyMuPDF4LLM page text must be a string")
            raw_boxes = chunk.get("page_boxes", [])
            if not isinstance(raw_boxes, list):
                raise ValueError("PyMuPDF4LLM page_boxes must be a list")
            layout_boxes: list[LayoutBox] = []
            for raw_box in raw_boxes:
                if not isinstance(raw_box, dict):
                    raise ValueError("PyMuPDF4LLM layout box must be a dictionary")
                bbox = raw_box.get("bbox")
                pos = raw_box.get("pos")
                layout_class = raw_box.get("class")
                if (
                    not isinstance(bbox, (list, tuple))
                    or len(bbox) != 4
                    or not isinstance(pos, (list, tuple))
                    or len(pos) != 2
                    or not isinstance(layout_class, str)
                ):
                    raise ValueError("Malformed PyMuPDF4LLM page box")
                start, end = int(pos[0]), int(pos[1])
                if not 0 <= start <= end <= len(markdown):
                    raise ValueError("Layout box Markdown offsets are out of range")
                logical_bbox = _logical_bbox(spec, bbox)
                physical_bbox = _physical_bbox(spec, logical_bbox)
                box_index = int(raw_box.get("index", len(layout_boxes)))
                layout_boxes.append(
                    LayoutBox(
                        index=box_index,
                        layout_class=layout_class,
                        bbox=physical_bbox,
                        markdown_start=start,
                        markdown_end=end,
                        logical_bbox=logical_bbox,
                        picture_geometry=picture_geometry.get(
                            (logical_index, box_index)
                        ),
                        font_size=box_prominence.get((logical_index, box_index)),
                    )
                )
            ordered_boxes: tuple[LayoutBox, ...]
            if self.layout_profile is not None:
                ordered_boxes = ExplicitLogicalPageColumnOrderer(
                    self.layout_profile
                ).order(
                    layout_boxes,
                    logical_page_width=spec.logical_page_width,
                )
            else:
                ordered_boxes = tuple(layout_boxes)
            extracted.append(
                ExtractedPage(
                    page=spec.physical_page,
                    markdown=markdown,
                    logical_page_side=spec.logical_page_side,
                    physical_page_width=spec.physical_page_width,
                    physical_page_height=spec.physical_page_height,
                    logical_page_width=spec.logical_page_width,
                    layout_boxes=ordered_boxes,
                )
            )

        return ExtractionResult(
            pages=tuple(extracted),
            selected_pages=selected,
            page_count=page_count,
            pymupdf4llm_version=str(backend.pymupdf4llm.__version__),
            layout_profile=self.layout_profile,
        )


class MarkdownAtomicUnitParser:
    _HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$")
    _LIST_ITEM = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+\S")
    _TABLE_DIVIDER_CELL = re.compile(r"^:?-{3,}:?$")
    _PICTURE_PLACEHOLDER = re.compile(
        r"\*\*==>\s*picture\s*\[[^\]]+\]\s*intentionally omitted\s*<==\*\*",
        flags=re.IGNORECASE,
    )
    _PICTURE_TEXT_START = re.compile(
        r"\*\*-----\s*Start of picture text\s*-----\*\*(?:<br\s*/?>)?",
        flags=re.IGNORECASE,
    )
    _PICTURE_TEXT_END = re.compile(
        r"\*\*-----\s*End of picture text\s*-----\*\*(?:<br\s*/?>)?",
        flags=re.IGNORECASE,
    )
    _HTML_BREAK = re.compile(r"<br\s*/?>", flags=re.IGNORECASE)
    _NO_LAYOUT_TEXT_SURROGATE = "[visual-content-no-layout-text]"

    def parse_page(
        self,
        page: ExtractedPage,
        *,
        block_start: int = 1,
    ) -> list[AtomicBlock]:
        if block_start < 1:
            raise ValueError("block_start must be positive")
        if page.layout_boxes:
            parsed: list[AtomicBlock] = []
            for layout_box in page.layout_boxes:
                segment = page.markdown[
                    layout_box.markdown_start : layout_box.markdown_end
                ]
                if not segment.strip():
                    continue
                if layout_box.layout_class == "picture":
                    parsed.append(
                        self._picture_block(
                            page=page,
                            layout_box=layout_box,
                            markdown=segment,
                        )
                    )
                else:
                    parsed.extend(
                        self._parse_markdown(
                            markdown=segment,
                            page=page,
                            layout_box=layout_box,
                        )
                    )
            return [
                AtomicBlock(
                    **{
                        **block.__dict__,
                        "block": block_start + offset,
                    }
                )
                for offset, block in enumerate(parsed)
            ]
        return self._parse_markdown(
            markdown=page.markdown,
            page=page,
            block_start=block_start,
        )

    def _parse_markdown(
        self,
        *,
        markdown: str,
        page: ExtractedPage,
        block_start: int = 1,
        layout_box: LayoutBox | None = None,
    ) -> list[AtomicBlock]:
        lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        raw_blocks: list[tuple[list[str], int | None]] = []
        current: list[str] = []
        in_fence = False

        def flush() -> None:
            nonlocal current
            trimmed = self._trim_blank_lines(current)
            if trimmed:
                raw_blocks.append((trimmed, None))
            current = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = not in_fence
                current.append(line.rstrip())
                continue
            heading = None if in_fence else self._HEADING.fullmatch(line.strip())
            if heading is not None:
                flush()
                raw_blocks.append(([heading.group(2).strip()], len(heading.group(1))))
                continue
            if not stripped and not in_fence:
                flush()
                continue
            current.append(line.rstrip())
        flush()

        result: list[AtomicBlock] = []
        for block_index, (block_lines, heading_level) in enumerate(
            raw_blocks, start=block_start
        ):
            text = "\n".join(block_lines).strip()
            if not text:
                continue
            if heading_level is not None:
                unit_type = UnitType.HEADING
            elif self._is_table(block_lines):
                unit_type = UnitType.TABLE
            elif self._LIST_ITEM.match(block_lines[0]):
                unit_type = UnitType.LIST
            else:
                unit_type = UnitType.PARAGRAPH
            result.append(
                AtomicBlock(
                    page=page.page,
                    block=block_index,
                    text=text,
                    unit_type=unit_type,
                    heading_level=heading_level,
                    logical_page_side=page.logical_page_side,
                    raw_layout_class=(
                        layout_box.layout_class if layout_box is not None else None
                    ),
                    layout_box_index=(
                        layout_box.index if layout_box is not None else None
                    ),
                    logical_bbox=(
                        layout_box.logical_bbox if layout_box is not None else None
                    ),
                    physical_bbox=(
                        layout_box.bbox if layout_box is not None else None
                    ),
                    logical_column=(
                        layout_box.logical_column if layout_box is not None else None
                    ),
                    layout_band=(
                        layout_box.layout_band if layout_box is not None else None
                    ),
                    layout_reading_order_index=(
                        layout_box.reading_order_index
                        if layout_box is not None
                        else None
                    ),
                    reading_order_policy=(
                        layout_box.reading_order_policy
                        if layout_box is not None
                        else None
                    ),
                    font_size=(
                        layout_box.font_size if layout_box is not None else None
                    ),
                )
            )
        return result

    def _picture_block(
        self,
        *,
        page: ExtractedPage,
        layout_box: LayoutBox,
        markdown: str,
    ) -> AtomicBlock:
        raw_picture_text = self._extract_picture_text(markdown)
        # PyMuPDF4LLM serializes a picture's text by vertical position,
        # which breaks the label/value pairing of a KPI card grid whenever
        # two cards in a row use different font sizes. When the card
        # geometry is unambiguous the pairing is rebuilt from it; otherwise
        # the extractor's own text is kept untouched.
        reconstructed = reconstruct_card_grid(layout_box.picture_geometry)
        if reconstructed is not None:
            surrogate = reconstructed
            extraction_method = "layout_text_card_grid"
        elif raw_picture_text:
            surrogate = self._HTML_BREAK.sub("\n", raw_picture_text).strip()
            extraction_method = "layout_text"
        else:
            surrogate = self._NO_LAYOUT_TEXT_SURROGATE
            extraction_method = "layout_text"
        visual_id = (
            f"picture-p{page.page:05d}-{page.logical_page_side}-"
            f"{layout_box.index:03d}"
        )
        return AtomicBlock(
            page=page.page,
            block=0,
            text=surrogate,
            unit_type=UnitType.PARAGRAPH,
            logical_page_side=page.logical_page_side,
            unit_id_prefix="v",
            picture_bbox=layout_box.bbox,
            raw_layout_class=layout_box.layout_class,
            content_origin="visual",
            extraction_method=extraction_method,
            visual_provenance_id=visual_id,
            raw_extracted_picture_text=raw_picture_text or None,
            has_extracted_picture_text=bool(raw_picture_text)
            or reconstructed is not None,
            layout_box_index=layout_box.index,
            logical_bbox=layout_box.logical_bbox,
            physical_bbox=layout_box.bbox,
            logical_column=layout_box.logical_column,
            layout_band=layout_box.layout_band,
            layout_reading_order_index=layout_box.reading_order_index,
            reading_order_policy=layout_box.reading_order_policy,
        )

    def _extract_picture_text(self, markdown: str) -> str:
        start = self._PICTURE_TEXT_START.search(markdown)
        if start is not None:
            end = self._PICTURE_TEXT_END.search(markdown, start.end())
            stop = end.start() if end is not None else len(markdown)
            return markdown[start.end() : stop].strip()
        without_placeholder = self._PICTURE_PLACEHOLDER.sub("", markdown)
        without_end_marker = self._PICTURE_TEXT_END.sub("", without_placeholder)
        return without_end_marker.strip()

    @staticmethod
    def _trim_blank_lines(lines: Sequence[str]) -> list[str]:
        start = 0
        end = len(lines)
        while start < end and not lines[start].strip():
            start += 1
        while end > start and not lines[end - 1].strip():
            end -= 1
        return list(lines[start:end])

    @classmethod
    def _is_table(cls, lines: Sequence[str]) -> bool:
        if len(lines) < 2 or "|" not in lines[0] or "|" not in lines[1]:
            return False
        cells = [cell.strip() for cell in lines[1].strip().strip("|").split("|")]
        return bool(cells) and all(cls._TABLE_DIVIDER_CELL.fullmatch(cell) for cell in cells)


class SectionHierarchyBuilder:
    _PREFIXES = {
        UnitType.HEADING: "h",
        UnitType.PARAGRAPH: "p",
        UnitType.LIST: "l",
        UnitType.TABLE: "t",
    }

    def build(
        self,
        blocks: Sequence[AtomicBlock],
        *,
        document_id: str,
    ) -> list[RawDocumentUnit]:
        active_headings: list[tuple[int, str]] = []
        units: list[RawDocumentUnit] = []
        for order, block in enumerate(blocks, start=1):
            if block.unit_type == UnitType.HEADING:
                if block.heading_level is None:
                    raise AssertionError("Heading block is missing heading_level")
                # Looking like a heading is not the same claim as bearing
                # hierarchy. Once the role pass has decided, only a heading it
                # marked ``opens_section`` may touch the stack; a corpus
                # extracted before that pass existed carries no decision, and
                # every heading opens a section as it always did.
                if block.opens_section is not False:
                    active_headings = [
                        item for item in active_headings if item[0] < block.heading_level
                    ]
                    active_headings.append((block.heading_level, block.text))
            section_path = [text for _, text in active_headings]
            source_data: dict[str, Any] = {
                "page": block.page,
                "physical_page": block.page,
                "block": block.block,
                "logical_page_side": block.logical_page_side,
            }
            layout_source = {
                "layout_box_index": block.layout_box_index,
                "layout_bbox_logical": (
                    list(block.logical_bbox)
                    if block.logical_bbox is not None
                    else None
                ),
                "layout_bbox_physical": (
                    list(block.physical_bbox)
                    if block.physical_bbox is not None
                    else None
                ),
                "raw_layout_class": block.raw_layout_class,
                "logical_column": block.logical_column,
                "layout_band": block.layout_band,
                "layout_reading_order_index": (
                    block.layout_reading_order_index
                ),
                "reading_order_policy": block.reading_order_policy,
            }
            if block.reading_order_policy is not None:
                source_data.update(
                    {
                        key: value
                        for key, value in layout_source.items()
                        if value is not None
                    }
                )
            if block.content_origin == "visual":
                source_data.update(
                    {
                        "picture_bbox": list(block.picture_bbox or ()),
                        "raw_layout_class": block.raw_layout_class,
                        "content_origin": block.content_origin,
                        "extraction_method": block.extraction_method,
                        "visual_provenance_id": block.visual_provenance_id,
                    }
                )
            unit = RawDocumentUnit.model_validate(
                {
                    "document_id": document_id,
                    "unit_id": (
                        f"{block.unit_id_prefix or self._PREFIXES[block.unit_type]}-"
                        f"{order:05d}"
                    ),
                    "order": order,
                    "text": block.text,
                    "type": block.unit_type,
                    "heading_level": block.heading_level,
                    "semantic_role": block.semantic_role,
                    "opens_section": block.opens_section,
                    "section_path": section_path,
                    "source": SourceSpan.model_validate(source_data),
                }
            )
            units.append(unit)
        validate_document_units(units)
        return units


class CanonicalUnitWriter:
    def write(self, units: Sequence[RawDocumentUnit], path: str | Path) -> Path:
        validated = list(units)
        validate_document_units(validated)
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        rows: list[str] = []
        for unit in validated:
            row = unit.model_dump(mode="json", exclude_none=False)
            row["source"] = unit.source.model_dump(mode="json", exclude_none=True)
            # A field that only exists once a pass has produced it is omitted
            # when it has not, so a corpus extracted without that pass stays
            # byte-identical to the one the frozen sha was taken from.
            for optional in ("semantic_role", "opens_section"):
                if row.get(optional) is None:
                    row.pop(optional, None)
            rows.append(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
        payload = "".join(rows)
        destination.write_text(payload, encoding="utf-8", newline="\n")
        return destination


class VisualProvenanceWriter:
    @staticmethod
    def path_for(canonical_path: str | Path) -> Path:
        return Path(canonical_path).with_suffix(".visual-provenance.jsonl")

    def write(
        self,
        *,
        canonical_path: str | Path,
        blocks: Sequence[AtomicBlock],
        units: Sequence[RawDocumentUnit],
        document_id: str,
    ) -> Path:
        visual_units = {
            getattr(unit.source, "visual_provenance_id", None): unit
            for unit in units
            if getattr(unit.source, "content_origin", None) == "visual"
        }
        rows: list[str] = []
        for block in blocks:
            if block.content_origin != "visual":
                continue
            unit = visual_units.get(block.visual_provenance_id)
            payload = {
                "canonical_unit_id": unit.unit_id if unit is not None else None,
                "content_origin": "visual",
                "document_id": document_id,
                "extraction_method": "layout_text",
                "has_extracted_picture_text": bool(
                    block.has_extracted_picture_text
                ),
                "logical_page_side": block.logical_page_side,
                "layout_band": block.layout_band,
                "layout_bbox_logical": (
                    list(block.logical_bbox)
                    if block.logical_bbox is not None
                    else None
                ),
                "layout_bbox_physical": (
                    list(block.physical_bbox)
                    if block.physical_bbox is not None
                    else None
                ),
                "layout_box_index": block.layout_box_index,
                "layout_reading_order_index": block.layout_reading_order_index,
                "logical_column": block.logical_column,
                "physical_page": block.page,
                "picture_bbox": list(block.picture_bbox or ()),
                "raw_extracted_picture_text": block.raw_extracted_picture_text,
                "raw_layout_class": block.raw_layout_class,
                "reading_order_policy": block.reading_order_policy,
                "schema_version": "1.0",
                "textual_surrogate": unit.text if unit is not None else None,
                "visual_provenance_id": block.visual_provenance_id,
            }
            rows.append(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )
        destination = self.path_for(canonical_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("".join(rows), encoding="utf-8", newline="\n")
        return destination


class ExtractionManifestWriter:
    @staticmethod
    def path_for(canonical_path: str | Path) -> Path:
        return Path(canonical_path).with_suffix(".manifest.json")

    def write(
        self,
        *,
        canonical_path: str | Path,
        source_pdf: str | Path,
        document_id: str,
        selected_pages: Sequence[int],
        pymupdf4llm_version: str,
        visual_provenance_path: str | Path | None = None,
        layout_profile: CheckpointLayoutProfile | None = None,
    ) -> Path:
        extraction_parameters: dict[str, Any] = {
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
        if layout_profile is not None:
            extraction_parameters.update(
                {
                    "layout_profile": layout_profile.profile_id,
                    "logical_columns": layout_profile.logical_columns,
                    "reading_order": layout_profile.reading_order,
                    "spread_detection": "explicit_profile_requires_landscape",
                    "spread_mode": layout_profile.spread_mode,
                }
            )
        manifest = {
            "document_id": document_id,
            "extraction_parameters": extraction_parameters,
            "layout_profile": (
                layout_profile.model_dump(mode="json")
                if layout_profile is not None
                else None
            ),
            "page_number_semantics": {
                "canonical_source_page": "1-based physical PDF page",
                "cli": "1-based physical PDF pages; ranges are inclusive",
                "pymupdf_pages_argument": (
                    "all pages of the generated logical-page document "
                    "(pages=None)"
                ),
            },
            "provenance_semantics": {
                "source.block": (
                    "adapter-local 1-based atomic block index per page; "
                    "not a PyMuPDF layout block ID"
                ),
                "source.page": "1-based physical PDF page",
                "source.logical_page_side": (
                    "left/right for landscape spreads; single otherwise"
                ),
                "source.picture_bbox": (
                    "physical PDF page coordinates for visual-content units"
                ),
                "source.layout_bbox_logical": (
                    "coordinates inside the cropped logical page; used for "
                    "explicit checkpoint reading order"
                ),
                "source.layout_bbox_physical": (
                    "the same layout box mapped to physical PDF coordinates"
                ),
                "source.layout_box_index": (
                    "PyMuPDF4LLM page_boxes index; not a stable production "
                    "layout identity"
                ),
                "source.layout_reading_order_index": (
                    "adapter-computed 1-based box order inside one logical page"
                ),
            },
            "pymupdf4llm_version": pymupdf4llm_version,
            "schema_version": "1.0",
            "selected_pages": list(selected_pages),
            "source_pdf": Path(source_pdf).name,
            "source_pdf_sha256": sha256_file(source_pdf),
            "visual_content_policy": {
                "canonical_type_mapping": "paragraph_with_visual_provenance",
                "empty_layout_text_canonical_unit": False,
                "empty_layout_text_sidecar_only": True,
                "one_atomic_unit_per_picture": True,
                "placeholder_is_semantic_content": False,
            },
            "visual_provenance_file": (
                Path(visual_provenance_path).name
                if visual_provenance_path is not None
                else None
            ),
        }
        destination = self.path_for(canonical_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return destination


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_canonical_units(
    *,
    input_path: str | Path,
    pages: str | None = None,
    document_id: str = "kkb-2024",
    extractor: PyMuPDF4LLMExtractor | None = None,
    layout_profile: str | Path | CheckpointLayoutProfile | None = None,
) -> CanonicalExtraction:
    """Produce canonical units in memory without writing any file.

    This is the shared body of :func:`prepare_checkpoint`; callers that only
    need units (for example an application ingestion path) use this directly so
    there is exactly one canonical extraction implementation.
    """
    if isinstance(layout_profile, CheckpointLayoutProfile):
        resolved_profile = layout_profile
    elif layout_profile is not None:
        resolved_profile = load_checkpoint_layout_profile(layout_profile)
    else:
        resolved_profile = None
    extraction = (
        extractor
        or PyMuPDF4LLMExtractor(layout_profile=resolved_profile)
    ).extract(
        input_path, pages=pages
    )
    if (
        extractor is not None
        and resolved_profile is not None
        and extraction.layout_profile != resolved_profile
    ):
        raise ValueError(
            "Injected checkpoint extractor did not report the requested "
            "layout profile; refusing to write misleading order provenance"
        )
    active_profile = extraction.layout_profile or resolved_profile
    parser = MarkdownAtomicUnitParser()
    blocks: list[AtomicBlock] = []
    next_block_by_physical_page: dict[int, int] = {}
    for page in extraction.pages:
        block_start = next_block_by_physical_page.get(page.page, 1)
        page_blocks = parser.parse_page(page, block_start=block_start)
        blocks.extend(page_blocks)
        next_block_by_physical_page[page.page] = block_start + len(page_blocks)
    if not blocks:
        raise ValueError("Selected PDF pages produced no canonical atomic units")
    canonical_blocks = [
        block
        for block in blocks
        if not (
            block.content_origin == "visual"
            and block.has_extracted_picture_text is False
        )
    ]
    if not canonical_blocks:
        raise ValueError("Selected PDF pages produced no canonical semantic units")
    units = SectionHierarchyBuilder().build(
        canonical_blocks,
        document_id=document_id,
    )
    return CanonicalExtraction(
        units=tuple(units),
        blocks=tuple(blocks),
        selected_pages=extraction.selected_pages,
        pymupdf4llm_version=extraction.pymupdf4llm_version,
        picture_count=sum(block.content_origin == "visual" for block in blocks),
        layout_profile=active_profile,
    )


def prepare_checkpoint(
    *,
    input_path: str | Path,
    output_path: str | Path,
    pages: str | None = None,
    document_id: str = "kkb-2024",
    extractor: PyMuPDF4LLMExtractor | None = None,
    layout_profile: str | Path | CheckpointLayoutProfile | None = None,
) -> PreparationResult:
    extracted = extract_canonical_units(
        input_path=input_path,
        pages=pages,
        document_id=document_id,
        extractor=extractor,
        layout_profile=layout_profile,
    )
    units = list(extracted.units)
    blocks = list(extracted.blocks)
    active_profile = extracted.layout_profile
    CanonicalUnitWriter().write(units, output_path)
    visual_provenance_path = VisualProvenanceWriter().write(
        canonical_path=output_path,
        blocks=blocks,
        units=units,
        document_id=document_id,
    )
    manifest_path = ExtractionManifestWriter().write(
        canonical_path=output_path,
        source_pdf=input_path,
        document_id=document_id,
        selected_pages=extracted.selected_pages,
        pymupdf4llm_version=extracted.pymupdf4llm_version,
        visual_provenance_path=visual_provenance_path,
        layout_profile=active_profile,
    )
    return PreparationResult(
        units=tuple(units),
        manifest_path=manifest_path,
        visual_provenance_path=visual_provenance_path,
        selected_pages=extracted.selected_pages,
        pymupdf4llm_version=extracted.pymupdf4llm_version,
        picture_count=extracted.picture_count,
        visual_atomic_unit_count=sum(
            getattr(unit.source, "content_origin", None) == "visual"
            for unit in units
        ),
        layout_profile=active_profile,
    )


def unit_type_counts(units: Sequence[RawDocumentUnit]) -> dict[str, int]:
    return {
        unit_type.value: sum(unit.type == unit_type for unit in units)
        for unit_type in UnitType
    }
