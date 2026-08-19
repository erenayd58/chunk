from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import AdaptiveSemanticConfig, MultiScaleConfig, SelectionConfig
from .models import (
    AdaptiveThresholdProvenance,
    BoundaryEvidence,
    ChunkBoundary,
    ContentUnit,
)
from .selection import IntervalBoundarySelector
from .thresholds import HierarchicalAdaptiveThresholdEstimator
from .tokenization import TokenCounter


class ComparatorBoundaryProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method_id: Literal[
        "local_semantic_prominence",
        "cosine_kernel_change_point",
    ]
    score: float = Field(ge=0.0, le=1.0)
    adaptive_threshold: AdaptiveThresholdProvenance | None = None
    semantic_candidate: bool
    threshold_relative_evidence: float = Field(ge=0.0, le=1.0)
    shift_1: float = Field(ge=0.0, le=1.0)
    broad_context_shift: float | None = Field(default=None, ge=0.0, le=1.0)
    raw_local_prominence: float | None = Field(default=None, ge=-1.0, le=1.0)
    broad_context_scales: list[Literal[2, 3]] | None = None
    window_size: Literal[1, 2, 3] | None = None
    kernel: Literal["normalized_cosine_linear"] | None = None
    change_statistic: Literal["token_sqrt_weighted_mmd2_over_2"] | None = None
    unit_weighting: Literal["configured_token_counter_sqrt"]
    threshold_estimator: Literal["frozen_hierarchical_adaptive"] = (
        "frozen_hierarchical_adaptive"
    )

    @model_validator(mode="after")
    def validate_method_fields(self) -> "ComparatorBoundaryProvenance":
        if self.method_id == "local_semantic_prominence":
            if self.window_size is not None or self.kernel is not None:
                raise ValueError("Local prominence cannot carry kernel fields")
            if self.broad_context_shift is None:
                if self.adaptive_threshold is not None or self.semantic_candidate:
                    raise ValueError(
                        "Scale-1-only edge cannot be a local-prominence candidate"
                    )
            elif (
                self.raw_local_prominence is None
                or not self.broad_context_scales
                or self.adaptive_threshold is None
            ):
                raise ValueError("Local prominence provenance is incomplete")
        else:
            if (
                self.window_size is None
                or self.kernel is None
                or self.change_statistic is None
                or self.adaptive_threshold is None
            ):
                raise ValueError("Kernel change-point provenance is incomplete")
            if self.broad_context_shift is not None:
                raise ValueError("Kernel change-point cannot carry prominence fields")
        return self


class LocalSemanticProminenceComparator:
    """Measure a local 1-to-1 spike above the available broader-scale context."""

    method_id = "local_semantic_prominence"

    def __init__(
        self,
        semantic: AdaptiveSemanticConfig,
        multi_scale: MultiScaleConfig,
    ) -> None:
        self.estimator = HierarchicalAdaptiveThresholdEstimator(semantic)
        self.base_weights = multi_scale.shift_weights

    def compute(
        self,
        boundaries: Sequence[BoundaryEvidence],
        units_by_id: Mapping[str, ContentUnit],
    ) -> dict[int, ComparatorBoundaryProvenance]:
        scores: dict[int, float] = {}
        details: dict[int, tuple[float, float, list[int]]] = {}
        scored_boundaries: list[BoundaryEvidence] = []
        for boundary in boundaries:
            multi = boundary.multi_scale
            if multi is None:
                raise ValueError("Local prominence requires V3 multi-scale provenance")
            broad_scales = [scale for scale in multi.available_scales if scale > 1]
            if not broad_scales:
                continue
            broad_total = sum(self.base_weights[scale] for scale in broad_scales)
            broad = sum(
                self.base_weights[scale] * getattr(multi, f"shift_{scale}")
                for scale in broad_scales
            ) / broad_total
            raw_prominence = multi.shift_1 - broad
            score = max(0.0, raw_prominence)
            scores[boundary.boundary_index] = score
            details[boundary.boundary_index] = (
                broad,
                raw_prominence,
                broad_scales,
            )
            scored_boundaries.append(
                _as_score_boundary(boundary, score)
            )

        resolved = {
            item.boundary_index: item
            for item in self.estimator.apply(scored_boundaries, units_by_id)
        }
        result: dict[int, ComparatorBoundaryProvenance] = {}
        for boundary in boundaries:
            multi = boundary.multi_scale
            if multi is None:
                raise AssertionError("Multi-scale provenance disappeared")
            item = resolved.get(boundary.boundary_index)
            if item is None:
                result[boundary.boundary_index] = ComparatorBoundaryProvenance(
                    method_id=self.method_id,
                    score=0.0,
                    adaptive_threshold=None,
                    semantic_candidate=False,
                    threshold_relative_evidence=0.0,
                    shift_1=multi.shift_1,
                    broad_context_shift=None,
                    raw_local_prominence=None,
                    broad_context_scales=None,
                    unit_weighting="configured_token_counter_sqrt",
                )
                continue
            threshold = item.adaptive_threshold
            if threshold is None:
                raise AssertionError("Prominence estimator omitted provenance")
            broad, raw_prominence, broad_scales = details[
                boundary.boundary_index
            ]
            result[boundary.boundary_index] = ComparatorBoundaryProvenance(
                method_id=self.method_id,
                score=scores[boundary.boundary_index],
                adaptive_threshold=threshold,
                semantic_candidate=item.semantic_candidate,
                threshold_relative_evidence=_threshold_relative_evidence(
                    item.semantic_shift,
                    threshold,
                ),
                shift_1=multi.shift_1,
                broad_context_shift=broad,
                raw_local_prominence=raw_prominence,
                broad_context_scales=broad_scales,  # type: ignore[arg-type]
                unit_weighting="configured_token_counter_sqrt",
            )
        return result


