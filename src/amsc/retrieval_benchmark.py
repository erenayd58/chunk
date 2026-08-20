from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import time
from typing import Any, Literal, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
import yaml

from .evaluation import load_jsonl_objects, sha256_file
from .io import load_jsonl_units
from .legacy_chat_rag import (
    LegacyChatRAGCanonicalAdapter,
    LegacyChatRAGProfile,
)
from .models import RawDocumentUnit, UnitType
from .retrieval_pipeline import (
    DeterministicHybridIndex,
    E5RetrievalEmbedder,
    RetrievalDocument,
    RetrievalEmbeddingModel,
)
from .tokenization import TiktokenTokenCounter, TokenCounter


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BenchmarkIdentityConfig(_StrictModel):
    version: Literal["phase4-v1"]
    status: Literal["development_checkpoint"]


class BenchmarkSourceConfig(_StrictModel):
    units: str
    units_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gold_queries: str


class CandidateConfig(_StrictModel):
    kind: Literal["public_chat_rag_compatibility_adapter", "frozen_jsonl"]
    chunks: str | None = None
    source_repository: str | None = None
    source_commit: str | None = None
    profile: str | None = None
    chunk_size_words: int | None = Field(default=None, ge=1)
    chunk_overlap_words: int | None = Field(default=None, ge=0)
    min_chunk_size_words: int | None = Field(default=None, ge=1)
    sentence_tokenizer: Literal["deterministic_punctuation_span_v1"] | None = None
    use_semantic_segmentation: bool | None = None
    use_embedding_segmentation: bool | None = None

    @model_validator(mode="after")
    def validate_kind_fields(self) -> "CandidateConfig":
        if self.kind == "frozen_jsonl":
            if not self.chunks:
                raise ValueError("frozen_jsonl candidate requires chunks")
            legacy = (
                self.source_repository,
                self.source_commit,
                self.profile,
                self.chunk_size_words,
                self.chunk_overlap_words,
                self.min_chunk_size_words,
                self.sentence_tokenizer,
                self.use_semantic_segmentation,
                self.use_embedding_segmentation,
            )
            if any(value is not None for value in legacy):
                raise ValueError("frozen_jsonl candidate cannot contain legacy fields")
        else:
            required = (
                self.source_repository,
                self.source_commit,
                self.profile,
                self.chunk_size_words,
                self.chunk_overlap_words,
                self.min_chunk_size_words,
                self.sentence_tokenizer,
                self.use_semantic_segmentation,
                self.use_embedding_segmentation,
            )
            if any(value is None for value in required):
                raise ValueError("legacy candidate is missing profile fields")
            if self.chunks is not None:
                raise ValueError("legacy candidate chunks are generated, not configured")
        return self


class RetrievalEmbeddingConfig(_StrictModel):
    model: str
    revision: str | None = None
    device: str
    local_files_only: bool
    query_prefix: str
    document_prefix: str
    model_input_limit: int = Field(ge=1)
    overlength_strategy: Literal["sentence_fragment_token_weighted_pooling"]
    normalize_embeddings: bool
    cache_queries: Literal[False]
    batch_size: int = Field(ge=1)
    cache_dir: str


class BM25Config(_StrictModel):
    tokenizer: Literal["unicode_word_casefold_v1"]
    k1: float = Field(gt=0.0)
    b: float = Field(ge=0.0, le=1.0)


class RRFConfig(_StrictModel):
    rank_constant: int = Field(ge=1)
    dense_weight: float = Field(gt=0.0)
    bm25_weight: float = Field(gt=0.0)
    candidate_pool_size: int = Field(ge=1)


class RetrievalEvaluationConfig(_StrictModel):
    top_ks: list[int]
    latency_repetitions: int = Field(ge=1)
    token_counter_encoding: str

    @model_validator(mode="after")
    def validate_top_ks(self) -> "RetrievalEvaluationConfig":
        if self.top_ks != sorted(set(self.top_ks)) or not self.top_ks:
            raise ValueError("top_ks must be non-empty, unique, and sorted")
        if any(value < 1 for value in self.top_ks):
            raise ValueError("top_ks values must be positive")
        return self


