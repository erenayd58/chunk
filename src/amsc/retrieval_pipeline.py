from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Iterable, Literal, Protocol, Sequence
import unicodedata

import numpy as np


@dataclass(frozen=True)
class RetrievalEmbeddingStats:
    role: Literal["query", "document"]
    text_count: int
    cache_hits: int
    cache_misses: int
    fragment_count: int


class RetrievalEmbeddingModel(Protocol):
    @property
    def model_id(self) -> str: ...

    @property
    def model_input_limit(self) -> int: ...

    def embed_queries(
        self, texts: Sequence[str]
    ) -> tuple[np.ndarray, RetrievalEmbeddingStats]: ...

    def embed_documents(
        self, texts: Sequence[str]
    ) -> tuple[np.ndarray, RetrievalEmbeddingStats]: ...


class E5RetrievalEmbedder:
    """Independent E5 query/document adapter with exact-text role-separated cache."""

    _SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])(?:\s+|\n+)|\n{2,}")
    _POLICY_VERSION = "sentence-token-weighted-v1"

    def __init__(
        self,
        *,
        model: object,
        tokenizer: object,
        model_id: str,
        query_prefix: str,
        document_prefix: str,
        model_input_limit: int,
        batch_size: int,
        cache_dir: str | Path,
        normalize_embeddings: bool = True,
        cache_queries: bool = False,
    ) -> None:
        native_limit = int(getattr(tokenizer, "model_max_length"))
        if native_limit <= 0 or native_limit > 1_000_000:
            raise ValueError("Retrieval tokenizer must expose a finite input limit")
        if model_input_limit < 1 or model_input_limit > native_limit:
            raise ValueError("Retrieval model_input_limit must not exceed native limit")
        if batch_size < 1:
            raise ValueError("Retrieval embedding batch_size must be positive")
        self._model = model
        self._tokenizer = tokenizer
        self._model_id = model_id
        self._query_prefix = query_prefix
        self._document_prefix = document_prefix
        self._model_input_limit = model_input_limit
        self._batch_size = batch_size
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._normalize_embeddings = normalize_embeddings
        self._cache_queries = cache_queries
        setattr(self._model, "max_seq_length", model_input_limit)

    @classmethod
    def from_pretrained(
        cls,
        model_name: str,
        *,
        revision: str | None,
        device: str,
        local_files_only: bool,
        query_prefix: str,
        document_prefix: str,
        model_input_limit: int,
        batch_size: int,
        cache_dir: str | Path,
        normalize_embeddings: bool,
        cache_queries: bool,
    ) -> "E5RetrievalEmbedder":
        try:
            import torch
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Retrieval benchmark requires: pip install -e '.[benchmark]'"
            ) from exc
        resolved_device = (
            "cuda" if device == "auto" and torch.cuda.is_available() else device
        )
        if resolved_device == "auto":
            resolved_device = "cpu"
        model = SentenceTransformer(
            model_name,
            revision=revision,
            device=resolved_device,
            local_files_only=local_files_only,
        )
        return cls(
            model=model,
            tokenizer=model.tokenizer,
            model_id=f"{model_name}@{revision or 'default'}",
            query_prefix=query_prefix,
            document_prefix=document_prefix,
            model_input_limit=model_input_limit,
            batch_size=batch_size,
            cache_dir=cache_dir,
            normalize_embeddings=normalize_embeddings,
            cache_queries=cache_queries,
        )

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def model_input_limit(self) -> int:
        return self._model_input_limit

    def embed_queries(
        self, texts: Sequence[str]
    ) -> tuple[np.ndarray, RetrievalEmbeddingStats]:
        return self._embed(texts, role="query", prefix=self._query_prefix)

    def embed_documents(
        self, texts: Sequence[str]
    ) -> tuple[np.ndarray, RetrievalEmbeddingStats]:
        return self._embed(texts, role="document", prefix=self._document_prefix)

    def _embed(
        self,
        texts: Sequence[str],
        *,
        role: Literal["query", "document"],
        prefix: str,
    ) -> tuple[np.ndarray, RetrievalEmbeddingStats]:
        if not texts:
            return (
                np.empty((0, 0), dtype=np.float32),
                RetrievalEmbeddingStats(role, 0, 0, 0, 0),
            )
        vectors: list[np.ndarray | None] = [None] * len(texts)
        missing: list[tuple[int, str, str]] = []
        cache_hits = 0
        for index, text in enumerate(texts):
            if not text.strip():
                raise ValueError("Retrieval embedding text cannot be empty")
            key = self._cache_key(role, prefix, text)
            cached = None if role == "query" and not self._cache_queries else self._cache_get(key)
            if cached is None:
                missing.append((index, text, key))
            else:
                vectors[index] = cached
                cache_hits += 1

        fragment_count = 0
        if missing:
            fragments_by_text: list[list[str]] = []
            weights_by_text: list[np.ndarray] = []
            prepared: list[str] = []
            for _, text, _ in missing:
                fragments = self._fragment(text, prefix)
                fragments_by_text.append(fragments)
                weights_by_text.append(
                    np.asarray(
                        [max(1, self._count(fragment, special=False)) for fragment in fragments],
                        dtype=np.float32,
                    )
                )
                for fragment in fragments:
                    model_input = self._with_prefix(fragment, prefix)
                    count = self._count(model_input, special=True)
                    if count > self.model_input_limit:
                        raise AssertionError(
                            f"Prepared retrieval fragment has {count} tokens; "
                            f"limit is {self.model_input_limit}"
                        )
                    prepared.append(model_input)
            fragment_count = len(prepared)
            encoded = np.asarray(
                self._model.encode(
                    prepared,
                    batch_size=self._batch_size,
                    convert_to_numpy=True,
                    normalize_embeddings=self._normalize_embeddings,
                    show_progress_bar=False,
                ),
                dtype=np.float32,
            )
            if encoded.ndim != 2 or encoded.shape[0] != len(prepared):
                raise ValueError("Retrieval embedding backend returned an invalid shape")
            cursor = 0
            for missing_offset, (index, _, key) in enumerate(missing):
                count = len(fragments_by_text[missing_offset])
                pooled = np.average(
                    encoded[cursor : cursor + count],
                    axis=0,
                    weights=weights_by_text[missing_offset],
                )
                cursor += count
                norm = float(np.linalg.norm(pooled))
                if norm == 0.0:
                    raise ValueError("Retrieval embedding produced a zero vector")
                vector = np.asarray(pooled / norm, dtype=np.float32)
                vectors[index] = vector
                if role != "query" or self._cache_queries:
                    self._cache_set(key, vector)

        if any(vector is None for vector in vectors):
            raise AssertionError("Retrieval embedding assembly left a missing vector")
        matrix = np.vstack([vector for vector in vectors if vector is not None])
        return matrix, RetrievalEmbeddingStats(
            role=role,
            text_count=len(texts),
            cache_hits=cache_hits,
            cache_misses=len(missing),
            fragment_count=fragment_count,
        )

    def _fragment(self, text: str, prefix: str) -> list[str]:
        stripped = text.strip()
        if self._fits(stripped, prefix):
            return [stripped]
        sentences = [
            part.strip()
            for part in self._SENTENCE_BOUNDARY.split(stripped)
            if part.strip()
        ] or [stripped]
        fragments: list[str] = []
        current = ""
        for sentence in sentences:
            if not self._fits(sentence, prefix):
                if current:
                    fragments.append(current)
                    current = ""
                fragments.extend(self._split_oversized(sentence, prefix))
                continue
            candidate = sentence if not current else f"{current} {sentence}"
            if self._fits(candidate, prefix):
                current = candidate
            else:
                fragments.append(current)
                current = sentence
        if current:
            fragments.append(current)
        return fragments

    def _split_oversized(self, text: str, prefix: str) -> list[str]:
        prefix_cost = self._count(prefix, special=True)
        budget = self.model_input_limit - prefix_cost
        if budget < 1:
            raise ValueError("Retrieval prefix consumes model input limit")
        token_ids = self._tokenizer(
            text, add_special_tokens=False, truncation=False
        )["input_ids"]
        while budget >= 1:
            pieces = [
                self._tokenizer.decode(token_ids[start : start + budget]).strip()
                for start in range(0, len(token_ids), budget)
            ]
            pieces = [piece for piece in pieces if piece]
            if pieces and all(self._fits(piece, prefix) for piece in pieces):
                return pieces
            budget -= 1
        raise ValueError("Unable to split retrieval text under model input limit")

    def _fits(self, text: str, prefix: str) -> bool:
        return self._count(self._with_prefix(text, prefix), special=True) <= self.model_input_limit

    def _count(self, text: str, *, special: bool) -> int:
        return len(
            self._tokenizer(
                text, add_special_tokens=special, truncation=False
            )["input_ids"]
        )

    @staticmethod
    def _with_prefix(text: str, prefix: str) -> str:
        return text if text.startswith(prefix) else f"{prefix}{text}"

    def _cache_key(self, role: str, prefix: str, text: str) -> str:
        namespace = "|".join(
            (
                "retrieval",
                role,
                self.model_id,
                prefix,
                str(self.model_input_limit),
                self._POLICY_VERSION,
            )
        )
        return hashlib.sha256(f"{namespace}\0{text}".encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> np.ndarray | None:
        path = self._cache_dir / f"{key}.npy"
        if not path.exists():
            return None
        try:
            return np.asarray(np.load(path, allow_pickle=False), dtype=np.float32)
        except Exception:
            return None

    def _cache_set(self, key: str, vector: np.ndarray) -> None:
        destination = self._cache_dir / f"{key}.npy"
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".npy", dir=self._cache_dir, delete=False
        ) as handle:
            temporary = Path(handle.name)
            np.save(handle, np.asarray(vector, dtype=np.float32), allow_pickle=False)
        os.replace(temporary, destination)