class CosineKernelChangePointComparator:
    """Largest-window weighted cosine-kernel two-sample change statistic.

    With normalized unit vectors and token-sqrt weights, the score is
    ``||mean_left - mean_right||^2 / 4``.  This equals shift_1 for a 1-to-1
    window and is the normalized biased MMD statistic for the cosine-linear
    kernel at wider windows.  No bandwidth or fitted change penalty is used.
    """

    method_id = "cosine_kernel_change_point"

    def __init__(self, semantic: AdaptiveSemanticConfig) -> None:
        self.estimator = HierarchicalAdaptiveThresholdEstimator(semantic)

    def compute(
        self,
        *,
        prepared: Sequence[ContentUnit],
        boundaries: Sequence[BoundaryEvidence],
        units_by_id: Mapping[str, ContentUnit],
        retained_embeddings: Mapping[str, np.ndarray],
        token_counter: TokenCounter,
    ) -> dict[int, ComparatorBoundaryProvenance]:
        run_position = _semantic_run_positions(prepared)
        scores: dict[int, float] = {}
        window_sizes: dict[int, int] = {}
        scored_boundaries: list[BoundaryEvidence] = []
        for boundary in boundaries:
            left_position = run_position.get(boundary.left_unit_id)
            right_position = run_position.get(boundary.right_unit_id)
            if left_position is None or right_position is None:
                raise ValueError("Boundary unit is absent from semantic runs")
            run_units, left_index = left_position
            other_run, right_index = right_position
            if run_units is not other_run or right_index != left_index + 1:
                raise ValueError("Boundary crosses a semantic-run discontinuity")
            multi = boundary.multi_scale
            if multi is None:
                raise ValueError("Kernel comparator requires multi-scale provenance")
            window_size = max(multi.available_scales)
            left = run_units[left_index - window_size + 1 : left_index + 1]
            right = run_units[right_index : right_index + window_size]
            if len(left) != window_size or len(right) != window_size:
                raise AssertionError("Kernel window violates full-symmetric policy")
            score = _cosine_kernel_change_score(
                left,
                right,
                retained_embeddings,
                token_counter,
            )
            scores[boundary.boundary_index] = score
            window_sizes[boundary.boundary_index] = window_size
            scored_boundaries.append(_as_score_boundary(boundary, score))

        resolved = self.estimator.apply(scored_boundaries, units_by_id)
        result: dict[int, ComparatorBoundaryProvenance] = {}
        for boundary, item in zip(boundaries, resolved, strict=True):
            threshold = item.adaptive_threshold
            multi = boundary.multi_scale
            if threshold is None or multi is None:
                raise AssertionError("Kernel threshold provenance is incomplete")
            result[boundary.boundary_index] = ComparatorBoundaryProvenance(
                method_id=self.method_id,
                score=scores[boundary.boundary_index],
                adaptive_threshold=threshold,
                semantic_candidate=item.semantic_candidate,
                threshold_relative_evidence=_threshold_relative_evidence(
                    item.semantic_shift,
                    threshold,
                ),
                shift_1=multi.shift_1,
                window_size=window_sizes[boundary.boundary_index],  # type: ignore[arg-type]
                kernel="normalized_cosine_linear",
                change_statistic="token_sqrt_weighted_mmd2_over_2",
                unit_weighting="configured_token_counter_sqrt",
            )
        return result


