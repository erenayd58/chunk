from __future__ import annotations

import numpy as np

from amsc.config import SelectionConfig, SemanticConfig, TokenLimitsConfig
from amsc.features import AdjacentSemanticFeatureExtractor
from amsc.models import (
    AdaptiveThresholdProvenance,
    BoundaryEvidence,
    ChunkBoundary,
    ContentUnit,
    EmbeddingBatch,
    SelectedSegment,
    SemanticEmbeddingProvenance,
    SourceSpan,
    UnitType,
)
from amsc.selection import IntervalBoundarySelector, V1TailResolver, V2TailResolver
from amsc.units import RenderedTokenBudgeter
from conftest import WordTokenCounter


def unit(index: int, words: int) -> ContentUnit:
    return ContentUnit(
        document_id="d",
        unit_id=f"u{index}",
        source_unit_id=f"u{index}",
        order=index,
        text=" ".join(f"w{index}_{i}" for i in range(words)),
        type=UnitType.PARAGRAPH,
        section_path=(),
        source=SourceSpan(page=1, block=index),
        semantic_text=f"u{index}",
    )


def evidence(index: int, shift: float, threshold: float = 0.2):
    return BoundaryEvidence(
        boundary_index=index,
        left_unit_id=f"u{index}",
        right_unit_id=f"u{index + 1}",
        cosine_similarity=1 - 2 * shift,
        semantic_shift=shift,
        fixed_threshold=threshold,
        semantic_candidate=shift >= threshold,
    )


def selector(minimum=2, target=6, soft=10, hard=12):
    budgeter = RenderedTokenBudgeter(WordTokenCounter(), hard)
    return IntervalBoundarySelector(
        budgeter=budgeter,
        token_limits=TokenLimitsConfig(
            min_tokens=minimum,
            target_tokens=target,
            soft_max_tokens=soft,
            hard_max_tokens=hard,
        ),
        semantic=SemanticConfig(fixed_threshold=0.2),
        selection=SelectionConfig(semantic_weight=0.8, size_weight=0.2),
    )


def adaptive_provenance(value: float = 0.2) -> AdaptiveThresholdProvenance:
    return AdaptiveThresholdProvenance(
        value=value,
        scope=[],
        threshold_scope_kind="document",
        sample_count=4,
        method="short_document_fixed_fallback",
        low_confidence=True,
        degenerate=False,
    )


def adaptive_evidence(index: int, shift: float, threshold: float = 0.2):
    return BoundaryEvidence(
        boundary_index=index,
        left_unit_id=f"u{index}",
        right_unit_id=f"u{index + 1}",
        cosine_similarity=1 - 2 * shift,
        semantic_shift=shift,
        adaptive_threshold=adaptive_provenance(threshold),
        semantic_candidate=shift >= threshold,
    )


def adaptive_selector(minimum=2, target=6, soft=10, hard=12):
    budgeter = RenderedTokenBudgeter(WordTokenCounter(), hard)
    limits = TokenLimitsConfig(
        min_tokens=minimum,
        target_tokens=target,
        soft_max_tokens=soft,
        hard_max_tokens=hard,
    )
    return IntervalBoundarySelector(
        budgeter=budgeter,
        token_limits=limits,
        semantic=None,
        selection=SelectionConfig(semantic_weight=0.8, size_weight=0.2),
        semantic_boundary_reason="adaptive_semantic_boundary",
        tail_resolver=V2TailResolver(budgeter, limits),
        removed_tail_selected_reason="removed_by_v2_tail_coalescing",
    )


def test_adjacent_cosine_shift() -> None:
    units = [unit(0, 2), unit(1, 2)]
    provenance = SemanticEmbeddingProvenance(
        model_id="m",
        prefix_policy="symmetric_query",
        prefix="query: ",
        model_input_limit=512,
        semantic_fragment_count=1,
        semantic_pooling="token_weighted_mean",
    )
    batch = EmbeddingBatch(
        vectors=np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        provenance=(provenance, provenance),
    )
    result = AdjacentSemanticFeatureExtractor(0.2).compute(units, batch)
    assert result[0].cosine_similarity == 0.0
    assert result[0].semantic_shift == 0.5
    assert result[0].semantic_candidate is True


def test_interval_does_not_choose_first_threshold_crossing() -> None:
    units = [unit(i, 2) for i in range(5)]
    boundaries = [
        evidence(0, 0.21),
        evidence(1, 0.22),
        evidence(2, 0.45),
        evidence(3, 0.10),
    ]
    segments, updated = selector().select(units, boundaries)
    assert segments[0].end == 3
    assert updated[2].selected_reason == "fixed_semantic_boundary"


