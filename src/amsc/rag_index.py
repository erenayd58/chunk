"""One retrieval index per (document, chunking arm) for the RAG chat.

Dense + lexical + reciprocal-rank fusion, built on the same deterministic
pieces the retrieval benchmark uses -- :class:`DeterministicHybridIndex`
for the fusion and tie-breaks, the benchmark's Turkish diacritic fold for
BM25 -- so a ranking is a pure function of (chunks, model, question) and two
arms are compared under one retriever. Nothing here re-ranks, expands the
query or calls a generative model.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from .chunk_benchmark import FOLDS
from .rag_embeddings import CachedEmbeddings
from .retrieval_pipeline import DeterministicHybridIndex, RetrievalDocument, RetrievalHit


@dataclass(frozen=True)
class RetrievalSettings:
    top_k: int = 5
    candidate_pool: int = 50
    rrf_k: int = 60
    dense_weight: float = 1.0
    bm25_weight: float = 1.0
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    fold: str = "turkish_diacritics_v1"
    tuning_status: str = "poc_initial_not_optimized"

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any] | None) -> "RetrievalSettings":
        config = dict(config or {})
        bm25 = dict(config.pop("bm25", {}) or {})
        known = {k: v for k, v in config.items() if k in cls.__dataclass_fields__}
        for key, alias in (("k1", "bm25_k1"), ("b", "bm25_b"), ("fold", "fold")):
            if key in bm25:
                known[alias] = bm25[key]
        return cls(**known)


@dataclass(frozen=True)
class IndexedChunk:
    """The slice of a chunk row the chat needs, in index order."""

    index: int
    chunk_id: str
    text: str
    token_count: int
    pages: tuple[int, ...]
    heading: str | None
    section_path: tuple[str, ...]
    unit_ids: tuple[str, ...]
    #: A retrieval-only rendering of a table this chunk carries, when the
    #: chunker produced one. Never rendered into the answer context: ``text``
    #: remains the only thing a citation can point at.
    search_text: str | None = None

    @classmethod
    def from_row(cls, index: int, row: Mapping[str, Any]) -> "IndexedChunk":
        paths = row.get("section_paths") or []
        return cls(
            index=index,
            chunk_id=str(row["chunk_id"]),
            text=str(row.get("text") or ""),
            token_count=int(row.get("token_count") or 0),
            pages=tuple(int(p) for p in (row.get("pages") or [])),
            heading=row.get("heading"),
            section_path=tuple(paths[0]) if paths and paths[0] else (),
            unit_ids=tuple(str(u) for u in (row.get("unit_ids") or [])),
            search_text=str(row["search_text"]) if row.get("search_text") else None,
        )


@dataclass
class IndexStats:
    chunk_count: int
    build_seconds: float
    embedding_cache_hits: int
    embedding_cache_misses: int
    embedding_provider_calls: int
    dense: bool


@dataclass
class ChunkIndex:
    """The searchable form of one arm's ``chunks.jsonl``."""

    arm: str
    kind: str
    chunks: list[IndexedChunk]
    settings: RetrievalSettings
    embedder: CachedEmbeddings | None = None
    _index: DeterministicHybridIndex | None = field(default=None, repr=False)
    stats: IndexStats | None = None

    @property
    def dense(self) -> bool:
        return self.embedder is not None

    def build(self) -> "ChunkIndex":
        started = time.perf_counter()
        fold = FOLDS[self.settings.fold]
        # BM25 reads the table's rendering *in addition to* its markdown, so
        # nothing that matched before can stop matching. The dense leg reads it
        # *instead*: one vector cannot hold both a page of pipes and the
        # sentences derived from it, and the sentences are what a question
        # looks like.
        documents = [
            RetrievalDocument(
                chunk_id=chunk.chunk_id,
                text=fold(chunk.text if chunk.search_text is None
                          else chunk.text + "\n" + chunk.search_text),
                unit_ids=chunk.unit_ids,
                pages=chunk.pages,
                token_count=chunk.token_count,
            )
            for chunk in self.chunks
        ]
        hits = misses = calls = 0
        if self.embedder is not None:
            vectors = self.embedder.embed(
                [chunk.search_text or chunk.text for chunk in self.chunks]
            )
            usage = self.embedder.last_usage
            if usage is not None:
                hits, misses, calls = usage.cache_hits, usage.cache_misses, usage.provider_calls
        else:
            vectors = np.zeros((len(documents), 1), dtype=np.float32)
        self._index = DeterministicHybridIndex(
            documents=documents,
            document_embeddings=vectors,
            bm25_k1=self.settings.bm25_k1,
            bm25_b=self.settings.bm25_b,
            rrf_rank_constant=self.settings.rrf_k,
            # Without a dense leg every dense score is 0 and its rank order
            # is the stable chunk-id order; a negligible weight keeps the
            # fusion arithmetic identical while BM25 decides.
            dense_weight=self.settings.dense_weight if self.dense else 1e-9,
            bm25_weight=self.settings.bm25_weight,
            candidate_pool_size=self.settings.candidate_pool,
        )
        self.stats = IndexStats(
            chunk_count=len(self.chunks),
            build_seconds=round(time.perf_counter() - started, 3),
            embedding_cache_hits=hits,
            embedding_cache_misses=misses,
            embedding_provider_calls=calls,
            dense=self.dense,
        )
        return self

    def search(self, question: str, *, top_k: int | None = None) -> list[RetrievalHit]:
        if self._index is None:
            self.build()
        assert self._index is not None
        fold = FOLDS[self.settings.fold]
        if self.embedder is not None:
            query_vector = self.embedder.embed([question])[0]
        else:
            query_vector = np.zeros(1, dtype=np.float32)
        return self._index.search(
            fold(question), query_vector, top_k=top_k or self.settings.top_k
        )

    def by_id(self) -> dict[str, IndexedChunk]:
        return {chunk.chunk_id: chunk for chunk in self.chunks}


def index_rows(
    arm: str,
    kind: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    settings: RetrievalSettings,
    embedder: CachedEmbeddings | None,
) -> ChunkIndex:
    chunks = [IndexedChunk.from_row(index, row) for index, row in enumerate(rows)]
    return ChunkIndex(arm=arm, kind=kind, chunks=chunks, settings=settings, embedder=embedder).build()