class ComparatorIntervalBoundarySelector(IntervalBoundarySelector):
    """Frozen V3 interval/token policy with an injected comparator signal."""

    def __init__(
        self,
        *args: object,
        comparator_by_boundary: Mapping[int, ComparatorBoundaryProvenance],
        selection: SelectionConfig,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, selection=selection, **kwargs)  # type: ignore[arg-type]
        self.comparator_by_boundary = comparator_by_boundary

    def _score(
        self,
        evidence: BoundaryEvidence,
        token_count: int,
    ) -> BoundaryEvidence:
        distance = self._target_distance(token_count)
        comparator = self.comparator_by_boundary[evidence.boundary_index]
        signal = comparator.threshold_relative_evidence
        selection_score = (
            self.selection.semantic_weight * signal
            + self.selection.size_weight * (1.0 - distance)
        )
        return evidence.model_copy(
            update={
                "candidate_chunk_tokens": token_count,
                "target_distance": distance,
                "selection_score": selection_score,
                "selection_signal": signal,
            }
        )

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
                self.comparator_by_boundary[
                    item[1].boundary_index
                ].threshold_relative_evidence,
                self.comparator_by_boundary[item[1].boundary_index].score,
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
        evidence: BoundaryEvidence,
        reason: str,
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
            original_boundary_strength=evidence.original_boundary_strength,
            effective_boundary_strength=evidence.effective_boundary_strength,
            selection_signal=evidence.selection_signal,
        )


def _as_score_boundary(
    boundary: BoundaryEvidence,
    score: float,
) -> BoundaryEvidence:
    return boundary.model_copy(
        update={
            "semantic_shift": score,
            "adaptive_threshold": None,
            "semantic_candidate": False,
            "candidate_chunk_tokens": None,
            "target_distance": None,
            "selection_score": None,
            "selected_reason": None,
            "selection_signal": None,
            "selection_strategy": None,
            "merge_decisions": None,
        }
    )


def _threshold_relative_evidence(
    score: float,
    threshold: AdaptiveThresholdProvenance,
) -> float:
    if threshold.degenerate or score <= threshold.value:
        return 0.0
    if threshold.value >= 1.0:
        return 1.0
    return max(0.0, min(1.0, (score - threshold.value) / (1.0 - threshold.value)))


def _semantic_run_positions(
    prepared: Sequence[ContentUnit],
) -> dict[str, tuple[list[ContentUnit], int]]:
    positions: dict[str, tuple[list[ContentUnit], int]] = {}
    cursor = 0
    while cursor < len(prepared):
        if prepared[cursor].text_for_embedding is None:
            cursor += 1
            continue
        end = cursor
        while end < len(prepared) and prepared[end].text_for_embedding is not None:
            end += 1
        run = list(prepared[cursor:end])
        for index, unit in enumerate(run):
            positions[unit.unit_id] = (run, index)
        cursor = end
    return positions


def _cosine_kernel_change_score(
    left: Sequence[ContentUnit],
    right: Sequence[ContentUnit],
    retained_embeddings: Mapping[str, np.ndarray],
    token_counter: TokenCounter,
) -> float:
    left_mean = _weighted_feature_mean(left, retained_embeddings, token_counter)
    right_mean = _weighted_feature_mean(right, retained_embeddings, token_counter)
    score = float(np.dot(left_mean - right_mean, left_mean - right_mean) / 4.0)
    return max(0.0, min(1.0, score))


def _weighted_feature_mean(
    units: Sequence[ContentUnit],
    retained_embeddings: Mapping[str, np.ndarray],
    token_counter: TokenCounter,
) -> np.ndarray:
    vectors: list[np.ndarray] = []
    weights: list[float] = []
    for unit in units:
        text = unit.text_for_embedding
        vector = retained_embeddings.get(unit.unit_id)
        if text is None or vector is None:
            raise ValueError("Kernel window is missing semantic text or embedding")
        count = token_counter.count(text)
        if count <= 0:
            raise ValueError("Kernel window unit has a non-positive token count")
        normalized = np.asarray(vector, dtype=np.float64)
        norm = float(np.linalg.norm(normalized))
        if norm == 0.0:
            raise ValueError("Kernel window contains a zero embedding")
        vectors.append(normalized / norm)
        weights.append(math.sqrt(count))
    weight_array = np.asarray(weights, dtype=np.float64)
    vector_array = np.vstack(vectors)
    return np.sum(vector_array * weight_array[:, None], axis=0) / float(
        np.sum(weight_array)
    )
