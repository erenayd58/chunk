from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from typing import Any, Protocol, Sequence, runtime_checkable

import numpy as np

from .cache import CacheEntry, EmbeddingCache
from .models import EmbeddingBatch, SemanticEmbeddingProvenance


@runtime_checkable
class SemanticBoundaryEmbedder(Protocol):
    @property
    def model_id(self) -> str: ...

    @property
    def prefix_policy(self) -> str: ...

    @property
    def model_input_limit(self) -> int: ...

    @property
    def cache_namespace(self) -> str: ...

    def embed_units(self, texts: Sequence[str]) -> EmbeddingBatch: ...


@runtime_checkable
class RetrievalEmbedder(Protocol):
    @property
    def model_id(self) -> str: ...

    def embed_queries(self, texts: Sequence[str]) -> EmbeddingBatch: ...

    def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch: ...


class ModelTokenizer(Protocol):
    @property
    def model_max_length(self) -> int: ...

    def count(self, text: str, *, add_special_tokens: bool) -> int: ...

    def split(self, text: str, max_tokens: int) -> list[str]: ...


class EncodingBackend(Protocol):
    def encode(self, texts: Sequence[str], *, truncation: bool) -> np.ndarray: ...


class HuggingFaceModelTokenizer:
    def __init__(self, tokenizer: Any) -> None:
        self._tokenizer = tokenizer

    @property
    def model_max_length(self) -> int:
        return int(self._tokenizer.model_max_length)

    def count(self, text: str, *, add_special_tokens: bool) -> int:
        return len(
            self._tokenizer.encode(
                text,
                add_special_tokens=add_special_tokens,
                truncation=False,
            )
        )

    def split(self, text: str, max_tokens: int) -> list[str]:
        ids = self._tokenizer.encode(
            text, add_special_tokens=False, truncation=False
        )
        return [
            self._tokenizer.decode(
                ids[start : start + max_tokens], skip_special_tokens=True
            )
            for start in range(0, len(ids), max_tokens)
        ]


class _SentenceTransformerBackend:
    def __init__(self, model: Any, normalize_embeddings: bool) -> None:
        self.model = model
        self.normalize_embeddings = normalize_embeddings

    def encode(self, texts: Sequence[str], *, truncation: bool) -> np.ndarray:
        if truncation:
            raise ValueError("Silent truncation is forbidden for boundary embeddings")
        vectors = self.model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


class SemanticFragmentPooler:
    POLICY_VERSION = "sentence-token-weighted-v1"
    _sentence_boundary = re.compile(r"(?<=[.!?…])(?:\s+|\n+)|\n{2,}")

    def __init__(
        self,
        tokenizer: ModelTokenizer,
        backend: EncodingBackend,
        prefix: str,
        model_input_limit: int,
    ) -> None:
        self.tokenizer = tokenizer
        self.backend = backend
        self.prefix = prefix
        self.model_input_limit = model_input_limit

    def embed(self, text: str) -> tuple[np.ndarray, int]:
        fragments = self.fragment(text)
        prepared = [self._with_prefix(fragment) for fragment in fragments]
        for model_input in prepared:
            count = self.tokenizer.count(model_input, add_special_tokens=True)
            if count > self.model_input_limit:
                raise AssertionError(
                    f"Prepared semantic fragment has {count} model tokens; "
                    f"limit is {self.model_input_limit}"
                )

        vectors = np.asarray(
            self.backend.encode(prepared, truncation=False), dtype=np.float32
        )
        if vectors.ndim != 2 or vectors.shape[0] != len(fragments):
            raise ValueError("Embedding backend returned an unexpected shape")

        weights = np.asarray(
            [
                max(1, self.tokenizer.count(fragment, add_special_tokens=False))
                for fragment in fragments
            ],
            dtype=np.float32,
        )
        pooled = np.average(vectors, axis=0, weights=weights)
        norm = float(np.linalg.norm(pooled))
        if norm == 0.0:
            raise ValueError("Embedding backend returned a zero pooled vector")
        return np.asarray(pooled / norm, dtype=np.float32), len(fragments)

    def fragment(self, text: str) -> list[str]:
        normalized = text.strip()
        if not normalized:
            raise ValueError("Semantic text cannot be empty")
        if self._fits(normalized):
            return [normalized]

        sentences = [
            part.strip()
            for part in self._sentence_boundary.split(normalized)
            if part.strip()
        ]
        if not sentences:
            sentences = [normalized]

        fragments: list[str] = []
        current = ""
        for sentence in sentences:
            if not self._fits(sentence):
                if current:
                    fragments.append(current)
                    current = ""
                fragments.extend(self._split_oversized_sentence(sentence))
                continue

            candidate = sentence if not current else f"{current} {sentence}"
            if self._fits(candidate):
                current = candidate
            else:
                fragments.append(current)
                current = sentence

        if current:
            fragments.append(current)
        return fragments

    def _fits(self, text: str) -> bool:
        return (
            self.tokenizer.count(
                self._with_prefix(text), add_special_tokens=True
            )
            <= self.model_input_limit
        )

    def _with_prefix(self, text: str) -> str:
        return text if text.startswith(self.prefix) else f"{self.prefix}{text}"

    def _split_oversized_sentence(self, sentence: str) -> list[str]:
        special_and_prefix = self.tokenizer.count(
            self.prefix, add_special_tokens=True
        )
        content_budget = self.model_input_limit - special_and_prefix
        if content_budget < 1:
            raise ValueError("Prefix and special tokens consume model input limit")

        while content_budget >= 1:
            pieces = [piece.strip() for piece in self.tokenizer.split(sentence, content_budget)]
            pieces = [piece for piece in pieces if piece]
            if pieces and all(self._fits(piece) for piece in pieces):
                return pieces
            content_budget -= 1
        raise ValueError("Unable to fragment sentence under model input limit")


