from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

from .models import BoundaryEvidence


class ThresholdRelativeBoundaryStrengthScorer:
    def __init__(
        self,
        threshold_kind: Literal["original", "effective"],
        *,
        epsilon: float,
    ) -> None:
        self.threshold_kind = threshold_kind
        self.epsilon = epsilon

    def score(self, boundary: BoundaryEvidence) -> float:
        threshold = self._threshold(boundary)
        adaptive = boundary.adaptive_threshold
        if adaptive is None:
            raise ValueError("Threshold-relative strength requires adaptive provenance")
        if adaptive.degenerate or boundary.semantic_shift < threshold:
            return 0.0
        if threshold >= 1.0 - self.epsilon:
            return 1.0
        value = (boundary.semantic_shift - threshold) / (1.0 - threshold)
        return max(0.0, min(1.0, value))

    def _threshold(self, boundary: BoundaryEvidence) -> float:
        adaptive = boundary.adaptive_threshold
        if adaptive is None:
            raise ValueError("Adaptive threshold provenance is required")
        if self.threshold_kind == "original":
            return adaptive.value
        if boundary.structural is not None:
            return boundary.structural.effective_threshold
        return adaptive.value


class DualBoundaryStrengthAnnotator:
    def __init__(self, *, epsilon: float) -> None:
        self.original = ThresholdRelativeBoundaryStrengthScorer(
            "original", epsilon=epsilon
        )
        self.effective = ThresholdRelativeBoundaryStrengthScorer(
            "effective", epsilon=epsilon
        )

    def apply(
        self, boundaries: Sequence[BoundaryEvidence]
    ) -> list[BoundaryEvidence]:
        return [
            boundary.model_copy(
                update={
                    "original_boundary_strength": self.original.score(boundary),
                    "effective_boundary_strength": self.effective.score(boundary),
                }
            )
            for boundary in boundaries
        ]


class SelectionSignalScorer(Protocol):
    @property
    def strategy_id(self) -> str: ...

    def signal(self, boundary: BoundaryEvidence) -> float: ...

    def tie_strength(self, boundary: BoundaryEvidence) -> float: ...


class RawSemanticShiftSelectionScorer:
    strategy_id = "raw_semantic_shift"

    def signal(self, boundary: BoundaryEvidence) -> float:
        return boundary.semantic_shift

    def tie_strength(self, boundary: BoundaryEvidence) -> float:
        return boundary.semantic_shift


class EffectiveThresholdRelativeSelectionScorer:
    strategy_id = "threshold_relative"

    def signal(self, boundary: BoundaryEvidence) -> float:
        if boundary.effective_boundary_strength is None:
            raise ValueError("Effective boundary strength has not been annotated")
        return boundary.effective_boundary_strength

    def tie_strength(self, boundary: BoundaryEvidence) -> float:
        return self.signal(boundary)
