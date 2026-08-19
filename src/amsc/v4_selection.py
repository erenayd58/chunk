from __future__ import annotations

from collections.abc import Sequence

from .config import TokenLimitsConfig, V4SelectionConfig
from .models import (
    BoundaryEvidence,
    ChunkBoundary,
    ContentUnit,
    SelectedSegment,
)
from .selection import TailResolver
from .strength import SelectionSignalScorer
from .structure import effective_semantic_candidate
from .units import RenderedTokenBudgeter


class V4IntervalBoundarySelector:
    """V3 interval policy with an injected V4 semantic ranking signal."""

    def __init__(
        self,
        *,
        budgeter: RenderedTokenBudgeter,
        token_limits: TokenLimitsConfig,
        selection: V4SelectionConfig,
        scorer: SelectionSignalScorer,
        tail_resolver: TailResolver,
        semantic_boundary_reason: str = "adaptive_semantic_boundary",
        removed_tail_selected_reason: str = "removed_by_v4_tail_coalescing",
    ) -> None:
        self.budgeter = budgeter
        self.limits = token_limits
        self.selection = selection
        self.scorer = scorer
        self.tail_resolver = tail_resolver
        self.semantic_boundary_reason = semantic_boundary_reason
        self.removed_tail_selected_reason = removed_tail_selected_reason

    def select(
        self,
        units: Sequence[ContentUnit],
        boundaries: Sequence[BoundaryEvidence],
    ) -> tuple[list[SelectedSegment], list[BoundaryEvidence]]:
        if not units:
            return [], list(boundaries)
        if len(boundaries) != max(0, len(units) - 1):
            raise ValueError("Boundary evidence must align with adjacent units")

        evidence = list(boundaries)
        segments: list[SelectedSegment] = []
        start = 0
        while start < len(units):
            remaining_tokens = self.budgeter.count_units(units[start:])
            scored = self._scored_boundaries(units, evidence, start)
            semantic_candidates = [
                item
                for item in scored
                if effective_semantic_candidate(item[1])
            ]

            if semantic_candidates:
                end, selected = self._choose(semantic_candidates)
                reason = self.semantic_boundary_reason
            elif remaining_tokens <= self.limits.soft_max_tokens:
                segments.append(
                    SelectedSegment(
                        start=start,
                        end=len(units),
                        end_boundary=ChunkBoundary(reason="document_end"),
                    )
                )
                break
            elif scored:
                end, selected = self._choose(scored)
                reason = "size_fallback"
            else:
                hard_fallbacks = self._hard_limit_boundaries(
                    units, evidence, start
                )
                if not hard_fallbacks:
                    if remaining_tokens <= self.limits.hard_max_tokens:
                        segments.append(
                            SelectedSegment(
                                start=start,
                                end=len(units),
                                end_boundary=ChunkBoundary(reason="document_end"),
                            )
                        )
                        break
                    raise AssertionError(
                        "No safe boundary exists before configured hard cap"
                    )
                end, selected = self._choose(hard_fallbacks)
                reason = "hard_limit_fallback"

            selected = selected.model_copy(update={"selected_reason": reason})
            evidence[end - 1] = selected
            segments.append(
                SelectedSegment(
                    start=start,
                    end=end,
                    end_boundary=self._as_chunk_boundary(selected, reason),
                    selected_evidence=selected,
                )
            )
            start = end

        selected_before_tail = {
            segment.end_boundary.boundary_index
            for segment in segments
            if segment.end_boundary.boundary_index is not None
        }
        segments = self.tail_resolver.resolve(units, segments)
        selected_after_tail = {
            segment.end_boundary.boundary_index
            for segment in segments
            if segment.end_boundary.boundary_index is not None
        }
        removed = selected_before_tail - selected_after_tail
        for index, item in enumerate(evidence):
            if item.boundary_index in removed:
                evidence[index] = item.model_copy(
                    update={"selected_reason": self.removed_tail_selected_reason}
                )
        return segments, evidence

    def _scored_boundaries(
        self,
        units: Sequence[ContentUnit],
        evidence: Sequence[BoundaryEvidence],
        start: int,
    ) -> list[tuple[int, BoundaryEvidence]]:
        scored: list[tuple[int, BoundaryEvidence]] = []
        for end in range(start + 1, len(units)):
            token_count = self.budgeter.count_units(units[start:end])
            if token_count > self.limits.soft_max_tokens:
                break
            if token_count < self.limits.min_tokens:
                continue
            scored.append((end, self._score(evidence[end - 1], token_count)))
        return scored

    def _hard_limit_boundaries(
        self,
        units: Sequence[ContentUnit],
        evidence: Sequence[BoundaryEvidence],
        start: int,
    ) -> list[tuple[int, BoundaryEvidence]]:
        scored: list[tuple[int, BoundaryEvidence]] = []
        for end in range(start + 1, len(units)):
            token_count = self.budgeter.count_units(units[start:end])
            if token_count > self.limits.hard_max_tokens:
                break
            scored.append((end, self._score(evidence[end - 1], token_count)))
        return scored

    def _score(
        self, evidence: BoundaryEvidence, token_count: int
    ) -> BoundaryEvidence:
        distance = self._target_distance(token_count)
        signal = self.scorer.signal(evidence)
        score = (
            self.selection.semantic_weight * signal
            + self.selection.size_weight * (1.0 - distance)
        )
        return evidence.model_copy(
            update={
                "candidate_chunk_tokens": token_count,
                "target_distance": distance,
                "selection_score": score,
                "selection_signal": signal,
                "selection_strategy": self.scorer.strategy_id,
            }
        )

    def _target_distance(self, token_count: int) -> float:
        if token_count <= self.limits.target_tokens:
            denominator = self.limits.target_tokens - self.limits.min_tokens
            value = (self.limits.target_tokens - token_count) / denominator
        else:
            denominator = (
                self.limits.soft_max_tokens - self.limits.target_tokens
            )
            value = (token_count - self.limits.target_tokens) / denominator
        return max(0.0, min(1.0, value))

    def _choose(
        self,
        candidates: Sequence[tuple[int, BoundaryEvidence]],
    ) -> tuple[int, BoundaryEvidence]:
        return max(
            candidates,
            key=lambda item: (
                item[1].selection_score
                if item[1].selection_score is not None
                else float("-inf"),
                self.scorer.tie_strength(item[1]),
                -(
                    item[1].target_distance
                    if item[1].target_distance is not None
                    else 1.0
                ),
                -item[1].boundary_index,
            ),
        )

    @staticmethod
    def _as_chunk_boundary(
        evidence: BoundaryEvidence, reason: str
    ) -> ChunkBoundary:
        return ChunkBoundary(
            reason=reason,
            boundary_index=evidence.boundary_index,
            left_unit_id=evidence.left_unit_id,
            right_unit_id=evidence.right_unit_id,
            cosine_similarity=evidence.cosine_similarity,
            semantic_shift=evidence.semantic_shift,
            adaptive_threshold=evidence.adaptive_threshold,
            multi_scale=evidence.multi_scale,
            semantic_candidate=evidence.semantic_candidate,
            selection_score=evidence.selection_score,
            structural=evidence.structural,
            original_boundary_strength=evidence.original_boundary_strength,
            effective_boundary_strength=evidence.effective_boundary_strength,
            selection_signal=evidence.selection_signal,
            selection_strategy=evidence.selection_strategy,
        )
