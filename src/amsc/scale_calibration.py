from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Literal

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


class ScaleCalibrationProvenance(BaseModel):
    """Research-only per-scale adaptive evidence.

    V3's raw shifts and combined adaptive threshold remain untouched.  This
    sidecar provenance records what the frozen threshold estimator decides
    when it observes each available scale as its own distribution.
    """

    model_config = ConfigDict(extra="forbid")

    available_scales: list[Literal[1, 2, 3]]
    shift_1: float = Field(ge=0.0, le=1.0)
    shift_2: float | None = Field(default=None, ge=0.0, le=1.0)
    shift_3: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold_1: float = Field(ge=0.0, le=1.0)
    threshold_2: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold_3: float | None = Field(default=None, ge=0.0, le=1.0)
    candidate_1: bool
    candidate_2: bool | None = None
    candidate_3: bool | None = None
    threshold_provenance_1: AdaptiveThresholdProvenance
    threshold_provenance_2: AdaptiveThresholdProvenance | None = None
    threshold_provenance_3: AdaptiveThresholdProvenance | None = None
    calibrated_evidence_1: float = Field(ge=0.0, le=1.0)
    calibrated_evidence_2: float | None = Field(default=None, ge=0.0, le=1.0)
    calibrated_evidence_3: float | None = Field(default=None, ge=0.0, le=1.0)
    effective_weight_1: float = Field(gt=0.0, le=1.0)
    effective_weight_2: float | None = Field(default=None, gt=0.0, le=1.0)
    effective_weight_3: float | None = Field(default=None, gt=0.0, le=1.0)
    fused_evidence: float = Field(ge=0.0, le=1.0)
    fused_candidate: bool
    calibration_method: Literal["per_scale_adaptive_threshold_relative_excess"] = (
        "per_scale_adaptive_threshold_relative_excess"
    )
    fusion_method: Literal["available_scale_weighted_mean"] = (
        "available_scale_weighted_mean"
    )
    candidate_policy: Literal["any_per_scale_adaptive_candidate"] = (
        "any_per_scale_adaptive_candidate"
    )

    @model_validator(mode="after")
    def validate_alignment(self) -> "ScaleCalibrationProvenance":
        if self.available_scales != sorted(set(self.available_scales)):
            raise ValueError("available_scales must be unique and sorted")
        if not self.available_scales or self.available_scales[0] != 1:
            raise ValueError("scale 1 must be available")
        groups = {
            1: (
                self.shift_1,
                self.threshold_1,
                self.candidate_1,
                self.threshold_provenance_1,
                self.calibrated_evidence_1,
                self.effective_weight_1,
            ),
            2: (
                self.shift_2,
                self.threshold_2,
                self.candidate_2,
                self.threshold_provenance_2,
                self.calibrated_evidence_2,
                self.effective_weight_2,
            ),
            3: (
                self.shift_3,
                self.threshold_3,
                self.candidate_3,
                self.threshold_provenance_3,
                self.calibrated_evidence_3,
                self.effective_weight_3,
            ),
        }
        for scale, values in groups.items():
            expected = scale in self.available_scales
            if expected and any(value is None for value in values):
                raise ValueError(
                    f"scale {scale} provenance must align with available_scales"
                )
            if not expected and any(value is not None for value in values):
                raise ValueError(
                    f"scale {scale} provenance must align with available_scales"
                )
        weights = [
            value
            for value in (
                self.effective_weight_1,
                self.effective_weight_2,
                self.effective_weight_3,
            )
            if value is not None
        ]
        if not math.isclose(sum(weights), 1.0, rel_tol=1.0e-9, abs_tol=1.0e-9):
            raise ValueError("effective calibration weights must sum to 1.0")
        if self.fused_candidate is not any(
            value is True
            for value in (self.candidate_1, self.candidate_2, self.candidate_3)
        ):
            raise ValueError("fused_candidate must be the per-scale candidate OR")
        return self


