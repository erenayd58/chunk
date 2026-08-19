from __future__ import annotations

from dataclasses import replace
import math

import numpy as np
import pytest

from amsc.config import SemanticSafeMergeConfig, TokenLimitsConfig
from amsc.merge import SemanticSafeMergeResolver, V4ChunkDraft, _Proposal
from amsc.models import (
    AdaptiveThresholdProvenance,
    BoundaryEvidence,
    ChunkBoundary,
    ContentUnit,
    SourceSpan,
    StructuralBoundaryProvenance,
    UnitType,
)
from amsc.units import RenderedTokenBudgeter
from conftest import WordTokenCounter


def _unit(
    index: int,
    words: int,
    *,
    section: tuple[str, ...] = (),
) -> ContentUnit:
    return ContentUnit(
        document_id="doc",
        unit_id=f"p-{index}",
        source_unit_id=f"p-{index}",
        order=index,
        text=" ".join(f"w{index}-{word}" for word in range(words)),
        type=UnitType.PARAGRAPH,
        section_path=section,
        source=SourceSpan(page=1, block=index + 1),
    )


def _adaptive(value: float = 0.20) -> AdaptiveThresholdProvenance:
    return AdaptiveThresholdProvenance(
        value=value,
        scope=[],
        threshold_scope_kind="document",
        sample_count=20,
        method="mad_quantile",
        low_confidence=False,
        degenerate=False,
    )


def _structural() -> StructuralBoundaryProvenance:
    return StructuralBoundaryProvenance(
        provider_id="test",
        evidence_types=["heading_presence"],
        heading_unit_ids=["h-1"],
        heading_levels=[2],
        original_adaptive_threshold=0.20,
        effective_threshold=0.12,
        configured_max_relaxation=0.08,
        applied_relaxation=0.08,
        semantic_floor=0.12,
        original_semantic_candidate=False,
        effective_semantic_candidate=True,
        structural_assisted_candidate=True,
        boundary_candidate=True,
        adaptive_degenerate=False,
    )


def _boundary(
    index: int,
    *,
    strength: float = 0.0,
    structural: bool = False,
    reason: str = "size_fallback",
) -> tuple[BoundaryEvidence, ChunkBoundary]:
    evidence = BoundaryEvidence(
        boundary_index=index,
        left_unit_id=f"p-{index}",
        right_unit_id=f"p-{index + 1}",
        cosine_similarity=0.70,
        semantic_shift=0.15,
        adaptive_threshold=_adaptive(),
        semantic_candidate=False,
        structural=_structural() if structural else None,
        original_boundary_strength=strength,
        effective_boundary_strength=0.04 if structural else strength,
        selected_reason=reason,
    )
    chunk_boundary = ChunkBoundary(
        reason=reason,
        boundary_index=index,
        left_unit_id=evidence.left_unit_id,
        right_unit_id=evidence.right_unit_id,
        cosine_similarity=evidence.cosine_similarity,
        semantic_shift=evidence.semantic_shift,
        adaptive_threshold=evidence.adaptive_threshold,
        semantic_candidate=evidence.semantic_candidate,
        structural=evidence.structural,
        original_boundary_strength=strength,
        effective_boundary_strength=evidence.effective_boundary_strength,
    )
    return evidence, chunk_boundary


def _resolver(
    *, hard_max: int = 15, small_chunk_threshold: int | None = None
) -> SemanticSafeMergeResolver:
    counter = WordTokenCounter()
    limits = TokenLimitsConfig(
        min_tokens=3,
        target_tokens=8,
        soft_max_tokens=12,
        hard_max_tokens=hard_max,
    )
    budgeter = RenderedTokenBudgeter(counter, hard_max)
    return SemanticSafeMergeResolver(
        config=SemanticSafeMergeConfig(
            small_chunk_threshold=small_chunk_threshold
        ),
        token_limits=limits,
        token_counter=counter,
        budgeter=budgeter,
    )


