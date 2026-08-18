from __future__ import annotations

from collections.abc import Sequence
import math
from typing import Protocol

import numpy as np

from .config import MultiScaleConfig
from .models import (
    BoundaryEvidence,
    ContentUnit,
    EmbeddingBatch,
    MultiScaleSemanticProvenance,
)
from .tokenization import TokenCounter


class SemanticFeatureExtractor(Protocol):
    def compute_raw(
        self,
        units: Sequence[ContentUnit],
        embeddings: EmbeddingBatch,
        *,
        boundary_index_offset: int = 0,
    ) -> list[BoundaryEvidence]: ...


class AdjacentSemanticFeatureExtractor:
    """Computes raw 1-to-1 cosine features.

    ``fixed_threshold`` remains as a backwards-compatible convenience for the
    public V1 feature-extractor API. New orchestration calls ``compute_raw`` and
    delegates candidate decisions to a SemanticThresholdEstimator.
    """

    def __init__(self, fixed_threshold: float | None = None) -> None:
        self.fixed_threshold = fixed_threshold

    def compute(
        self,
        units: Sequence[ContentUnit],
        embeddings: EmbeddingBatch,
        *,
        boundary_index_offset: int = 0,
    ) -> list[BoundaryEvidence]:
        boundaries = self.compute_raw(
            units,
            embeddings,
            boundary_index_offset=boundary_index_offset,
        )
        if self.fixed_threshold is None:
            return boundaries
        return [
            boundary.model_copy(
                update={
                    "fixed_threshold": self.fixed_threshold,
                    "semantic_candidate": (
                        boundary.semantic_shift >= self.fixed_threshold
                    ),
                }
            )
            for boundary in boundaries
        ]

    def compute_raw(
        self,
        units: Sequence[ContentUnit],
        embeddings: EmbeddingBatch,
        *,
        boundary_index_offset: int = 0,
    ) -> list[BoundaryEvidence]:
        vectors = np.asarray(embeddings.vectors, dtype=np.float32)
        if vectors.shape[0] != len(units):
            raise ValueError("Embedding count must match semantic content unit count")

        boundaries: list[BoundaryEvidence] = []
        for index in range(len(units) - 1):
            left = vectors[index]
            right = vectors[index + 1]
            left_norm = float(np.linalg.norm(left))
            right_norm = float(np.linalg.norm(right))
            if left_norm == 0.0 or right_norm == 0.0:
                raise ValueError("Cannot calculate cosine similarity for a zero vector")
            cosine = float(np.dot(left, right) / (left_norm * right_norm))
            cosine = max(-1.0, min(1.0, cosine))
            shift = (1.0 - cosine) / 2.0
            boundaries.append(
                BoundaryEvidence(
                    boundary_index=boundary_index_offset + index,
                    left_unit_id=units[index].unit_id,
                    right_unit_id=units[index + 1].unit_id,
                    cosine_similarity=cosine,
                    semantic_shift=shift,
                    semantic_candidate=False,
                )
            )
        return boundaries


class TokenSqrtWindowPooler:
    def pool(
        self,
        vectors: Sequence[Sequence[float]] | np.ndarray,
        token_counts: Sequence[int],
    ) -> np.ndarray:
        array = np.asarray(vectors, dtype=np.float64)
        if array.ndim != 2 or array.shape[0] != len(token_counts):
            raise ValueError("Window vectors and token counts must align")
        if array.shape[0] == 0:
            raise ValueError("Cannot pool an empty semantic window")
        if any(count <= 0 for count in token_counts):
            raise ValueError("Semantic unit token counts must be positive")

        norms = np.linalg.norm(array, axis=1)
        if np.any(norms == 0.0):
            raise ValueError("Cannot pool a zero semantic unit vector")
        normalized_units = array / norms[:, np.newaxis]
        weights = np.sqrt(np.asarray(token_counts, dtype=np.float64))
        pooled = np.sum(normalized_units * weights[:, np.newaxis], axis=0)
        pooled /= float(np.sum(weights))
        pooled_norm = float(np.linalg.norm(pooled))
        if pooled_norm == 0.0:
            raise ValueError("Cannot normalize a zero pooled semantic window")
        return pooled / pooled_norm


class MultiScaleSemanticFeatureExtractor:
    def __init__(
        self,
        config: MultiScaleConfig,
        token_counter: TokenCounter,
        pooler: TokenSqrtWindowPooler | None = None,
    ) -> None:
        self.config = config
        self.token_counter = token_counter
        self.pooler = pooler or TokenSqrtWindowPooler()

    def compute_raw(
        self,
        units: Sequence[ContentUnit],
        embeddings: EmbeddingBatch,
        *,
        boundary_index_offset: int = 0,
    ) -> list[BoundaryEvidence]:
        vectors = np.asarray(embeddings.vectors, dtype=np.float64)
        if vectors.ndim != 2 or vectors.shape[0] != len(units):
            raise ValueError("Embedding count must match semantic content unit count")

        token_counts: list[int] = []
        for unit in units:
            text = unit.text_for_embedding
            if text is None:
                raise ValueError(
                    f"Heading-only unit {unit.unit_id!r} cannot enter semantic window"
                )
            count = self.token_counter.count(text)
            if count <= 0:
                raise ValueError(
                    f"Semantic unit {unit.unit_id!r} has a non-positive token count"
                )
            token_counts.append(count)

        boundaries: list[BoundaryEvidence] = []
        base_weights = self.config.shift_weights
        for index in range(len(units) - 1):
            available_scales = [
                scale
                for scale in (1, 2, 3)
                if index - scale + 1 >= 0 and index + scale < len(units)
            ]
            weight_total = sum(base_weights[scale] for scale in available_scales)
            effective_weights = {
                scale: base_weights[scale] / weight_total
                for scale in available_scales
            }

            shifts: dict[int, float] = {}
            cosines: dict[int, float] = {}
            for scale in available_scales:
                left_start = index - scale + 1
                left_end = index + 1
                right_start = index + 1
                right_end = index + scale + 1
                left = self.pooler.pool(
                    vectors[left_start:left_end],
                    token_counts[left_start:left_end],
                )
                right = self.pooler.pool(
                    vectors[right_start:right_end],
                    token_counts[right_start:right_end],
                )
                cosine = float(np.dot(left, right))
                cosine = max(-1.0, min(1.0, cosine))
                cosines[scale] = cosine
                shifts[scale] = (1.0 - cosine) / 2.0

            semantic_shift = sum(
                effective_weights[scale] * shifts[scale]
                for scale in available_scales
            )
            provenance = MultiScaleSemanticProvenance(
                shift_1=shifts[1],
                shift_2=shifts.get(2),
                shift_3=shifts.get(3),
                available_scales=available_scales,
                scale_count=len(available_scales),
                effective_weight_1=effective_weights[1],
                effective_weight_2=effective_weights.get(2),
                effective_weight_3=effective_weights.get(3),
                unit_weighting=self.config.unit_weighting,
                window_pooling=self.config.window_pooling,
                token_counter_id=self.token_counter.counter_id,
            )
            if not math.isclose(
                sum(effective_weights.values()),
                1.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-12,
            ):
                raise AssertionError("Effective scale weights must sum to 1.0")
            boundaries.append(
                BoundaryEvidence(
                    boundary_index=boundary_index_offset + index,
                    left_unit_id=units[index].unit_id,
                    right_unit_id=units[index + 1].unit_id,
                    cosine_similarity=cosines[1],
                    semantic_shift=semantic_shift,
                    multi_scale=provenance,
                    semantic_candidate=False,
                )
            )
        return boundaries