class RetrievalBenchmarkConfig(_StrictModel):
    benchmark: BenchmarkIdentityConfig
    source: BenchmarkSourceConfig
    candidates: dict[str, CandidateConfig]
    retrieval_embedding: RetrievalEmbeddingConfig
    bm25: BM25Config
    rrf: RRFConfig
    evaluation: RetrievalEvaluationConfig

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RetrievalBenchmarkConfig":
        return cls.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))

    @model_validator(mode="after")
    def validate_candidates(self) -> "RetrievalBenchmarkConfig":
        if set(self.candidates) != {"legacy", "v3", "v4", "c3"}:
            raise ValueError("Phase 4 requires exactly legacy, v3, v4, and c3")
        return self


class RetrievalGoldQuery(_StrictModel):
    query_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    evidence_unit_ids: list[str] = Field(min_length=1)
    evidence_pages: list[int] = Field(min_length=1)
    expected_answer: str | None = None


class RetrievalGoldSet(_StrictModel):
    schema_version: Literal["1.0"]
    document_id: str
    source_units_file: str
    source_units_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    annotation_status: Literal["manual_development_checkpoint"]
    authoring_method: str
    queries: list[RetrievalGoldQuery] = Field(min_length=30, max_length=50)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "RetrievalGoldSet":
        ids = [query.query_id for query in self.queries]
        if len(ids) != len(set(ids)):
            raise ValueError("query_id values must be unique")
        return self


