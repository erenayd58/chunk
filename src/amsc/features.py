from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .models import BoundaryEvidence, ContentUnit, EmbeddingBatch


class AdjacentSemanticFeatureExtractor:
    def __init__(self, fixed_threshold: float) -> None:
        self.fixed_threshold = fixed_threshold

    def compute(
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
                    fixed_threshold=self.fixed_threshold,
                    semantic_candidate=shift >= self.fixed_threshold,
                )
            )
        return boundaries

