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
from .heading_levels import assign_heading_levels
from .lead_in_headings import demote_lead_ins
from .models import RawDocumentUnit
from .numbered_headings import promote_numbered_headings
from .running_headers import drop_running_headers
from .semantic_roles import assign_semantic_roles
from .sentence_headings import demote_sentence_headings
from .split_headings import rejoin_hyphenated_headings, rejoin_split_headings
from .table_captions import demote_table_captions


@dataclass(frozen=True)
class FullCheckpointResult:
    preparation: PreparationResult
    physical_page_count: int
    portrait_single_pages: tuple[int, ...]
    landscape_spread_pages: tuple[int, ...]
    canonical_sha256: str
    canonical_profile: str = "v1-frozen"


#: The canonical repairs applied by ``--canonical-profile v2-repaired``.
#:
#: Running-header removal is deliberately **not** in this set. On kkb-2024 the
#: pass removes 42 furniture headings but also deletes every occurrence of two
#: genuine numbered chapter titles, because those are printed as a banner on
#: each page of their own chapter. Losing a chapter title is a worse defect
#: than keeping the banners, so the pass stays off and the banners stay a
#: recorded limitation.
V2_CANONICAL_REPAIRS: dict[str, bool] = {
    "reconstruct_visual_grids": True,
    "demote_lead_in_headings": True,
    "promote_missed_headings": True,
    "demote_caption_headings": True,
    "rejoin_split_headings_enabled": True,
    "rejoin_hyphenated_headings_enabled": True,
    "demote_sentence_headings_enabled": True,
    "assign_typographic_heading_levels": True,
}

#: ``v3-semantic`` adds the heading/section split: every repair in v2, plus
#: semantic roles, so ``section_path`` changes only at a heading that actually
#: bears hierarchy. Kept as its own profile rather than folded into v2 so the
#: two remain measurable against each other.
V3_CANONICAL_REPAIRS: dict[str, bool] = {
    **V2_CANONICAL_REPAIRS,
    "assign_semantic_heading_roles": True,
}