def run_retrieval_benchmark(
    *,
    config_path: str | Path,
    output_dir: str | Path,
    embedder: RetrievalEmbeddingModel | None = None,
    legacy_sentence_span_tokenizer: Any | None = None,
) -> dict[str, Any]:
    config_path = Path(config_path)
    config = RetrievalBenchmarkConfig.from_yaml(config_path)
    root = config_path.resolve().parent.parent
    output = Path(output_dir)
    if not output.is_absolute():
        output = root / output
    units_path = root / config.source.units
    gold_path = root / config.source.gold_queries
    if sha256_file(units_path) != config.source.units_sha256:
        raise ValueError("Frozen canonical units SHA256 mismatch")
    units = load_jsonl_units(units_path)
    gold = RetrievalGoldSet.model_validate_json(gold_path.read_text(encoding="utf-8"))
    _validate_gold(gold, units, config.source.units_sha256)
    token_counter = TiktokenTokenCounter(config.evaluation.token_counter_encoding)

    output.mkdir(parents=True, exist_ok=True)
    candidates = _load_candidates(
        root=root,
        output=output,
        config=config,
        units=units,
        token_counter=token_counter,
        legacy_sentence_span_tokenizer=legacy_sentence_span_tokenizer,
    )
    query_texts = [query.question for query in gold.queries]
    retrieval_embedder = embedder or E5RetrievalEmbedder.from_pretrained(
        config.retrieval_embedding.model,
        revision=config.retrieval_embedding.revision,
        device=config.retrieval_embedding.device,
        local_files_only=config.retrieval_embedding.local_files_only,
        query_prefix=config.retrieval_embedding.query_prefix,
        document_prefix=config.retrieval_embedding.document_prefix,
        model_input_limit=config.retrieval_embedding.model_input_limit,
        batch_size=config.retrieval_embedding.batch_size,
        cache_dir=root / config.retrieval_embedding.cache_dir,
        normalize_embeddings=config.retrieval_embedding.normalize_embeddings,
        cache_queries=config.retrieval_embedding.cache_queries,
    )

    query_start = time.perf_counter_ns()
    query_embeddings, query_embedding_stats = retrieval_embedder.embed_queries(query_texts)
    query_embedding_ms = (time.perf_counter_ns() - query_start) / 1_000_000.0

    unique_texts = list(
        dict.fromkeys(
            document.text
            for candidate_documents in candidates.values()
            for document in candidate_documents
        )
    )
    document_start = time.perf_counter_ns()
    unique_embeddings, document_embedding_stats = retrieval_embedder.embed_documents(
        unique_texts
    )
    document_embedding_ms = (time.perf_counter_ns() - document_start) / 1_000_000.0
    embedding_by_text = {
        text: unique_embeddings[index] for index, text in enumerate(unique_texts)
    }

    metrics_by_candidate: dict[str, dict[str, Any]] = {}
    input_shas: dict[str, str] = {}
    for candidate_id, documents in candidates.items():
        candidate_start = time.perf_counter_ns()
        document_embeddings = np.vstack(
            [embedding_by_text[document.text] for document in documents]
        )
        index = DeterministicHybridIndex(
            documents=documents,
            document_embeddings=document_embeddings,
            bm25_k1=config.bm25.k1,
            bm25_b=config.bm25.b,
            rrf_rank_constant=config.rrf.rank_constant,
            dense_weight=config.rrf.dense_weight,
            bm25_weight=config.rrf.bm25_weight,
            candidate_pool_size=config.rrf.candidate_pool_size,
        )
        index_build_ms = (time.perf_counter_ns() - candidate_start) / 1_000_000.0
        metrics_by_candidate[candidate_id] = _evaluate_candidate(
            candidate_id=candidate_id,
            documents=documents,
            index=index,
            gold=gold,
            units=units,
            query_embeddings=query_embeddings,
            top_ks=config.evaluation.top_ks,
            latency_repetitions=config.evaluation.latency_repetitions,
            token_counter=token_counter,
            output_dir=output / candidate_id,
            index_build_ms=index_build_ms,
            shared_query_embedding_per_query_ms=query_embedding_ms / len(gold.queries),
        )
        chunks_file = output / candidate_id / "chunks.jsonl"
        input_shas[candidate_id] = sha256_file(chunks_file)

    query_comparison, comparison_summary = _query_comparison(output, gold)
    _write_jsonl(output / "query-comparison.jsonl", query_comparison)
    summary = {
        "schema_version": "1.0",
        "benchmark_version": config.benchmark.version,
        "status": config.benchmark.status,
        "canonical_sha256": config.source.units_sha256,
        "gold_queries_sha256": sha256_file(gold_path),
        "query_count": len(gold.queries),
        "gold_evidence_profile": {
            "evidence_link_count": sum(
                len(query.evidence_unit_ids) for query in gold.queries
            ),
            "multi_unit_query_count": sum(
                len(query.evidence_unit_ids) > 1 for query in gold.queries
            ),
            "expected_answer_count": sum(
                query.expected_answer is not None for query in gold.queries
            ),
            "visual_evidence_link_count": sum(
                unit_id.startswith("v-")
                for query in gold.queries
                for unit_id in query.evidence_unit_ids
            ),
            "table_evidence_link_count": sum(
                unit_id.startswith("t-")
                for query in gold.queries
                for unit_id in query.evidence_unit_ids
            ),
            "list_evidence_link_count": sum(
                unit_id.startswith("l-")
                for query in gold.queries
                for unit_id in query.evidence_unit_ids
            ),
        },
        "retrieval_pipeline": {
            "model_id": retrieval_embedder.model_id,
            "model_input_limit": retrieval_embedder.model_input_limit,
            "query_prefix": config.retrieval_embedding.query_prefix,
            "document_prefix": config.retrieval_embedding.document_prefix,
            "overlength_strategy": config.retrieval_embedding.overlength_strategy,
            "bm25": config.bm25.model_dump(mode="json"),
            "rrf": config.rrf.model_dump(mode="json"),
            "query_expansion": False,
            "contextualization": False,
            "reranker": False,
            "token_counter_id": token_counter.counter_id,
        },
        "shared_embedding": {
            "query_total_ms": query_embedding_ms,
            "document_total_ms": document_embedding_ms,
            "unique_document_text_count": len(unique_texts),
            "query_stats": asdict(query_embedding_stats),
            "document_stats": asdict(document_embedding_stats),
        },
        "candidate_chunk_sha256": input_shas,
        "candidates": metrics_by_candidate,
        "query_comparison": comparison_summary,
        "interpretation_guardrail": (
            "C3 boundary ±1 F1=0.6667 is a development result, not evidence of "
            "semantic improvement; Phase 3C genuine semantic rescue count remained 0."
        ),
    }
    _write_json(output / "summary.json", summary)
    _write_json(output / "resolved-config.json", config.model_dump(mode="json"))
    _write_json(
        output / "manifest.json",
        {
            "config_sha256": sha256_file(config_path),
            "canonical_sha256": config.source.units_sha256,
            "gold_queries_sha256": sha256_file(gold_path),
            "gold_authoring_method": gold.authoring_method,
            "candidate_chunk_sha256": input_shas,
            "legacy_source_commit": config.candidates["legacy"].source_commit,
            "only_chunker_varies": True,
        },
    )
    (output / "retrieval-benchmark-report.md").write_text(
        _render_report(summary), encoding="utf-8", newline="\n"
    )
    return summary