class SentenceTransformerBoundaryEmbedder:
    def __init__(
        self,
        *,
        backend: EncodingBackend,
        tokenizer: ModelTokenizer,
        model_id: str,
        prefix: str = "query: ",
        prefix_policy: str = "symmetric_query",
        max_input_tokens_override: int | None = None,
    ) -> None:
        native_limit = tokenizer.model_max_length
        if native_limit <= 0 or native_limit > 1_000_000:
            raise ValueError("Model tokenizer must expose a finite input limit")
        if (
            max_input_tokens_override is not None
            and max_input_tokens_override > native_limit
        ):
            raise ValueError("Model input override cannot exceed native model limit")

        self._backend = backend
        self._tokenizer = tokenizer
        self._model_id = model_id
        self._prefix = prefix
        self._prefix_policy = prefix_policy
        self._model_input_limit = max_input_tokens_override or native_limit
        self._pooler = SemanticFragmentPooler(
            tokenizer=tokenizer,
            backend=backend,
            prefix=prefix,
            model_input_limit=self._model_input_limit,
        )

    @classmethod
    def from_pretrained(
        cls,
        model_name: str,
        *,
        revision: str | None = None,
        device: str = "auto",
        prefix: str = "query: ",
        prefix_policy: str = "symmetric_query",
        max_input_tokens_override: int | None = None,
        normalize_embeddings: bool = True,
    ) -> "SentenceTransformerBoundaryEmbedder":
        try:
            import torch
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError(
                "Install the model extra with: pip install -e '.[model]'"
            ) from exc

        resolved_device = (
            "cuda" if device == "auto" and torch.cuda.is_available() else device
        )
        if resolved_device == "auto":
            resolved_device = "cpu"
        model = SentenceTransformer(
            model_name, revision=revision, device=resolved_device
        )
        tokenizer = HuggingFaceModelTokenizer(model.tokenizer)
        effective_limit = max_input_tokens_override or tokenizer.model_max_length
        model.max_seq_length = effective_limit
        backend = _SentenceTransformerBackend(model, normalize_embeddings)
        model_id = f"{model_name}@{revision or 'default'}"
        return cls(
            backend=backend,
            tokenizer=tokenizer,
            model_id=model_id,
            prefix=prefix,
            prefix_policy=prefix_policy,
            max_input_tokens_override=max_input_tokens_override,
        )

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def prefix_policy(self) -> str:
        return self._prefix_policy

    @property
    def prefix(self) -> str:
        return self._prefix

    @property
    def model_input_limit(self) -> int:
        return self._model_input_limit

    @property
    def cache_namespace(self) -> str:
        return "|".join(
            [
                "semantic-boundary",
                self.model_id,
                self.prefix_policy,
                self._prefix,
                str(self.model_input_limit),
                SemanticFragmentPooler.POLICY_VERSION,
            ]
        )

    def embed_units(self, texts: Sequence[str]) -> EmbeddingBatch:
        vectors: list[np.ndarray] = []
        provenance: list[SemanticEmbeddingProvenance] = []
        for text in texts:
            vector, fragment_count = self._pooler.embed(text)
            vectors.append(vector)
            provenance.append(
                SemanticEmbeddingProvenance(
                    model_id=self.model_id,
                    prefix_policy=self.prefix_policy,
                    prefix=self._prefix,
                    model_input_limit=self.model_input_limit,
                    semantic_fragment_count=fragment_count,
                    semantic_pooling="token_weighted_mean",
                )
            )
        if not vectors:
            return EmbeddingBatch(
                vectors=np.empty((0, 0), dtype=np.float32), provenance=()
            )
        return EmbeddingBatch(vectors=np.vstack(vectors), provenance=tuple(provenance))


class CachedSemanticBoundaryEmbedder:
    def __init__(
        self, delegate: SemanticBoundaryEmbedder, cache: EmbeddingCache
    ) -> None:
        self.delegate = delegate
        self.cache = cache

    @property
    def model_id(self) -> str:
        return self.delegate.model_id

    @property
    def prefix_policy(self) -> str:
        return self.delegate.prefix_policy

    @property
    def model_input_limit(self) -> int:
        return self.delegate.model_input_limit

    @property
    def cache_namespace(self) -> str:
        return self.delegate.cache_namespace

    def embed_units(self, texts: Sequence[str]) -> EmbeddingBatch:
        vectors: list[np.ndarray | None] = [None] * len(texts)
        provenance: list[SemanticEmbeddingProvenance | None] = [None] * len(texts)
        missing_indices: list[int] = []
        missing_texts: list[str] = []
        keys: list[str] = []

        for index, text in enumerate(texts):
            key = self._key(text)
            keys.append(key)
            cached = self.cache.get(key)
            if cached is None:
                missing_indices.append(index)
                missing_texts.append(text)
            else:
                vectors[index] = cached.vector
                provenance[index] = replace(cached.provenance, cache_hit=True)

        if missing_texts:
            batch = self.delegate.embed_units(missing_texts)
            for offset, index in enumerate(missing_indices):
                vector = np.asarray(batch.vectors[offset], dtype=np.float32)
                item_provenance = batch.provenance[offset]
                vectors[index] = vector
                provenance[index] = item_provenance
                self.cache.set(
                    keys[index],
                    CacheEntry(vector=vector, provenance=item_provenance),
                )

        if any(vector is None for vector in vectors):
            raise AssertionError("Embedding cache assembly left missing vectors")
        return EmbeddingBatch(
            vectors=np.vstack([vector for vector in vectors if vector is not None]),
            provenance=tuple(item for item in provenance if item is not None),
        )

    def _key(self, text: str) -> str:
        payload = f"{self.cache_namespace}\0{text}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
