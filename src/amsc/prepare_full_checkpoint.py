from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Sequence

from .checkpoint_adapter import (
    AtomicBlock,
    CanonicalExtraction,
    CanonicalUnitWriter,
    ExtractionManifestWriter,
    ExtractionResult,
    MarkdownAtomicUnitParser,
    PreparationResult,
    PyMuPDF4LLMExtractor,
    SectionHierarchyBuilder,
    VisualProvenanceWriter,
    sha256_file,
    unit_type_counts,
)
from .checkpoint_layout import (
    CheckpointLayoutProfile,
    ExplicitLogicalPageColumnOrderer,
    load_checkpoint_layout_profile,
)
from .lead_in_headings import demote_lead_ins
from .models import RawDocumentUnit
from .numbered_headings import promote_numbered_headings
from .running_headers import drop_running_headers


@dataclass(frozen=True)
class FullCheckpointResult:
    preparation: PreparationResult
    physical_page_count: int
    portrait_single_pages: tuple[int, ...]
    landscape_spread_pages: tuple[int, ...]
    canonical_sha256: str


def apply_profile_to_spread_logical_pages(
    extraction: ExtractionResult,
    profile: CheckpointLayoutProfile,
) -> ExtractionResult:
    """Apply explicit column order only to already split logical pages.

    The frozen extractor remains responsible for orientation handling:
    portrait physical pages stay ``single`` and landscape physical pages are
    emitted as ``left`` then ``right``. This Phase-1 orchestration only orders
    the latter's existing layout boxes.
    """

    orderer = ExplicitLogicalPageColumnOrderer(profile)
    pages = []
    for page in extraction.pages:
        if page.logical_page_side == "single":
            pages.append(page)
            continue
        if page.logical_page_width is None:
            raise ValueError(
                "Spread logical page is missing logical_page_width provenance"
            )
        pages.append(
            replace(
                page,
                layout_boxes=orderer.order(
                    page.layout_boxes,
                    logical_page_width=page.logical_page_width,
                ),
            )
        )
    return replace(
        extraction,
        pages=tuple(pages),
        layout_profile=profile,
    )


def extract_full_canonical_units(
    *,
    input_path: str | Path,
    layout_profile_path: str | Path | CheckpointLayoutProfile | None = None,
    document_id: str = "kkb-2024",
    extractor: PyMuPDF4LLMExtractor | None = None,
    running_header_min_pages: int | None = None,
    reconstruct_visual_grids: bool = False,
    demote_lead_in_headings: bool = False,
    promote_missed_headings: bool = False,
) -> CanonicalExtraction:
    """Produce mixed-orientation canonical units in memory, writing no file.

    This is the shared body of :func:`prepare_full_checkpoint`.  Unlike that
    function the layout profile is optional: when it is omitted the frozen
    extractor's own reading order is kept for spread pages.  Portrait-only
    documents are unaffected either way because
    :func:`apply_profile_to_spread_logical_pages` skips ``single`` pages.

    ``reconstruct_visual_grids``, ``demote_lead_in_headings`` and
    ``promote_missed_headings`` are likewise opt-in and off by default, so the
    frozen research canonical stays byte-identical.
    """

    if isinstance(layout_profile_path, CheckpointLayoutProfile):
        profile = layout_profile_path
    elif layout_profile_path is not None:
        profile = load_checkpoint_layout_profile(layout_profile_path)
    else:
        profile = None
    # Opt-in: rebuild label/value pairs inside KPI card grids from page
    # geometry. An explicitly supplied extractor keeps its own configuration.
    extraction = (
        extractor
        or PyMuPDF4LLMExtractor(capture_picture_geometry=reconstruct_visual_grids)
    ).extract(
        input_path,
        pages=None,
    )
    if profile is not None:
        extraction = apply_profile_to_spread_logical_pages(extraction, profile)

    parser = MarkdownAtomicUnitParser()
    blocks: list[AtomicBlock] = []
    next_block_by_physical_page: dict[int, int] = {}
    for page in extraction.pages:
        block_start = next_block_by_physical_page.get(page.page, 1)
        page_blocks = parser.parse_page(page, block_start=block_start)
        blocks.extend(page_blocks)
        next_block_by_physical_page[page.page] = block_start + len(page_blocks)
    if not blocks:
        raise ValueError("Full PDF produced no canonical atomic units")

    canonical_blocks = [
        block
        for block in blocks
        if not (
            block.content_origin == "visual"
            and block.has_extracted_picture_text is False
        )
    ]
    if not canonical_blocks:
        raise ValueError("Full PDF produced no canonical semantic units")

    if promote_missed_headings:
        # Opt-in: the layout model reports a few numbered section titles as
        # body text, so the section they open never starts and their tables
        # keep the previous note's path. Recovering them before the furniture
        # and lead-in passes means those passes see the complete heading
        # stream.
        canonical_blocks, _promoted = promote_numbered_headings(canonical_blocks)

    if running_header_min_pages is not None:
        # Opt-in: a chapter banner repeated at the top of each page reaches the
        # section state machine as a heading and reassigns the paragraph that
        # continues across the page break. Removing it before the hierarchy is
        # built is the only point where the attribution can still be correct.
        canonical_blocks, _furniture = drop_running_headers(
            canonical_blocks, min_pages=running_header_min_pages
        )
        if not canonical_blocks:
            raise ValueError(
                "Running-header removal left no canonical semantic units"
            )

    if demote_lead_in_headings:
        # Opt-in: a sentence that introduces the bullets under it reaches the
        # section state machine as a heading and detaches those bullets from
        # their own section. Rewriting it as body text before the hierarchy is
        # built is the only point where the attribution can still be correct.
        # Runs after running-header removal so that step still sees the
        # untouched heading stream.
        canonical_blocks, _lead_ins = demote_lead_ins(canonical_blocks)

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
        layout_profile=profile,
        page_count=extraction.page_count,
        portrait_single_pages=tuple(
            sorted(
                {
                    page.page
                    for page in extraction.pages
                    if page.logical_page_side == "single"
                }
            )
        ),
        landscape_spread_pages=tuple(
            sorted(
                {
                    page.page
                    for page in extraction.pages
                    if page.logical_page_side in {"left", "right"}
                }
            )
        ),
    )