class PerScaleAdaptiveCalibrator:
    """Apply the frozen hierarchical estimator independently to each scale."""

    def __init__(
        self,
        semantic: AdaptiveSemanticConfig,
        multi_scale: MultiScaleConfig,
    ) -> None:
        self.estimator = HierarchicalAdaptiveThresholdEstimator(semantic)
        self.base_weights = multi_scale.shift_weights

    def apply(
        self,
        boundaries: Sequence[BoundaryEvidence],
        units_by_id: Mapping[str, ContentUnit],
    ) -> dict[int, ScaleCalibrationProvenance]:
        if not boundaries:
            return {}
        resolved_by_scale: dict[int, dict[int, BoundaryEvidence]] = {}
        for scale in (1, 2, 3):
            scale_boundaries: list[BoundaryEvidence] = []
            for boundary in boundaries:
                shift = self._shift(boundary, scale)
                if shift is None:
                    continue
                scale_boundaries.append(
                    boundary.model_copy(
                        update={
                            "semantic_shift": shift,
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
                )
            resolved = self.estimator.apply(scale_boundaries, units_by_id)
            resolved_by_scale[scale] = {
                item.boundary_index: item for item in resolved
            }

        result: dict[int, ScaleCalibrationProvenance] = {}
        for boundary in boundaries:
            if boundary.multi_scale is None:
                raise ValueError("Scale calibration requires V3 multi-scale provenance")
            available = list(boundary.multi_scale.available_scales)
            weight_total = sum(self.base_weights[scale] for scale in available)
            effective_weights = {
                scale: self.base_weights[scale] / weight_total for scale in available
            }
            shifts: dict[int, float] = {}
            thresholds: dict[int, AdaptiveThresholdProvenance] = {}
            candidates: dict[int, bool] = {}
            evidence: dict[int, float] = {}
            for scale in available:
                resolved = resolved_by_scale[scale][boundary.boundary_index]
                threshold = resolved.adaptive_threshold
                if threshold is None:
                    raise AssertionError("Per-scale estimator omitted threshold provenance")
                shift = resolved.semantic_shift
                shifts[scale] = shift
                thresholds[scale] = threshold
                candidates[scale] = resolved.semantic_candidate
                evidence[scale] = self._threshold_relative_excess(
                    shift,
                    threshold,
                )
            fused = sum(
                effective_weights[scale] * evidence[scale] for scale in available
            )
            result[boundary.boundary_index] = ScaleCalibrationProvenance(
                available_scales=available,
                shift_1=shifts[1],
                shift_2=shifts.get(2),
                shift_3=shifts.get(3),
                threshold_1=thresholds[1].value,
                threshold_2=(thresholds[2].value if 2 in thresholds else None),
                threshold_3=(thresholds[3].value if 3 in thresholds else None),
                candidate_1=candidates[1],
                candidate_2=candidates.get(2),
                candidate_3=candidates.get(3),
                threshold_provenance_1=thresholds[1],
                threshold_provenance_2=thresholds.get(2),
                threshold_provenance_3=thresholds.get(3),
                calibrated_evidence_1=evidence[1],
                calibrated_evidence_2=evidence.get(2),
                calibrated_evidence_3=evidence.get(3),
                effective_weight_1=effective_weights[1],
                effective_weight_2=effective_weights.get(2),
                effective_weight_3=effective_weights.get(3),
                fused_evidence=fused,
                fused_candidate=any(candidates.values()),
            )
        return result

    @staticmethod
    def _shift(boundary: BoundaryEvidence, scale: int) -> float | None:
        if boundary.multi_scale is None:
            return None
        return getattr(boundary.multi_scale, f"shift_{scale}")

    @staticmethod
    def _threshold_relative_excess(
        shift: float,
        threshold: AdaptiveThresholdProvenance,
    ) -> float:
        if threshold.degenerate or shift <= threshold.value:
            return 0.0
        if threshold.value >= 1.0:
            return 1.0
        return max(0.0, min(1.0, (shift - threshold.value) / (1.0 - threshold.value)))


class ScaleCalibratedIntervalBoundarySelector(IntervalBoundarySelector):
    """Frozen V3 interval policy using research-only fused evidence for ranking."""

    def __init__(
        self,
        *args: object,
        calibration_by_boundary: Mapping[int, ScaleCalibrationProvenance],
        selection: SelectionConfig,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, selection=selection, **kwargs)  # type: ignore[arg-type]
        self.calibration_by_boundary = calibration_by_boundary

    def _score(
        self, evidence: BoundaryEvidence, token_count: int
    ) -> BoundaryEvidence:
        distance = self._target_distance(token_count)
        calibration = self.calibration_by_boundary[evidence.boundary_index]
        score = (
            self.selection.semantic_weight * calibration.fused_evidence
            + self.selection.size_weight * (1.0 - distance)
        )
        return evidence.model_copy(
            update={
                "candidate_chunk_tokens": token_count,
                "target_distance": distance,
                "selection_score": score,
                "selection_signal": calibration.fused_evidence,
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
                self.calibration_by_boundary[
                    item[1].boundary_index
                ].fused_evidence,
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
            adaptive_threshold=evidence.adaptive_threshold,
            multi_scale=evidence.multi_scale,
            semantic_candidate=evidence.semantic_candidate,
            selection_score=evidence.selection_score,
            original_boundary_strength=evidence.original_boundary_strength,
            effective_boundary_strength=evidence.effective_boundary_strength,
            selection_signal=evidence.selection_signal,
        )