@dataclass(frozen=True)
class RetrievalDocument:
    chunk_id: str
    text: str
    unit_ids: tuple[str, ...]
    pages: tuple[int, ...]
    token_count: int


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: str
    rank: int
    rrf_score: float
    dense_rank: int | None
    bm25_rank: int | None
    dense_score: float
    bm25_score: float


class DeterministicBM25:
    _WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)

    def __init__(self, texts: Sequence[str], *, k1: float, b: float) -> None:
        if k1 <= 0.0 or not 0.0 <= b <= 1.0:
            raise ValueError("Invalid BM25 parameters")
        self.k1 = k1
        self.b = b
        self.documents = [self.tokenize(text) for text in texts]
        self.lengths = np.asarray([len(tokens) for tokens in self.documents], dtype=np.float64)
        self.avgdl = float(np.mean(self.lengths)) if len(self.lengths) else 0.0
        self.term_frequencies = [Counter(tokens) for tokens in self.documents]
        document_frequency: Counter[str] = Counter()
        for tokens in self.documents:
            document_frequency.update(set(tokens))
        count = len(self.documents)
        self.idf = {
            term: math.log(1.0 + (count - df + 0.5) / (df + 0.5))
            for term, df in document_frequency.items()
        }

    @classmethod
    def tokenize(cls, text: str) -> list[str]:
        tokens: list[str] = []
        for match in cls._WORD.finditer(text):
            folded = unicodedata.normalize("NFKD", match.group(0).casefold())
            folded = folded.replace("\u0307", "")
            tokens.append(unicodedata.normalize("NFC", folded))
        return tokens

    def scores(self, query: str) -> np.ndarray:
        scores = np.zeros(len(self.documents), dtype=np.float64)
        if not len(scores) or self.avgdl == 0.0:
            return scores
        for term in self.tokenize(query):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for index, frequencies in enumerate(self.term_frequencies):
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (
                    1.0 - self.b + self.b * self.lengths[index] / self.avgdl
                )
                scores[index] += idf * frequency * (self.k1 + 1.0) / denominator
        return scores


