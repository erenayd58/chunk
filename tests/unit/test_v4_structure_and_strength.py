from __future__ import annotations

import pytest

from amsc.config import SoftStructureConfig
from amsc.models import (
    AdaptiveThresholdProvenance,
    BoundaryEvidence,
    ContentUnit,
    HeadingAttachment,
    SourceSpan,
    UnitType,
)
from amsc.strength import (
    DualBoundaryStrengthAnnotator,
    ThresholdRelativeBoundaryStrengthScorer,
)
from amsc.structure import SoftStructureSupportPolicy


def _unit(
    unit_id: str,
    *,
    unit_type: UnitType = UnitType.PARAGRAPH,
    section_path: tuple[str, ...] = (),
    headings: tuple[HeadingAttachment, ...] = (),
    visual: bool = False,
) -> ContentUnit:
    source = SourceSpan(page=1, block=1)
    if visual:
        source = SourceSpan.model_validate(
            {"page": 1, "block": 1, "content_origin": "visual"}
        )
    return ContentUnit(
        document_id="doc",
        unit_id=unit_id,
        source_unit_id=unit_id,
        order=1,
        text=unit_id,
        type=unit_type,
        section_path=section_path,
        source=source,
        leading_headings=headings,
    )


def _boundary(
    shift: float,
    *,
    threshold: float = 0.27,
    candidate: bool | None = None,
    degenerate: bool = False,
) -> BoundaryEvidence:
    if candidate is None:
        candidate = not degenerate and shift >= threshold
    return BoundaryEvidence(
        boundary_index=0,
        left_unit_id="left",
        right_unit_id="right",
        cosine_similarity=1.0 - 2.0 * shift,
        semantic_shift=shift,
        adaptive_threshold=AdaptiveThresholdProvenance(
            value=threshold,
            scope=[],
            threshold_scope_kind="document",
            sample_count=20,
            method="mad_quantile",
            low_confidence=False,
            degenerate=degenerate,
        ),
        semantic_candidate=candidate,
    )


def _heading() -> HeadingAttachment:
    return HeadingAttachment(
        unit_id="h-1",
        text="Visual heading",
        heading_level=2,
        source=SourceSpan(page=1, block=2),
    )


def test_heading_is_bounded_support_not_a_hard_boundary() -> None:
    left = _unit("left", section_path=("Root",))
    right = _unit(
        "right", section_path=("Root", "Child"), headings=(_heading(),)
    )
    result = SoftStructureSupportPolicy(SoftStructureConfig()).apply(
        [_boundary(0.08)], {"left": left, "right": right}
    )[0]

    assert result.semantic_candidate is False
    assert result.structural is not None
    assert result.structural.effective_threshold == pytest.approx(0.23)
    assert result.structural.effective_semantic_candidate is False
    assert result.structural.boundary_candidate is False
    assert result.structural.heading_unit_ids == ["h-1"]


def test_soft_structure_can_promote_near_threshold_semantics() -> None:
    left = _unit("left", section_path=("Root",))
    right = _unit("right", section_path=("Other",), headings=(_heading(),))
    result = SoftStructureSupportPolicy(SoftStructureConfig()).apply(
        [_boundary(0.25)], {"left": left, "right": right}
    )[0]

    assert result.semantic_candidate is False
    assert result.structural is not None
    assert result.structural.effective_semantic_candidate is True
    assert result.structural.structural_assisted_candidate is True
    assert result.structural.boundary_candidate is True


def test_floor_never_raises_a_low_original_threshold() -> None:
    left = _unit("left", section_path=("A",))
    right = _unit("right", section_path=("B",))
    result = SoftStructureSupportPolicy(SoftStructureConfig()).apply(
        [_boundary(0.09, threshold=0.10)], {"left": left, "right": right}
    )[0]

    assert result.structural is not None
    assert result.structural.effective_threshold == pytest.approx(0.10)
    assert result.structural.applied_relaxation == pytest.approx(0.0)


def test_degenerate_threshold_cannot_be_promoted_by_structure() -> None:
    left = _unit("left")
    right = _unit("right", headings=(_heading(),))
    result = SoftStructureSupportPolicy(SoftStructureConfig()).apply(
        [_boundary(0.30, degenerate=True)], {"left": left, "right": right}
    )[0]

    assert result.structural is not None
    assert result.structural.effective_threshold == pytest.approx(0.27)
    assert result.structural.boundary_candidate is False


def test_visual_transition_is_parser_agnostic_structural_evidence() -> None:
    left = _unit("left")
    right = _unit("right", visual=True)
    result = SoftStructureSupportPolicy(SoftStructureConfig()).apply(
        [_boundary(0.25)], {"left": left, "right": right}
    )[0]

    assert result.structural is not None
    assert result.structural.evidence_types == ["visual_transition"]


def test_original_and_effective_strength_are_separate() -> None:
    left = _unit("left")
    right = _unit("right", headings=(_heading(),))
    structured = SoftStructureSupportPolicy(SoftStructureConfig()).apply(
        [_boundary(0.25)], {"left": left, "right": right}
    )
    result = DualBoundaryStrengthAnnotator(epsilon=1.0e-8).apply(structured)[0]

    assert result.original_boundary_strength == 0.0
    assert result.effective_boundary_strength == pytest.approx(
        (0.25 - 0.23) / (1.0 - 0.23)
    )


def test_near_one_threshold_strength_avoids_division_by_zero() -> None:
    boundary = _boundary(1.0, threshold=1.0, candidate=True)
    scorer = ThresholdRelativeBoundaryStrengthScorer(
        "original", epsilon=1.0e-8
    )

    assert scorer.score(boundary) == 1.0