def prepare_full_checkpoint(
    *,
    input_path: str | Path,
    output_path: str | Path,
    layout_profile_path: str | Path,
    document_id: str = "kkb-2024",
    extractor: PyMuPDF4LLMExtractor | None = None,
) -> FullCheckpointResult:
    extracted = extract_full_canonical_units(
        input_path=input_path,
        layout_profile_path=layout_profile_path,
        document_id=document_id,
        extractor=extractor,
    )
    profile = extracted.layout_profile
    units = list(extracted.units)
    blocks = list(extracted.blocks)

    CanonicalUnitWriter().write(units, output_path)
    visual_path = VisualProvenanceWriter().write(
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
        visual_provenance_path=visual_path,
        layout_profile=profile,
    )

    portrait_pages = extracted.portrait_single_pages
    landscape_pages = extracted.landscape_spread_pages
    _record_full_document_profile_application(
        manifest_path,
        portrait_pages=portrait_pages,
        landscape_pages=landscape_pages,
    )

    preparation = PreparationResult(
        units=tuple(units),
        manifest_path=manifest_path,
        visual_provenance_path=visual_path,
        selected_pages=extracted.selected_pages,
        pymupdf4llm_version=extracted.pymupdf4llm_version,
        picture_count=sum(block.content_origin == "visual" for block in blocks),
        visual_atomic_unit_count=sum(
            getattr(unit.source, "content_origin", None) == "visual"
            for unit in units
        ),
        layout_profile=profile,
    )
    return FullCheckpointResult(
        preparation=preparation,
        physical_page_count=extracted.page_count,
        portrait_single_pages=portrait_pages,
        landscape_spread_pages=landscape_pages,
        canonical_sha256=sha256_file(output_path),
    )


def _record_full_document_profile_application(
    manifest_path: Path,
    *,
    portrait_pages: Sequence[int],
    landscape_pages: Sequence[int],
) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["extraction_parameters"]["spread_detection"] = (
        "frozen_extractor_physical_page_width_gt_height"
    )
    payload["layout_profile_application"] = {
        "landscape_physical_pages": list(landscape_pages),
        "landscape_policy": (
            "left-right spread; two columns per logical page; "
            "column-major-left-to-right"
        ),
        "portrait_physical_pages": list(portrait_pages),
        "portrait_policy": "single logical page; frozen extractor order",
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.prepare_full_checkpoint",
        description=(
            "Prepare the full mixed-orientation KKB Phase-1 checkpoint "
            "without changing the frozen adapter"
        ),
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--layout-profile", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = prepare_full_checkpoint(
        input_path=args.input,
        output_path=args.output,
        layout_profile_path=args.layout_profile,
    )
    units: Sequence[RawDocumentUnit] = result.preparation.units
    counts = unit_type_counts(units)
    sidecar_only = (
        result.preparation.picture_count
        - result.preparation.visual_atomic_unit_count
    )
    print(
        json.dumps(
            {
                "canonical_sha256": result.canonical_sha256,
                "canonical_unit_count": len(units),
                "forced_atomic_split_count": 0,
                "layout_profile": (
                    result.preparation.layout_profile.profile_id
                    if result.preparation.layout_profile is not None
                    else None
                ),
                "physical_page_count": result.physical_page_count,
                "portrait_single_pages": list(result.portrait_single_pages),
                "sidecar_only_visual_count": sidecar_only,
                "status": "ok",
                "unit_counts": counts,
                "visual_unit_count": (
                    result.preparation.visual_atomic_unit_count
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
