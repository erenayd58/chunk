from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .config import AdaptiveSemanticConfig
from .models import (
    AdaptiveThresholdProvenance,
    BoundaryEvidence,
    ContentUnit,
)


class SemanticThresholdEstimator(Protocol):
    @property
    def semantic_boundary_reason(self) -> str: ...

    def apply(
        self,
        boundaries: Sequence[BoundaryEvidence],
        units_by_id: Mapping[str, ContentUnit],
    ) -> list[BoundaryEvidence]: ...


class FixedThresholdEstimator:
    semantic_boundary_reason = "fixed_semantic_boundary"

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold

    def apply(
        self,
        boundaries: Sequence[BoundaryEvidence],
        units_by_id: Mapping[str, ContentUnit],
    ) -> list[BoundaryEvidence]:
        del units_by_id
        return [
            boundary.model_copy(
                update={
                    "fixed_threshold": self.threshold,
                    "semantic_candidate": (
                        boundary.semantic_shift >= self.threshold
                    ),
                }
            )
            for boundary in boundaries
        ]


@dataclass(frozen=True)
class _DistributionEstimate:
    value: float
    sample_count: int
    method: str
    median: float
    mad: float
    robust_scale: float
    q25: float
    q75: float
    q90: float
    degenerate: bool


class HierarchicalAdaptiveThresholdEstimator:
    semantic_boundary_reason = "adaptive_semantic_boundary"

    def __init__(self, config: AdaptiveSemanticConfig) -> None:
        self.config = config

    def apply(
        self,
        boundaries: Sequence[BoundaryEvidence],
        units_by_id: Mapping[str, ContentUnit],
    ) -> list[BoundaryEvidence]:
        if not boundaries:
            return []

        scopes = [
            longest_common_prefix(
                units_by_id[boundary.left_unit_id].section_path,
                units_by_id[boundary.right_unit_id].section_path,
            )
            for boundary in boundaries
        ]
        shifts = [boundary.semantic_shift for boundary in boundaries]
        updated: list[BoundaryEvidence] = []

        for boundary, initial_scope in zip(boundaries, scopes, strict=True):
            provenance = self._resolve_threshold(initial_scope, scopes, shifts)
            updated.append(
                boundary.model_copy(
                    update={
                        "adaptive_threshold": provenance,
                        "semantic_candidate": (
                            not provenance.degenerate
                            and boundary.semantic_shift >= provenance.value
                        ),
                    }
                )
            )
        return updated

    def _resolve_threshold(
        self,
        initial_scope: tuple[str, ...],
        boundary_scopes: Sequence[tuple[str, ...]],
        shifts: Sequence[float],
    ) -> AdaptiveThresholdProvenance:
        for depth in range(len(initial_scope), 0, -1):
            scope = initial_scope[:depth]
            samples = self._samples_for_scope(scope, boundary_scopes, shifts)
            if len(samples) < self.config.min_section_boundaries:
                continue
            estimate = self._estimate_distribution(samples)
            if estimate.degenerate:
                continue
            kind = "section" if scope == initial_scope else "parent_section"
            return self._provenance(estimate, scope, kind)

        document_samples = list(shifts)
        if len(document_samples) < self.config.min_document_boundaries:
            return AdaptiveThresholdProvenance(
                value=self.config.short_document_fallback_threshold,
                scope=[],
                threshold_scope_kind="document",
                sample_count=len(document_samples),
                method="short_document_fixed_fallback",
                low_confidence=True,
                degenerate=False,
            )

        estimate = self._estimate_distribution(document_samples)
        if estimate.degenerate:
            return self._provenance(
                estimate,
                (),
                "document",
                method="uniform_document_no_candidate",
            )
        return self._provenance(estimate, (), "document")

    @staticmethod
    def _samples_for_scope(
        scope: tuple[str, ...],
        boundary_scopes: Sequence[tuple[str, ...]],
        shifts: Sequence[float],
    ) -> list[float]:
        depth = len(scope)
        return [
            shift
            for boundary_scope, shift in zip(boundary_scopes, shifts, strict=True)
            if boundary_scope[:depth] == scope
        ]

    def _estimate_distribution(
        self, samples: Sequence[float]
    ) -> _DistributionEstimate:
        values = np.asarray(samples, dtype=np.float64)
        median = float(np.median(values))
        deviations = np.abs(values - median)
        mad = float(np.median(deviations))
        q25 = self._quantile(values, 0.25)
        q75 = self._quantile(values, 0.75)
        q90 = self._quantile(values, 0.90)
        iqr = q75 - q25
        clamp_floor = self._quantile(values, self.config.quantile_floor)
        clamp_ceiling = self._quantile(values, self.config.quantile_ceiling)
        epsilon = self.config.dispersion_epsilon

        if mad > epsilon:
            robust_scale = 1.4826 * mad
            raw_threshold = median + self.config.mad_lambda * robust_scale
            value = min(clamp_ceiling, max(clamp_floor, raw_threshold))
            method = "mad_quantile"
            degenerate = False
        elif iqr > epsilon:
            robust_scale = iqr / 1.349
            raw_threshold = median + self.config.mad_lambda * robust_scale
            value = min(clamp_ceiling, max(clamp_floor, raw_threshold))
            method = "iqr_quantile"
            degenerate = False
        else:
            positive_tail = sorted(
                value for value in values.tolist() if value > median + epsilon
            )
            robust_scale = 0.0
            if positive_tail:
                value = float(positive_tail[0])
                method = "positive_tail"
                degenerate = False
            else:
                value = median
                method = "uniform_distribution"
                degenerate = True

        return _DistributionEstimate(
            value=float(value),
            sample_count=len(samples),
            method=method,
            median=median,
            mad=mad,
            robust_scale=float(robust_scale),
            q25=q25,
            q75=q75,
            q90=q90,
            degenerate=degenerate,
        )

    @staticmethod
    def _quantile(values: np.ndarray, quantile: float) -> float:
        return float(np.quantile(values, quantile, method="linear"))

    def _provenance(
        self,
        estimate: _DistributionEstimate,
        scope: tuple[str, ...],
        kind: str,
        *,
        method: str | None = None,
    ) -> AdaptiveThresholdProvenance:
        return AdaptiveThresholdProvenance(
            value=estimate.value,
            scope=list(scope),
            threshold_scope_kind=kind,  # type: ignore[arg-type]
            sample_count=estimate.sample_count,
            method=method or estimate.method,
            median=estimate.median,
            mad=estimate.mad,
            robust_scale=estimate.robust_scale,
            q25=estimate.q25,
            q75=estimate.q75,
            q90=estimate.q90,
            mad_lambda=self.config.mad_lambda,
            low_confidence=False,
            degenerate=estimate.degenerate,
        )


def longest_common_prefix(
    left: Sequence[str], right: Sequence[str]
) -> tuple[str, ...]:
    common: list[str] = []
    for left_part, right_part in zip(left, right, strict=False):
        if left_part != right_part:
            break
        common.append(left_part)
    return tuple(common)