def _load_candidates(
    *,
    root: Path,
    output: Path,
    config: RetrievalBenchmarkConfig,
    units: Sequence[RawDocumentUnit],
    token_counter: TokenCounter,
    legacy_sentence_span_tokenizer: Any | None,
) -> dict[str, list[RetrievalDocument]]:
    candidates: dict[str, list[RetrievalDocument]] = {}
    raw_by_id = {unit.unit_id: unit for unit in units}
    for candidate_id in ("legacy", "v3", "v4", "c3"):
        candidate = config.candidates[candidate_id]
        candidate_dir = output / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        if candidate.kind == "public_chat_rag_compatibility_adapter":
            profile = LegacyChatRAGProfile(
                source_repository=str(candidate.source_repository),
                source_commit=str(candidate.source_commit),
                profile_id=str(candidate.profile),
                chunk_size_words=int(candidate.chunk_size_words or 0),
                chunk_overlap_words=int(candidate.chunk_overlap_words or 0),
                min_chunk_size_words=int(candidate.min_chunk_size_words or 0),
                sentence_tokenizer=str(candidate.sentence_tokenizer),
                use_semantic_segmentation=bool(candidate.use_semantic_segmentation),
                use_embedding_segmentation=bool(candidate.use_embedding_segmentation),
            )
            adapter = LegacyChatRAGCanonicalAdapter(
                profile,
                token_counter,
                sentence_span_tokenizer=legacy_sentence_span_tokenizer,
            )
            rows = [record.as_dict() for record in adapter.build(units)]
            _write_json(
                candidate_dir / "legacy-compatibility.json",
                {
                    "profile": asdict(profile),
                    "compatibility_notes": list(adapter.compatibility_notes),
                },
            )
        else:
            rows = load_jsonl_objects(root / str(candidate.chunks))
        documents = [_to_document(row, raw_by_id, token_counter) for row in rows]
        _write_jsonl(candidate_dir / "chunks.jsonl", [_document_row(doc) for doc in documents])
        candidates[candidate_id] = documents
    return candidates


def _to_document(
    row: dict[str, Any],
    raw_by_id: dict[str, RawDocumentUnit],
    token_counter: TokenCounter,
) -> RetrievalDocument:
    text = str(row["text"])
    unit_ids = tuple(
        unit_id for unit_id in row.get("unit_ids", []) if unit_id in raw_by_id
    )
    if not unit_ids:
        unit_ids = tuple(
            unit_id
            for unit_id in row.get("content_unit_ids", [])
            if unit_id in raw_by_id
        )
    pages = tuple(
        sorted(
            {
                raw_by_id[unit_id].source.page
                for unit_id in unit_ids
                if raw_by_id[unit_id].source.page is not None
            }
        )
    )
    return RetrievalDocument(
        chunk_id=str(row["chunk_id"]),
        text=text,
        unit_ids=tuple(dict.fromkeys(unit_ids)),
        pages=pages,
        token_count=token_counter.count(text),
    )