def _two_drafts(
    *,
    left_words: int = 4,
    right_words: int = 1,
    strength: float = 0.0,
    structural: bool = False,
    left_section: tuple[str, ...] = (),
    right_section: tuple[str, ...] = (),
):
    left = _unit(0, left_words, section=left_section)
    right = _unit(1, right_words, section=right_section)
    evidence, chunk_boundary = _boundary(
        0, strength=strength, structural=structural
    )
    drafts = [
        V4ChunkDraft([left], chunk_boundary, (0,)),
        V4ChunkDraft(
            [right], ChunkBoundary(reason="document_end"), (1,)
        ),
    ]
    return drafts, [evidence], left, right


def test_merge_cohesion_uses_original_not_effective_threshold() -> None:
    drafts, boundaries, left, right = _two_drafts(structural=True)
    # cosine=0.70 -> pair_shift=0.15: below original 0.20 but above
    # structure-relaxed effective threshold 0.12.
    vectors = {
        left.unit_id: np.asarray([1.0, 0.0]),
        right.unit_id: np.asarray([0.70, math.sqrt(0.51)]),
    }

    merged, updated = _resolver().resolve(drafts, boundaries, vectors)

    assert len(merged) == 1
    assert merged[0].accepted_merge is not None
    assert merged[0].accepted_merge.pair_shift == pytest.approx(0.15)
    assert merged[0].accepted_merge.original_adaptive_threshold == 0.20
    assert updated[0].selected_reason == "removed_by_v4_semantic_safe_merge"


def test_original_high_confidence_strength_blocks_merge() -> None:
    drafts, boundaries, left, right = _two_drafts(strength=0.50)
    vectors = {
        left.unit_id: np.asarray([1.0, 0.0]),
        right.unit_id: np.asarray([1.0, 0.0]),
    }

    merged, updated = _resolver().resolve(drafts, boundaries, vectors)

    assert len(merged) == 2
    decision = updated[0].merge_decisions[0]  # type: ignore[index]
    assert decision.rejection_reason == "original_boundary_high_confidence"


def test_structure_mismatch_is_reported_but_never_a_veto() -> None:
    drafts, boundaries, left, right = _two_drafts(
        left_section=("A",), right_section=("B",)
    )
    vectors = {
        left.unit_id: np.asarray([1.0, 0.0]),
        right.unit_id: np.asarray([1.0, 0.0]),
    }

    merged, updated = _resolver().resolve(drafts, boundaries, vectors)

    assert len(merged) == 1
    decision = updated[0].merge_decisions[0]  # type: ignore[index]
    assert decision.structural_compatibility is False
    assert decision.accepted is True


def test_hard_cap_rejects_otherwise_cohesive_merge() -> None:
    drafts, boundaries, left, right = _two_drafts(
        left_words=8, right_words=8
    )
    vectors = {
        left.unit_id: np.asarray([1.0, 0.0]),
        right.unit_id: np.asarray([1.0, 0.0]),
    }

    merged, updated = _resolver(
        hard_max=15, small_chunk_threshold=10
    ).resolve(
        drafts, boundaries, vectors
    )

    assert len(merged) == 2
    reasons = {
        decision.rejection_reason
        for decision in updated[0].merge_decisions or []
    }
    assert "combined_hard_cap_exceeded" in reasons


def test_original_hard_limit_fallback_is_never_merge_eligible() -> None:
    left = _unit(0, 4)
    right = _unit(1, 1)
    evidence, chunk_boundary = _boundary(
        0,
        reason="hard_limit_fallback",
    )
    drafts = [
        V4ChunkDraft([left], chunk_boundary, (0,)),
        V4ChunkDraft(
            [right], ChunkBoundary(reason="document_end"), (1,)
        ),
    ]
    vectors = {
        left.unit_id: np.asarray([1.0, 0.0]),
        right.unit_id: np.asarray([1.0, 0.0]),
    }

    merged, updated = _resolver().resolve(drafts, [evidence], vectors)

    assert len(merged) == 2
    decision = updated[0].merge_decisions[0]  # type: ignore[index]
    assert decision.rejection_reason == (
        "original_boundary_hard_limit_fallback"
    )
    assert decision.pair_shift is None
    assert decision.combined_token_count is None
    assert decision.accepted is False