class DeterministicHybridIndex:
    def __init__(
        self,
        *,
        documents: Sequence[RetrievalDocument],
        document_embeddings: np.ndarray,
        bm25_k1: float,
        bm25_b: float,
        rrf_rank_constant: int,
        dense_weight: float,
        bm25_weight: float,
        candidate_pool_size: int,
    ) -> None:
        if len(documents) != len(document_embeddings):
            raise ValueError("Document/embedding count mismatch")
        if rrf_rank_constant < 1 or candidate_pool_size < 1:
            raise ValueError("RRF constants must be positive")
        if dense_weight <= 0.0 or bm25_weight <= 0.0:
            raise ValueError("RRF weights must be positive")
        self.documents = tuple(documents)
        self.document_embeddings = np.asarray(document_embeddings, dtype=np.float32)
        self.bm25 = DeterministicBM25(
            [document.text for document in documents], k1=bm25_k1, b=bm25_b
        )
        self.rank_constant = rrf_rank_constant
        self.dense_weight = dense_weight
        self.bm25_weight = bm25_weight
        self.pool_size = min(candidate_pool_size, len(documents))

    def search(
        self,
        query: str,
        query_embedding: np.ndarray,
        *,
        top_k: int,
    ) -> list[RetrievalHit]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        dense_scores = self.document_embeddings @ np.asarray(query_embedding, dtype=np.float32)
        bm25_scores = self.bm25.scores(query)
        stable_ids = [document.chunk_id for document in self.documents]
        dense_order = sorted(
            range(len(self.documents)), key=lambda i: (-float(dense_scores[i]), stable_ids[i])
        )
        bm25_order = sorted(
            range(len(self.documents)), key=lambda i: (-float(bm25_scores[i]), stable_ids[i])
        )
        dense_rank = {index: rank for rank, index in enumerate(dense_order[: self.pool_size], start=1)}
        bm25_rank = {index: rank for rank, index in enumerate(bm25_order[: self.pool_size], start=1)}
        candidates = set(dense_rank) | set(bm25_rank)
        fused: list[tuple[int, float]] = []
        for index in candidates:
            score = 0.0
            if index in dense_rank:
                score += self.dense_weight / (self.rank_constant + dense_rank[index])
            if index in bm25_rank:
                score += self.bm25_weight / (self.rank_constant + bm25_rank[index])
            fused.append((index, score))
        fused.sort(
            key=lambda item: (
                -item[1],
                min(dense_rank.get(item[0], 10**9), bm25_rank.get(item[0], 10**9)),
                stable_ids[item[0]],
            )
        )
        return [
            RetrievalHit(
                chunk_id=stable_ids[index],
                rank=rank,
                rrf_score=score,
                dense_rank=dense_rank.get(index),
                bm25_rank=bm25_rank.get(index),
                dense_score=float(dense_scores[index]),
                bm25_score=float(bm25_scores[index]),
            )
            for rank, (index, score) in enumerate(fused[:top_k], start=1)
        ]
