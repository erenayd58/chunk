from __future__ import annotations

from amsc.config import TokenLimitsConfig, V4SelectionConfig
from amsc.models import (
    AdaptiveThresholdProvenance,
    BoundaryEvidence,
    ContentUnit,
    SourceSpan,
    StructuralBoundaryProvenance,
    UnitType,
)
from amsc.selection import V2TailResolver
from amsc.strength import (
    EffectiveThresholdRelativeSelectionScorer,
    RawSemanticShiftSelectionScorer,
)
from amsc.units import RenderedTokenBudgeter
from amsc.v4_selection import V4IntervalBoundarySelector
from conftest import WordTokenCounter


def _unit(index: int) -> ContentUnit:
    return ContentUnit(
        document_id="doc",
        unit_id=f"p-{index}",
        source_unit_id=f"p-{index}",
        order=index,
        text=f"word {index}",
        type=UnitType.PARAGRAPH,
        section_path=(),
        source=SourceSpan(page=1, block=index),
    )


def _boundary(
    index: int,
    shift: float,
    strength: float,
    *,
    candidate: bool = True,
    structural_candidate: bool | None = None,
) -> BoundaryEvidence:
    structural = None
    if structural_candidate is not None:
        structural = StructuralBoundaryProvenance(
            provider_id="test",
            evidence_types=["heading_presence"],
            heading_unit_ids=["h-1"],
            heading_levels=[2],
            original_adaptive_threshold=0.40,
            effective_threshold=0.36,
            configured_max_relaxation=0.04,
            applied_relaxation=0.04,
            semantic_floor=0.12,
            original_semantic_candidate=candidate,
            effective_semantic_candidate=structural_candidate,
            structural_assisted_candidate=(
                not candidate and structural_candidate
            ),
            boundary_candidate=structural_candidate,
            adaptive_degenerate=False,
        )
    return BoundaryEvidence(
        boundary_index=index,
        left_unit_id=f"p-{index}",
        right_unit_id=f"p-{index + 1}",
        cosine_similarity=1.0 - 2.0 * shift,
        semantic_shift=shift,
        adaptive_threshold=AdaptiveThresholdProvenance(
            value=0.20,
            scope=[],
            threshold_scope_kind="document",
            sample_count=10,
            method="mad_quantile",
            low_confidence=False,
            degenerate=False,
        ),
        semantic_candidate=candidate,
        structural=structural,
        original_boundary_strength=strength,
        effective_boundary_strength=strength,
    )


def _selector(scorer):
    limits = TokenLimitsConfig(
        min_tokens=1,
        target_tokens=4,
        soft_max_tokens=10,
        hard_max_tokens=12,
    )
    budgeter = RenderedTokenBudgeter(WordTokenCounter(), 12)
    return V4IntervalBoundarySelector(
        budgeter=budgeter,
        token_limits=limits,
        selection=V4SelectionConfig(),
        scorer=scorer,
        tail_resolver=V2TailResolver(budgeter, limits),
    )


def test_relative_selector_can_prefer_lower_raw_shift() -> None:
    units = [_unit(index) for index in range(4)]
    boundaries = [
        _boundary(0, 0.50, 0.10),
        _boundary(1, 0.30, 0.40),
        _boundary(2, 0.10, 0.00, candidate=False),
    ]

    relative, _ = _selector(
        EffectiveThresholdRelativeSelectionScorer()
    ).select(units, boundaries)
    raw, _ = _selector(RawSemanticShiftSelectionScorer()).select(
        units, boundaries
    )

    assert relative[0].end_boundary.boundary_index == 1
    assert raw[0].end_boundary.boundary_index == 0
    assert relative[0].end_boundary.selection_strategy == "threshold_relative"
    assert raw[0].end_boundary.selection_strategy == "raw_semantic_shift"


def test_effective_structural_candidate_enters_interval_without_hard_cut() -> None:
    units = [_unit(index) for index in range(3)]
    boundaries = [
        _boundary(
            0,
            0.37,
            0.01,
            candidate=False,
            structural_candidate=True,
        ),
        _boundary(1, 0.10, 0.0, candidate=False),
    ]

    segments, evidence = _selector(
        EffectiveThresholdRelativeSelectionScorer()
    ).select(units, boundaries)

    assert segments[0].end_boundary.boundary_index == 0
    assert segments[0].end_boundary.reason == "adaptive_semantic_boundary"
    assert evidence[0].structural is not None
    assert evidence[0].structural.structural_assisted_candidate is True