def test_single_pass_never_chains_or_overlaps_merges() -> None:
    units = [_unit(index, 1) for index in range(3)]
    evidence_0, chunk_boundary_0 = _boundary(0)
    evidence_1, chunk_boundary_1 = _boundary(1)
    drafts = [
        V4ChunkDraft([units[0]], chunk_boundary_0, (0,)),
        V4ChunkDraft([units[1]], chunk_boundary_1, (1,)),
        V4ChunkDraft([units[2]], ChunkBoundary(reason="document_end"), (2,)),
    ]
    vectors = {unit.unit_id: np.asarray([1.0, 0.0]) for unit in units}

    merged, updated = _resolver().resolve(
        drafts, [evidence_0, evidence_1], vectors
    )

    assert len(merged) == 2
    assert sum(draft.accepted_merge is not None for draft in merged) == 1
    decisions = [
        decision
        for boundary in updated
        for decision in boundary.merge_decisions or []
    ]
    assert sum(decision.accepted for decision in decisions) == 1
    assert any(
        decision.rejection_reason == "overlapping_proposal_conflict"
        for decision in decisions
    )


def test_proposal_rank_matches_frozen_criterion_order() -> None:
    resolver = _resolver()
    base = _Proposal(
        proposal_id="base",
        focus_index=5,
        left_index=4,
        right_index=5,
        direction="left",
        boundary_index=4,
        boundary_original_reason="size_fallback",
        original_boundary_strength=0.20,
        pair_shift=0.10,
        original_adaptive_threshold=0.20,
        semantic_cohesion_passed=True,
        combined_token_count=8,
        hard_cap_passed=True,
        structural_compatibility=False,
        rejection_reason=None,
    )
    rank = resolver._proposal_rank

    # Higher absolute cohesion margin wins before every later criterion.
    assert rank(
        replace(
            base,
            proposal_id="higher-margin",
            pair_shift=0.05,
            original_boundary_strength=0.49,
        )
    ) < rank(
        replace(
            base,
            proposal_id="lower-margin",
            pair_shift=0.10,
            original_boundary_strength=0.00,
        )
    )
    # With equal margin, lower original boundary strength wins.
    assert rank(
        replace(base, proposal_id="lower-strength", original_boundary_strength=0.10)
    ) < rank(
        replace(base, proposal_id="higher-strength", original_boundary_strength=0.20)
    )
    # Target distance precedes original focus index.
    assert rank(
        replace(base, proposal_id="on-target", combined_token_count=8, focus_index=9)
    ) < rank(
        replace(base, proposal_id="off-target", combined_token_count=4, focus_index=1)
    )
    # Lower original focus index precedes direction and structure.
    assert rank(
        replace(
            base,
            proposal_id="earlier-focus",
            focus_index=1,
            direction="right",
            structural_compatibility=False,
        )
    ) < rank(
        replace(
            base,
            proposal_id="later-focus",
            focus_index=2,
            direction="left",
            structural_compatibility=True,
        )
    )
    # Left direction precedes structural compatibility; structure is last.
    assert rank(
        replace(
            base,
            proposal_id="left-mismatch",
            direction="left",
            structural_compatibility=False,
        )
    ) < rank(
        replace(
            base,
            proposal_id="right-compatible",
            direction="right",
            structural_compatibility=True,
        )
    )
    assert rank(
        replace(base, proposal_id="compatible", structural_compatibility=True)
    ) < rank(
        replace(base, proposal_id="mismatch", structural_compatibility=False)
    )