def test_target_distance_breaks_equal_semantic_score() -> None:
    units = [unit(i, 2) for i in range(5)]
    boundaries = [
        evidence(0, 0.3),
        evidence(1, 0.3),
        evidence(2, 0.3),
        evidence(3, 0.1),
    ]
    segments, _ = selector().select(units, boundaries)
    assert segments[0].end == 3  # six tokens, exactly target


def test_size_fallback_when_no_semantic_candidate() -> None:
    units = [unit(i, 3) for i in range(5)]
    boundaries = [evidence(i, 0.1) for i in range(4)]
    segments, _ = selector(minimum=2, target=6, soft=9, hard=12).select(
        units, boundaries
    )
    assert segments[0].end_boundary.reason == "size_fallback"


def test_tail_resolver_preserves_semantic_boundary() -> None:
    units = [unit(0, 5), unit(1, 1)]
    selected, _ = selector(minimum=2, target=4, soft=6, hard=8).select(
        units, [evidence(0, 0.4)]
    )
    assert len(selected) == 2
    assert selected[-1].unmerged_short_tail_reason == (
        "preceding_boundary_is_not_fallback"
    )


def test_tail_resolver_removes_only_nonsemantic_fallback() -> None:
    units = [unit(0, 4), unit(1, 1)]
    budgeter = RenderedTokenBudgeter(WordTokenCounter(), 8)
    boundary = evidence(0, 0.1)
    from amsc.models import ChunkBoundary, SelectedSegment

    segments = [
        SelectedSegment(
            0,
            1,
            ChunkBoundary(
                reason="size_fallback",
                semantic_shift=boundary.semantic_shift,
                fixed_threshold=0.2,
            ),
        ),
        SelectedSegment(1, 2, ChunkBoundary(reason="document_end")),
    ]
    resolved = V1TailResolver(
        budgeter,
        TokenLimitsConfig(
            min_tokens=2, target_tokens=4, soft_max_tokens=6, hard_max_tokens=8
        ),
        fixed_threshold=0.2,
    ).resolve(units, segments)
    assert len(resolved) == 1
    assert resolved[0].tail_coalesced is True


def test_v2_selector_keeps_raw_semantic_shift_scoring() -> None:
    units = [unit(i, 2) for i in range(5)]
    boundaries = [
        adaptive_evidence(0, 0.21),
        adaptive_evidence(1, 0.22),
        adaptive_evidence(2, 0.45),
        adaptive_evidence(3, 0.10),
    ]
    segments, updated = adaptive_selector().select(units, boundaries)
    assert segments[0].end == 3
    assert segments[0].end_boundary.reason == "adaptive_semantic_boundary"
    assert updated[2].selection_score == 0.8 * 0.45 + 0.2


def test_v2_tail_preserves_adaptive_semantic_boundary() -> None:
    units = [unit(0, 5), unit(1, 1)]
    selected, _ = adaptive_selector(minimum=2, target=4, soft=6, hard=8).select(
        units, [adaptive_evidence(0, 0.4)]
    )
    assert len(selected) == 2
    assert selected[-1].unmerged_short_tail_reason == (
        "preceding_boundary_is_not_fallback"
    )


def test_v2_tail_merges_only_nonsemantic_fallback() -> None:
    units = [unit(0, 4), unit(1, 1)]
    budgeter = RenderedTokenBudgeter(WordTokenCounter(), 8)
    limits = TokenLimitsConfig(
        min_tokens=2, target_tokens=4, soft_max_tokens=6, hard_max_tokens=8
    )
    segments = [
        SelectedSegment(
            0,
            1,
            ChunkBoundary(
                reason="size_fallback",
                semantic_shift=0.1,
                adaptive_threshold=adaptive_provenance(),
                semantic_candidate=False,
            ),
        ),
        SelectedSegment(1, 2, ChunkBoundary(reason="document_end")),
    ]
    resolved = V2TailResolver(budgeter, limits).resolve(units, segments)
    assert len(resolved) == 1
    assert resolved[0].tail_coalesced is True


def test_v2_tail_does_not_remove_semantic_fallback_boundary() -> None:
    units = [unit(0, 4), unit(1, 1)]
    budgeter = RenderedTokenBudgeter(WordTokenCounter(), 8)
    limits = TokenLimitsConfig(
        min_tokens=2, target_tokens=4, soft_max_tokens=6, hard_max_tokens=8
    )
    segments = [
        SelectedSegment(
            0,
            1,
            ChunkBoundary(
                reason="hard_limit_fallback",
                semantic_shift=0.4,
                adaptive_threshold=adaptive_provenance(),
                semantic_candidate=True,
            ),
        ),
        SelectedSegment(1, 2, ChunkBoundary(reason="document_end")),
    ]
    resolved = V2TailResolver(budgeter, limits).resolve(units, segments)
    assert len(resolved) == 2
    assert resolved[-1].unmerged_short_tail_reason == (
        "preceding_boundary_is_semantic"
    )