CANONICAL_PROFILES: dict[str, dict[str, bool]] = {
    "v1-frozen": {},
    "v2-repaired": V2_CANONICAL_REPAIRS,
    "v3-semantic": V3_CANONICAL_REPAIRS,
}


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
    demote_caption_headings: bool = False,
    rejoin_split_headings_enabled: bool = False,
    rejoin_hyphenated_headings_enabled: bool = False,
    demote_sentence_headings_enabled: bool = False,
    assign_typographic_heading_levels: bool = False,
    assign_semantic_heading_roles: bool = False,
) -> CanonicalExtraction:
    """Produce mixed-orientation canonical units in memory, writing no file.

    This is the shared body of :func:`prepare_full_checkpoint`.  Unlike that
    function the layout profile is optional: when it is omitted the frozen
    extractor's own reading order is kept for spread pages.  Portrait-only
    documents are unaffected either way because
    :func:`apply_profile_to_spread_logical_pages` skips ``single`` pages.

    Every canonical repair -- ``reconstruct_visual_grids``,
    ``demote_lead_in_headings``, ``promote_missed_headings``,
    ``demote_caption_headings``, ``rejoin_split_headings_enabled``,
    ``rejoin_hyphenated_headings_enabled``,
    ``demote_sentence_headings_enabled``, ``assign_typographic_heading_levels``
    and ``assign_semantic_heading_roles`` -- is likewise opt-in and off by
    default, so the frozen research canonical stays byte-identical.
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
        or PyMuPDF4LLMExtractor(
            capture_picture_geometry=reconstruct_visual_grids,
            capture_heading_prominence=(
                assign_typographic_heading_levels or assign_semantic_heading_roles
            ),
        )
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

    if rejoin_hyphenated_headings_enabled:
        # Opt-in: a heading too long for its column wraps mid-word and each
        # printed line arrives as its own heading box, so the chunker is free
        # to cut between ``Da-`` and ``valar``. Rejoining before the
        # side-by-side pass means that pass sees whole titles.
        canonical_blocks, _wrapped = rejoin_hyphenated_headings(canonical_blocks)

    if rejoin_split_headings_enabled:
        # Opt-in: one printed heading line can arrive as two layout boxes, the
        # section number in one and the title in the other. Rejoining them
        # first means every later pass sees whole headings.
        canonical_blocks, _rejoined = rejoin_split_headings(canonical_blocks)

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

    if demote_caption_headings:
        # Opt-in: a period label printed above its table reaches the section
        # state machine as a heading and opens a section named after a table
        # caption. It is recognisable because the layout model also emits it
        # as the table's own leading cell.
        canonical_blocks, _captions = demote_table_captions(canonical_blocks)

    if demote_sentence_headings_enabled:
        # Opt-in: a standfirst set in display type is reported as a section
        # header, so a whole sentence opens a section. Demoting it keeps the
        # units below under the chapter title they belong to.
        canonical_blocks, _sentences = demote_sentence_headings(canonical_blocks)

    if demote_lead_in_headings:
        # Opt-in: a sentence that introduces the bullets under it reaches the
        # section state machine as a heading and detaches those bullets from
        # their own section. Rewriting it as body text before the hierarchy is
        # built is the only point where the attribution can still be correct.
        # Runs after running-header removal so that step still sees the
        # untouched heading stream.
        canonical_blocks, _lead_ins = demote_lead_ins(canonical_blocks)

    if assign_semantic_heading_roles:
        # Opt-in, and before the levels: a level only means something for a
        # heading that bears hierarchy, and which headings those are is exactly
        # what this pass decides. Runs after every demotion above so it never
        # classifies a heading that is about to stop being one.
        canonical_blocks, _roles = assign_semantic_roles(canonical_blocks)

    if assign_typographic_heading_levels:
        # Opt-in, and deliberately last: every pass above adds, removes or
        # demotes headings, and a level is only meaningful once the heading
        # stream is final. Levels stay relative to the document's own
        # shallowest heading, so a corpus with one typographic tier comes out
        # exactly as it went in.
        canonical_blocks, _levels = assign_heading_levels(canonical_blocks)

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
    canonical_profile: str = "v1-frozen",
) -> FullCheckpointResult:
    if canonical_profile not in CANONICAL_PROFILES:
        raise ValueError(
            f"Unknown canonical profile {canonical_profile!r}; "
            f"expected one of {sorted(CANONICAL_PROFILES)}"
        )
    extracted = extract_full_canonical_units(
        input_path=input_path,
        layout_profile_path=layout_profile_path,
        document_id=document_id,
        extractor=extractor,
        **CANONICAL_PROFILES[canonical_profile],
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
        canonical_path=output_path,
        portrait_pages=portrait_pages,
        landscape_pages=landscape_pages,
        canonical_profile=canonical_profile,
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
        canonical_profile=canonical_profile,
    )


def _record_full_document_profile_application(
    manifest_path: Path,
    *,
    canonical_path: Path,
    portrait_pages: Sequence[int],
    landscape_pages: Sequence[int],
    canonical_profile: str = "v1-frozen",
) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    # The manifest names the PDF it came from and pins its sha; without the
    # same pin on its own output, a canonical and its manifest can drift apart
    # silently -- and every benchmark config downstream pins a sha the manifest
    # could not confirm. ``units_sha256`` closes that loop.
    #
    # Only for a repaired profile. ``v1-frozen`` is the historical baseline and
    # its checked-in manifest predates both this field and ``canonical_profile``;
    # writing them would make a regenerated v1 manifest differ from the frozen
    # one for no gain, since the v1 canonical is pinned by its ``.sha256``
    # sidecar and by the configs that consume it. Each profile keeps its own
    # manifest contract rather than one schema being retrofitted onto all three.
    if CANONICAL_PROFILES[canonical_profile]:
        payload["units_file"] = canonical_path.name
        payload["units_sha256"] = sha256_file(canonical_path)
    payload["extraction_parameters"]["spread_detection"] = (
        "frozen_extractor_physical_page_width_gt_height"
    )
    # Which repairs produced this canonical is provenance, not configuration:
    # two files extracted from the same PDF are only comparable when both say
    # so. ``v1-frozen`` records the empty set explicitly rather than by
    # omission.
    payload["canonical_profile"] = {
        "profile_id": canonical_profile,
        "repairs": dict(sorted(CANONICAL_PROFILES[canonical_profile].items())),
    }
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
    parser.add_argument(
        "--canonical-profile",
        default="v1-frozen",
        choices=sorted(CANONICAL_PROFILES),
        help=(
            "v1-frozen reproduces the checked-in research canonical byte for "
            "byte; v2-repaired applies the audited canonical repairs"
        ),
    )
    parser.add_argument("--document-id", default="kkb-2024")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = prepare_full_checkpoint(
        input_path=args.input,
        output_path=args.output,
        layout_profile_path=args.layout_profile,
        document_id=args.document_id,
        canonical_profile=args.canonical_profile,
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
                "canonical_profile": result.canonical_profile,
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