def _document_row(document: RetrievalDocument) -> dict[str, Any]:
    return {
        "chunk_id": document.chunk_id,
        "text": document.text,
        "unit_ids": list(document.unit_ids),
        "pages": list(document.pages),
        "token_count": document.token_count,
    }


def _validate_gold(
    gold: RetrievalGoldSet,
    units: Sequence[RawDocumentUnit],
    canonical_sha: str,
) -> None:
    if gold.source_units_sha256 != canonical_sha:
        raise ValueError("Gold query source SHA does not match canonical input")
    if gold.document_id != units[0].document_id:
        raise ValueError("Gold query document_id mismatch")
    raw_by_id = {unit.unit_id: unit for unit in units}
    for query in gold.queries:
        if len(query.evidence_unit_ids) != len(set(query.evidence_unit_ids)):
            raise ValueError(f"{query.query_id} has duplicate evidence unit IDs")
        missing = [unit_id for unit_id in query.evidence_unit_ids if unit_id not in raw_by_id]
        if missing:
            raise ValueError(f"{query.query_id} references missing evidence: {missing}")
        if any(raw_by_id[unit_id].type == UnitType.HEADING for unit_id in query.evidence_unit_ids):
            raise ValueError(f"{query.query_id} evidence must be semantic content")
        actual_pages = sorted(
            {
                raw_by_id[unit_id].source.page
                for unit_id in query.evidence_unit_ids
                if raw_by_id[unit_id].source.page is not None
            }
        )
        if query.evidence_pages != actual_pages:
            raise ValueError(
                f"{query.query_id} evidence_pages {query.evidence_pages} != {actual_pages}"
            )


