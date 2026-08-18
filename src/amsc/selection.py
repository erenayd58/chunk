from __future__ import annotations

from collections.abc import Sequence

from .config import SelectionConfig, SemanticConfig, TokenLimitsConfig
from .models import (
    BoundaryEvidence,
    ChunkBoundary,
    ContentUnit,
    SelectedSegment,
)
from .units import RenderedTokenBudgeter


class IntervalBoundarySelector:
    def __init__(
        self,
        budgeter: RenderedTokenBudgeter,
        token_limits: TokenLimitsConfig,
        semantic: SemanticConfig,
        selection: SelectionConfig,
    ) -> None:
        self.budgeter = budgeter
        self.limits = token_limits
        self.semantic = semantic
        self.selection = selection

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
                item for item in scored if item[1].semantic_candidate
            ]

            if semantic_candidates:
                end, selected = self._choose(semantic_candidates)
                reason = "fixed_semantic_boundary"
            elif remaining_tokens <= self.limits.soft_max_tokens:
                segments.append(
                    SelectedSegment(
                        start=start,
                        end=len(units),
                        end_boundary=ChunkBoundary(reason="document_end"),
                    )
                )
                break
            else:
                size_fallbacks = scored
                if size_fallbacks:
                    end, selected = self._choose(size_fallbacks)
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
                                    end_boundary=ChunkBoundary(
                                        reason="document_end"
                                    ),
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
        segments = V1TailResolver(
            budgeter=self.budgeter,
            limits=self.limits,
            fixed_threshold=self.semantic.fixed_threshold,
        ).resolve(units, segments)
        selected_after_tail = {
            segment.end_boundary.boundary_index
            for segment in segments
            if segment.end_boundary.boundary_index is not None
        }
        removed = selected_before_tail - selected_after_tail
        for index, item in enumerate(evidence):
            if item.boundary_index in removed:
                evidence[index] = item.model_copy(
                    update={"selected_reason": "removed_by_v1_tail_coalescing"}
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
            updated = self._score(evidence[end - 1], token_count)
            scored.append((end, updated))
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
            updated = self._score(evidence[end - 1], token_count)
            scored.append((end, updated))
        return scored

    def _score(
        self, evidence: BoundaryEvidence, token_count: int
    ) -> BoundaryEvidence:
        distance = self._target_distance(token_count)
        score = (
            self.selection.semantic_weight * evidence.semantic_shift
            + self.selection.size_weight * (1.0 - distance)
        )
        return evidence.model_copy(
            update={
                "candidate_chunk_tokens": token_count,
                "target_distance": distance,
                "selection_score": score,
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

    @staticmethod
    def _choose(
        candidates: Sequence[tuple[int, BoundaryEvidence]],
    ) -> tuple[int, BoundaryEvidence]:
        return max(
            candidates,
            key=lambda item: (
                item[1].selection_score
                if item[1].selection_score is not None
                else float("-inf"),
                item[1].semantic_shift,
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
            fixed_threshold=evidence.fixed_threshold,
            selection_score=evidence.selection_score,
        )


class V1TailResolver:
    def __init__(
        self,
        budgeter: RenderedTokenBudgeter,
        limits: TokenLimitsConfig,
        fixed_threshold: float,
    ) -> None:
        self.budgeter = budgeter
        self.limits = limits
        self.fixed_threshold = fixed_threshold

    def resolve(
        self,
        units: Sequence[ContentUnit],
        segments: list[SelectedSegment],
    ) -> list[SelectedSegment]:
        if len(segments) < 2:
            return segments

        tail = segments[-1]
        tail_tokens = self.budgeter.count_units(units[tail.start : tail.end])
        if tail_tokens >= self.limits.min_tokens:
            return segments

        previous = segments[-2]
        removed_boundary = previous.end_boundary
        if removed_boundary.reason not in {
            "size_fallback",
            "hard_limit_fallback",
        }:
            tail.unmerged_short_tail_reason = "preceding_boundary_is_not_fallback"
            return segments
        if (
            removed_boundary.semantic_shift is not None
            and removed_boundary.semantic_shift >= self.fixed_threshold
        ):
            tail.unmerged_short_tail_reason = "preceding_boundary_is_semantic"
            return segments

        combined_tokens = self.budgeter.count_units(
            units[previous.start : tail.end]
        )
        if combined_tokens > self.limits.hard_max_tokens:
            tail.unmerged_short_tail_reason = "combined_chunk_exceeds_configured_cap"
            return segments

        previous.end = tail.end
        previous.end_boundary = tail.end_boundary
        previous.tail_coalesced = True
        previous.metadata["removed_tail_boundary_reason"] = removed_boundary.reason
        return segments[:-1]
