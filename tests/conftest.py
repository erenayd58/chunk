from __future__ import annotations

from dataclasses import replace
from typing import Sequence

import numpy as np

from amsc.models import (
    EmbeddingBatch,
    SemanticEmbeddingProvenance,
)


class WordTokenCounter:
    counter_id = "test:whitespace@1"

    def count(self, text: str) -> int:
        return len(text.split())

    def split(self, text: str, max_tokens: int) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        return [
            " ".join(words[index : index + max_tokens])
            for index in range(0, len(words), max_tokens)
        ]


class StaticBoundaryEmbedder:
    def __init__(self, vectors_by_text: dict[str, Sequence[float]]) -> None:
        self.vectors_by_text = vectors_by_text
        self.calls: list[list[str]] = []

    @property
    def model_id(self) -> str:
        return "test:static-boundary@1"

    @property
    def prefix_policy(self) -> str:
        return "symmetric_query"

    @property
    def model_input_limit(self) -> int:
        return 512

    @property
    def cache_namespace(self) -> str:
        return "semantic-boundary|test-static|query|512|v1"

    def embed_units(self, texts: Sequence[str]) -> EmbeddingBatch:
        self.calls.append(list(texts))
        vectors = np.asarray([self.vectors_by_text[text] for text in texts], dtype=np.float32)
        provenance = tuple(
            SemanticEmbeddingProvenance(
                model_id=self.model_id,
                prefix_policy=self.prefix_policy,
                prefix="query: ",
                model_input_limit=self.model_input_limit,
                semantic_fragment_count=1,
                semantic_pooling="token_weighted_mean",
            )
            for _ in texts
        )
        return EmbeddingBatch(vectors=vectors, provenance=provenance)


class FakeModelTokenizer:
    def __init__(self, model_max_length: int = 8) -> None:
        self._model_max_length = model_max_length

    @property
    def model_max_length(self) -> int:
        return self._model_max_length

    def count(self, text: str, *, add_special_tokens: bool) -> int:
        base = len(text.split())
        return base + (2 if add_special_tokens else 0)

    def split(self, text: str, max_tokens: int) -> list[str]:
        words = text.split()
        return [
            " ".join(words[index : index + max_tokens])
            for index in range(0, len(words), max_tokens)
        ]


class RecordingBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], bool]] = []

    def encode(self, texts: Sequence[str], *, truncation: bool) -> np.ndarray:
        self.calls.append((list(texts), truncation))
        vectors = []
        for index, text in enumerate(texts, start=1):
            vectors.append([float(len(text.split())), float(index + 1)])
        return np.asarray(vectors, dtype=np.float32)


def copy_provenance(
    provenance: SemanticEmbeddingProvenance, **changes: object
) -> SemanticEmbeddingProvenance:
    return replace(provenance, **changes)