def _evaluate_candidate(
    *,
    candidate_id: str,
    documents: Sequence[RetrievalDocument],
    index: DeterministicHybridIndex,
    gold: RetrievalGoldSet,
    units: Sequence[RawDocumentUnit],
    query_embeddings: np.ndarray,
    top_ks: Sequence[int],
    latency_repetitions: int,
    token_counter: TokenCounter,
    output_dir: Path,
    index_build_ms: float,
    shared_query_embedding_per_query_ms: float,
) -> dict[str, Any]:
    by_id = {document.chunk_id: document for document in documents}
    unit_tokens = {unit.unit_id: token_counter.count(unit.text) for unit in units}
    max_k = max(top_ks)
    rows: list[dict[str, Any]] = []
    latency_ms: list[float] = []
    aggregates: dict[str, list[float]] = defaultdict(list)
    source_coverage: list[float] = []
    relevant_chunk_counts: list[float] = []
    minimum_cover_counts: list[float] = []

    for query_index, query in enumerate(gold.queries):
        hits = None
        repetitions: list[float] = []
        for _ in range(latency_repetitions):
            start = time.perf_counter_ns()
            current = index.search(
                query.question, query_embeddings[query_index], top_k=max_k
            )
            repetitions.append((time.perf_counter_ns() - start) / 1_000_000.0)
            if hits is None:
                hits = current
            elif current != hits:
                raise AssertionError("Deterministic retrieval returned different rankings")
        assert hits is not None
        latency_ms.append(statistics.median(repetitions))
        evidence = set(query.evidence_unit_ids)
        relevant_documents = [
            document for document in documents if evidence & set(document.unit_ids)
        ]
        covered_source = set().union(
            *(evidence & set(document.unit_ids) for document in relevant_documents)
        ) if relevant_documents else set()
        source_coverage.append(len(covered_source) / len(evidence))
        if relevant_documents:
            relevant_chunk_counts.append(float(len(relevant_documents)))
        minimum_cover = _minimum_evidence_cover(evidence, relevant_documents)
        if minimum_cover is not None:
            minimum_cover_counts.append(float(minimum_cover))

        result_rows: list[dict[str, Any]] = []
        first_relevant_rank: int | None = None
        for hit in hits:
            document = by_id[hit.chunk_id]
            matched = sorted(evidence & set(document.unit_ids))
            if matched and first_relevant_rank is None:
                first_relevant_rank = hit.rank
            result_rows.append(
                {
                    "rank": hit.rank,
                    "chunk_id": hit.chunk_id,
                    "rrf_score": hit.rrf_score,
                    "dense_rank": hit.dense_rank,
                    "bm25_rank": hit.bm25_rank,
                    "dense_score": hit.dense_score,
                    "bm25_score": hit.bm25_score,
                    "matched_evidence_unit_ids": matched,
                    "unit_ids": list(document.unit_ids),
                    "pages": list(document.pages),
                    "token_count": document.token_count,
                }
            )
        for top_k in top_ks:
            top_documents = [by_id[hit.chunk_id] for hit in hits[:top_k]]
            retrieved_evidence = set().union(
                *(evidence & set(document.unit_ids) for document in top_documents)
            ) if top_documents else set()
            aggregates[f"hit_at_{top_k}"].append(float(bool(retrieved_evidence)))
            aggregates[f"evidence_coverage_at_{top_k}"].append(
                len(retrieved_evidence) / len(evidence)
            )
            aggregates[f"irrelevant_token_ratio_at_{top_k}"].append(
                _irrelevant_token_ratio(top_documents, evidence, unit_tokens)
            )
        aggregates["mrr"].append(
            0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank
        )
        rows.append(
            {
                "query_id": query.query_id,
                "question": query.question,
                "evidence_unit_ids": query.evidence_unit_ids,
                "evidence_pages": query.evidence_pages,
                "expected_answer": query.expected_answer,
                "first_relevant_rank": first_relevant_rank,
                "source_evidence_coverage": source_coverage[-1],
                "evidence_fragment_count": len(relevant_documents),
                "minimum_evidence_cover_chunks": minimum_cover,
                "results": result_rows,
            }
        )

    metrics: dict[str, Any] = {
        "candidate_id": candidate_id,
        "query_count": len(gold.queries),
        "chunk_count": len(documents),
        "hit_at_1": _mean(aggregates["hit_at_1"]),
        "hit_at_3": _mean(aggregates["hit_at_3"]),
        "hit_at_5": _mean(aggregates["hit_at_5"]),
        "mrr": _mean(aggregates["mrr"]),
        "evidence_coverage_at_1": _mean(aggregates["evidence_coverage_at_1"]),
        "evidence_coverage_at_3": _mean(aggregates["evidence_coverage_at_3"]),
        "evidence_coverage_at_5": _mean(aggregates["evidence_coverage_at_5"]),
        "source_evidence_coverage": _mean(source_coverage),
        "evidence_fragmentation_mean_covered_queries": _mean(relevant_chunk_counts),
        "minimum_evidence_cover_chunks_mean": _mean(minimum_cover_counts),
        "retrieved_irrelevant_token_ratio_at_1": _mean(
            aggregates["irrelevant_token_ratio_at_1"]
        ),
        "retrieved_irrelevant_token_ratio_at_3": _mean(
            aggregates["irrelevant_token_ratio_at_3"]
        ),
        "retrieved_irrelevant_token_ratio_at_5": _mean(
            aggregates["irrelevant_token_ratio_at_5"]
        ),
        "latency": {
            "index_build_ms": index_build_ms,
            "search_median_ms": statistics.median(latency_ms),
            "search_p90_ms": _percentile(latency_ms, 0.90),
            "shared_query_embedding_per_query_ms": shared_query_embedding_per_query_ms,
            "estimated_end_to_end_median_ms": (
                statistics.median(latency_ms) + shared_query_embedding_per_query_ms
            ),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_dir / "query-results.jsonl", rows)
    _write_json(output_dir / "metrics.json", metrics)
    return metrics


def _minimum_evidence_cover(
    evidence: set[str], documents: Sequence[RetrievalDocument]
) -> int | None:
    if not evidence:
        return 0
    masks = [evidence & set(document.unit_ids) for document in documents]
    masks = [mask for mask in masks if mask]
    reachable: dict[frozenset[str], int] = {frozenset(): 0}
    for mask in masks:
        updated = dict(reachable)
        for covered, count in reachable.items():
            combined = frozenset(set(covered) | mask)
            updated[combined] = min(updated.get(combined, 10**9), count + 1)
        reachable = updated
    return reachable.get(frozenset(evidence))


def _query_comparison(
    output: Path, gold: RetrievalGoldSet
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidate_rows = {
        candidate_id: {
            row["query_id"]: row
            for row in load_jsonl_objects(output / candidate_id / "query-results.jsonl")
        }
        for candidate_id in ("legacy", "v3", "v4", "c3")
    }
    rows: list[dict[str, Any]] = []
    for query in gold.queries:
        candidates: dict[str, Any] = {}
        for candidate_id in ("legacy", "v3", "v4", "c3"):
            rank = candidate_rows[candidate_id][query.query_id]["first_relevant_rank"]
            candidates[candidate_id] = {
                "first_relevant_rank": rank,
                "hit_at_1": rank is not None and rank <= 1,
                "hit_at_3": rank is not None and rank <= 3,
                "hit_at_5": rank is not None and rank <= 5,
                "source_evidence_coverage": candidate_rows[candidate_id][query.query_id][
                    "source_evidence_coverage"
                ],
            }
        rows.append(
            {
                "query_id": query.query_id,
                "question": query.question,
                "evidence_unit_ids": query.evidence_unit_ids,
                "candidates": candidates,
            }
        )

    def hit_ids(candidate_id: str, top_k: int) -> set[str]:
        return {
            row["query_id"]
            for row in rows
            if row["candidates"][candidate_id][f"hit_at_{top_k}"]
        }

    c3_at_5 = hit_ids("c3", 5)
    v3_at_5 = hit_ids("v3", 5)
    v4_at_5 = hit_ids("v4", 5)
    return rows, {
        "c3_vs_v3_hit_at_5_gained": sorted(c3_at_5 - v3_at_5),
        "c3_vs_v3_hit_at_5_lost": sorted(v3_at_5 - c3_at_5),
        "v4_vs_v3_hit_at_5_gained": sorted(v4_at_5 - v3_at_5),
        "v4_vs_v3_hit_at_5_lost": sorted(v3_at_5 - v4_at_5),
        "missed_by_all_at_5": sorted(
            set(query.query_id for query in gold.queries)
            - hit_ids("legacy", 5)
            - v3_at_5
            - v4_at_5
            - c3_at_5
        ),
    }


def _irrelevant_token_ratio(
    documents: Sequence[RetrievalDocument],
    evidence: set[str],
    unit_tokens: dict[str, int],
) -> float:
    total = sum(document.token_count for document in documents)
    if total == 0:
        return 0.0
    evidence_tokens = 0
    for document in documents:
        matched_tokens = sum(
            unit_tokens[unit_id]
            for unit_id in evidence & set(document.unit_ids)
        )
        evidence_tokens += min(document.token_count, matched_tokens)
    return max(0.0, min(1.0, (total - evidence_tokens) / total))


def _mean(values: Sequence[float]) -> float:
    return float(statistics.mean(values)) if values else 0.0


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Phase 4 — KKB Retrieval Benchmark",
        "",
        "Bu development benchmark'ında parser/input ve retrieval hattı sabittir; yalnız chunker değişir.",
        "Query expansion, contextualization ve reranker kapalıdır. Dense retrieval, BM25 ve deterministic RRF tüm adaylarda aynıdır.",
        "",
        "| Chunker | Chunks | Hit@1 | Hit@3 | Hit@5 | MRR | Evidence coverage@5 | Source coverage | Fragmentation* | Irrelevant tokens@5 | Search p50 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {"legacy": "Legacy chat_rag", "v3": "V3", "v4": "A4 / V4", "c3": "C3"}
    for candidate_id in ("legacy", "v3", "v4", "c3"):
        metric = summary["candidates"][candidate_id]
        lines.append(
            "| {label} | {chunks} | {h1:.4f} | {h3:.4f} | {h5:.4f} | {mrr:.4f} | {cov:.4f} | {source:.4f} | {frag:.3f} | {irr:.4f} | {lat:.3f} |".format(
                label=labels[candidate_id],
                chunks=metric["chunk_count"],
                h1=metric["hit_at_1"],
                h3=metric["hit_at_3"],
                h5=metric["hit_at_5"],
                mrr=metric["mrr"],
                cov=metric["evidence_coverage_at_5"],
                source=metric["source_evidence_coverage"],
                frag=metric["evidence_fragmentation_mean_covered_queries"],
                irr=metric["retrieved_irrelevant_token_ratio_at_5"],
                lat=metric["latency"]["search_median_ms"],
            )
        )
    lines.extend(
        [
            "",
            "`Fragmentation*` yalnız gold evidence'ı candidate corpus'ta bulunan sorular üzerinde hesaplanır.",
            "Bu ilk gold sette her soru tek canonical evidence unit'e bağlıdır; bu nedenle evidence coverage Hit@K ile aynı, fragmentation ise ağırlıkla overlap/duplicate-fragment etkisini gösterir.",
            "",
            "## Query-level farklar",
            "",
            f"- C3'ün V3'e göre Hit@5 kazandığı sorular: {', '.join(summary['query_comparison']['c3_vs_v3_hit_at_5_gained']) or 'yok'}",
            f"- C3'ün V3'e göre Hit@5 kaybettiği sorular: {', '.join(summary['query_comparison']['c3_vs_v3_hit_at_5_lost']) or 'yok'}",
            f"- V4'ün V3'e göre Hit@5 kazandığı sorular: {', '.join(summary['query_comparison']['v4_vs_v3_hit_at_5_gained']) or 'yok'}",
            f"- V4'ün V3'e göre Hit@5 kaybettiği sorular: {', '.join(summary['query_comparison']['v4_vs_v3_hit_at_5_lost']) or 'yok'}",
            "",
            "## Yorumlama sınırı",
            "",
            summary["interpretation_guardrail"],
            "C3'ün `0.6667` boundary F1 değeri semantic improvement olarak yorumlanamaz; genuine semantic rescue sayısı `0` olarak kalmıştır.",
            "",
            "Legacy satırı KKB production agentic chunker değildir. Public `MurselTasgin/chat_rag` kodunun pinlenmiş code-default davranışını frozen canonical input üzerinde çalıştıran compatibility adapter'dır.",
            "Public legacy akışının kısa section'ları düşürme davranışı frozen canonical heading'lerle birlikte evidence kaybı üretmiştir. Bu nedenle legacy retrieval skoru production KKB legacy sistemine genellenemez.",
            "",
            "## Metric tanımları",
            "",
            "- `Hit@K`: İlk K sonuçta en az bir gold evidence unit bulunan soru oranı.",
            "- `MRR`: İlk evidence-bearing chunk sırasının reciprocal rank ortalaması.",
            "- `Evidence coverage@K`: İlk K sonuçta kapsanan gold evidence unit oranı.",
            "- `Fragmentation`: Gold evidence ile kesişen corpus chunk sayısının soru başına ortalaması; overlap da bu değeri artırır.",
            "- `Irrelevant tokens@K`: İlk K chunk tokenlarından gold evidence unit tokenlarına atfedilemeyen kısmın oranı.",
            "- Latency: Query embedding ortak olarak bir kez ölçülür; tabloda candidate-specific dense+BM25+RRF arama medyanı gösterilir.",
            "",
            "Bu veri seti KKB development checkpoint'idir; sonuçlar ikinci doküman/holdout olmadan validated production sonucu değildir.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )
