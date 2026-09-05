"""Compare three chunking methods on time and on quality, nothing else varying.

The frozen Phase 4/5 harness answers a different question -- it is locked to the
``{legacy, v3, v4, c3}`` candidate set (``retrieval_benchmark.py:155``), measures
time only at search, and has no chunker-agnostic structural layer. This module
is the missing one. What it does *not* do is re-implement the metrics: Hit@K,
MRR, evidence coverage, fragmentation and the irrelevant-token ratio all come
from :func:`amsc.retrieval_benchmark._evaluate_candidate`, imported and called
unchanged, so a number here means exactly what the same number means there.

Reusing that function is not free, and each condition below is load-bearing:

* the index must return :class:`amsc.retrieval_pipeline.RetrievalHit`. The
  determinism assertion compares two separately built hit lists with ``!=``
  once per repetition, and a hand-rolled hit class without ``__eq__`` fails on
  the first query.
* ``top_ks`` must be exactly ``[1, 3, 5]``. The metric dict hardcodes those nine
  keys and ``_mean([])`` returns ``0.0``, so any other value yields a silent
  zero that reads like a catastrophic result.
* ranks are cast to ``int`` and scores to ``float``; ``numpy.int64`` breaks
  ``json.dumps``.
* ``documents`` is passed separately, because relevance is derived from it
  rather than from the index.

Three things in that module are *not* reusable and are re-written here:
``_query_comparison`` and ``_render_report`` hardcode the four frozen candidate
names, and ``RetrievalBenchmarkConfig`` rejects any other candidate set.

Retrieval is BM25 only, reproducing the production ``BM25OnlyRetriever``: the
frozen :class:`amsc.retrieval_pipeline.DeterministicBM25` over a Turkish
diacritic fold, ties broken by ``chunk_id``. No dense leg, no reranker, no query
expansion. It is identical across the three arms, so the only variable is the
chunker.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import statistics
import tempfile
import time
from typing import Any, Literal, Mapping, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
import yaml

from . import chunk_quality, chunk_viewer, methods
from .cache import FileEmbeddingCache
from .chunk_mapping import base_unit_id, map_chunks
from .config import V4Config
from .embeddings import CachedSemanticBoundaryEmbedder, SentenceTransformerBoundaryEmbedder
from .evaluation import load_jsonl_objects, sha256_file
from .io import load_jsonl_units
from .models import RawDocumentUnit, UnitType
from .retrieval_benchmark import (
    RetrievalGoldSet,
    _evaluate_candidate,
    _to_document,
    _validate_gold,
    _write_json,
    _write_jsonl,
)
from .retrieval_pipeline import DeterministicBM25, RetrievalDocument, RetrievalHit
from .tokenization import TiktokenTokenCounter, TokenCounter

#: The compared arms: the registry's benchmark arms, in the benchmark's own
#: order. The set is a contract of the frozen checkpoint (see
#: ``validate_arms``); the *dispatch* of each arm's kind is the registry's.
ARMS = methods.benchmark_arms()
LABELS = {
    "markdown": "Markdown (size-first)",
    "hybrid": "Hybrid (structure + H1)",
    "structure-only": "Structure-only",
}

#: Reproduces ``chat_rag.components.retriever.bm25_only_retriever``'s production
#: fold. A reversible character fold applied identically to documents at index
#: time and to the query at search time, so a query typed without Turkish
#: diacritics still matches. Deliberately not stemming.
_TURKISH_FOLD = str.maketrans(
    {
        "ç": "c", "Ç": "c",
        "ğ": "g", "Ğ": "g",
        "ı": "i", "I": "i", "İ": "i", "i": "i",
        "ö": "o", "Ö": "o",
        "ş": "s", "Ş": "s",
        "ü": "u", "Ü": "u",
        "â": "a", "Â": "a", "î": "i", "Î": "i", "û": "u", "Û": "u",
    }
)


def fold_turkish(text: str) -> str:
    return text.translate(_TURKISH_FOLD).lower()


def identity_fold(text: str) -> str:
    return text


FOLDS = {"turkish_diacritics_v1": fold_turkish, "none": identity_fold}


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BenchmarkIdentity(_Strict):
    version: Literal["chunk-benchmark-v1"]
    status: Literal["development_checkpoint", "holdout_validation_checkpoint"]
    # Which canonical extraction the arms chunk. Two runs are only comparable
    # when this matches, so it is recorded rather than inferred from the path.
    canonical_profile: Literal["v1-frozen", "v2-repaired", "v3-semantic"] = "v1-frozen"


class SourceConfig(_Strict):
    units: str
    units_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gold_queries: str
    secondary_gold_queries: str | None = None
    document_pdf: str | None = None
    layout_profile: str | None = None


class ArmConfig(_Strict):
    #: A registered partition method's kind (``amsc.methods``). Validated
    #: against the registry rather than a literal list, so a new method is
    #: benchmarkable the moment it is registered.
    kind: str
    chunk_size_tokens: int | None = Field(default=None, ge=1)
    chunk_overlap_tokens: int | None = Field(default=None, ge=0)
    #: Take the section decision from the canonical's ``opens_section`` rather
    #: than opening at every heading. Meaningless for the markdown arm, which
    #: has no section machine at all.
    respect_semantic_roles: bool = False

    @model_validator(mode="after")
    def validate_kind_fields(self) -> "ArmConfig":
        try:
            method = methods.by_kind(self.kind)
        except methods.UnknownMethod as unknown:
            raise ValueError(str(unknown)) from None
        if method.partition is None:
            raise ValueError(f"{self.kind} is an orchestration, not a benchmark arm")
        sizing = (self.chunk_size_tokens, self.chunk_overlap_tokens)
        if method.sized:
            if any(value is None for value in sizing):
                raise ValueError(f"{self.kind} needs chunk_size and chunk_overlap")
            if self.respect_semantic_roles:
                raise ValueError(f"{self.kind} has no section machine to inform")
        elif any(value is not None for value in sizing):
            raise ValueError(f"{self.kind} takes its sizes from the shared token budget")
        return self


class AppendixConfig(_Strict):
    kind: Literal["frozen_jsonl"]
    chunks: str


class TokenBudget(_Strict):
    min_tokens: int = Field(ge=1)
    target_tokens: int = Field(ge=1)
    soft_max_tokens: int = Field(ge=1)
    hard_max_tokens: int = Field(ge=1)


class BM25Config(_Strict):
    k1: float = Field(gt=0.0)
    b: float = Field(ge=0.0, le=1.0)
    fold: Literal["turkish_diacritics_v1", "none"]


class BoundaryEmbeddingConfig(_Strict):
    #: Read-only reference to the frozen V4 settings. The config object is never
    #: extended: chat_rag's ``frozen_v4_chunker`` raises at runtime on hash drift.
    config: str


class EvaluationConfig(_Strict):
    top_ks: list[int]
    latency_repetitions: int = Field(ge=1)
    chunking_repetitions: int = Field(ge=1)
    token_counter_encoding: str

    @model_validator(mode="after")
    def validate_top_ks(self) -> "EvaluationConfig":
        if self.top_ks != [1, 3, 5]:
            raise ValueError(
                "top_ks must be exactly [1, 3, 5]: the reused metric function "
                "hardcodes those keys and returns 0.0 for anything else"
            )
        return self


class ChunkBenchmarkConfig(_Strict):
    benchmark: BenchmarkIdentity
    source: SourceConfig
    arms: dict[str, ArmConfig]
    tokens: TokenBudget
    bm25: BM25Config
    evaluation: EvaluationConfig
    boundary_embedding: BoundaryEmbeddingConfig
    appendix: dict[str, AppendixConfig] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ChunkBenchmarkConfig":
        return cls.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))

    @model_validator(mode="after")
    def validate_arms(self) -> "ChunkBenchmarkConfig":
        if set(self.arms) != set(ARMS):
            raise ValueError(f"the compared arms are exactly {list(ARMS)}")
        return self


# ---------------------------------------------------------------------------
# retrieval
# ---------------------------------------------------------------------------


class BM25OnlyIndex:
    """Lexical-only index with the production retriever's semantics.

    ``search`` keeps the frozen evaluator's signature and ignores the query
    vector: this profile has no dense leg. ``rrf_score`` carries the BM25 score
    because the frozen hit type names it that; nothing fuses here.
    """

    def __init__(
        self,
        documents: Sequence[RetrievalDocument],
        *,
        k1: float,
        b: float,
        fold: str,
    ) -> None:
        self.documents = tuple(documents)
        self._fold = FOLDS[fold]
        self._ids = [document.chunk_id for document in self.documents]
        self.bm25 = DeterministicBM25(
            [self._fold(document.text) for document in self.documents], k1=k1, b=b
        )

    def search(
        self, query: str, query_embedding: Any = None, *, top_k: int
    ) -> list[RetrievalHit]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        scores = self.bm25.scores(self._fold(query))
        order = sorted(
            range(len(self.documents)),
            key=lambda index: (-float(scores[index]), self._ids[index]),
        )
        return [
            RetrievalHit(
                chunk_id=self._ids[index],
                rank=int(rank),
                rrf_score=float(scores[index]),
                dense_rank=None,
                bm25_rank=int(rank),
                dense_score=0.0,
                bm25_score=float(scores[index]),
            )
            for rank, index in enumerate(order[:top_k], start=1)
        ]


def normalize_unit_ids_for_retrieval(row: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce a chunk's ``unit_ids`` to canonical ids, keeping the originals.

    ``_to_document`` filters ``unit_ids`` against the canonical corpus, so a
    fragment id like ``t-00186#f2`` is silently dropped. Measured on the frozen
    2024 corpus, that leaves 15 structure-first chunks with *no* unit ids at all:
    they can never count as a hit however well their text answers the question,
    and their page list empties too. The eight units affected are the document's
    largest tables, which is exactly where the benchmark is hardest.

    So the ids are reduced here, in the open, and the fragment-qualified list is
    kept under ``fragment_unit_ids`` for the mapping and the viewer. The frozen
    function is not touched.
    """
    normalized = dict(row)
    original = [str(unit_id) for unit_id in row.get("unit_ids") or []]
    reduced: list[str] = []
    for unit_id in original:
        base = base_unit_id(unit_id)
        if base not in reduced:
            reduced.append(base)
    normalized["unit_ids"] = reduced
    if any("#" in unit_id for unit_id in original):
        normalized["fragment_unit_ids"] = original
    return normalized


def to_documents(
    rows: Sequence[Mapping[str, Any]],
    units: Sequence[RawDocumentUnit],
    counter: TokenCounter,
    *,
    mapping: Any | None = None,
) -> list[RetrievalDocument]:
    """Convert chunk rows for the frozen evaluator, refusing unscorable content.

    A document with no unit ids can never count as a hit. That is a defect when
    the chunk carries content -- the fragment-id bug this benchmark exists to
    avoid -- and correct when it does not: a size-first splitter really can emit
    a chunk made only of consecutive headings (a run of board-member names, a
    row of product titles), and such a chunk answers nothing, so scoring it
    zero is the right answer rather than a measurement error. The two cases are
    told apart by the mapping, not by the chunk's own bookkeeping.
    """
    raw_by_id = {unit.unit_id: unit for unit in units}
    documents = [_to_document(dict(row), raw_by_id, counter) for row in rows]
    if mapping is None:
        return documents

    by_chunk = {chunk.chunk_id: chunk for chunk in mapping.chunks}
    unscorable: list[str] = []
    for document in documents:
        if document.unit_ids:
            continue
        mapped = by_chunk.get(document.chunk_id)
        carries_content = mapped is not None and any(
            raw_by_id[segment.unit_id].type != UnitType.HEADING
            for segment in mapped.segments
            if segment.unit_id in raw_by_id
        )
        if carries_content or mapped is None:
            unscorable.append(document.chunk_id)
    if unscorable:
        raise AssertionError(
            "chunks that carry content but no canonical unit ids can never be "
            f"scored: {unscorable[:5]} ({len(unscorable)} total)"
        )
    return documents


# ---------------------------------------------------------------------------
# arms
# ---------------------------------------------------------------------------


def build_boundary_embedder(root: Path, config_path: str) -> Any:
    """The frozen V4 boundary embedder, read from its config without changing it."""
    settings = V4Config.from_yaml(root / config_path).boundary_embedding
    cache_dir = settings.cache_dir
    if not Path(cache_dir).is_absolute():
        cache_dir = root / cache_dir
    delegate = SentenceTransformerBoundaryEmbedder.from_pretrained(
        settings.model,
        revision=settings.revision,
        device=settings.device,
        prefix=settings.prefix,
        prefix_policy=settings.prefix_policy,
        max_input_tokens_override=settings.max_input_tokens_override,
        normalize_embeddings=settings.normalize_embeddings,
    )
    return CachedSemanticBoundaryEmbedder(delegate, FileEmbeddingCache(cache_dir))


def run_arm(
    arm: str,
    config: ChunkBenchmarkConfig,
    units: Sequence[RawDocumentUnit],
    counter: TokenCounter,
    *,
    boundary_embedder: Any | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], Mapping[str, tuple[int, int]] | None]:
    """Produce one arm's chunks, its diagnostics and its rendered unit spans.

    Dispatch is the registry's: the arm's ``kind`` names a registered
    partition method and :func:`amsc.methods.partition` runs it. Nothing here
    knows which engine is which; a registered method is a benchmarkable one.
    """
    settings = config.arms[arm]
    method = methods.by_kind(settings.kind)
    options: dict[str, Any] = {}
    if method.sized:
        options = {
            "chunk_size_tokens": int(settings.chunk_size_tokens or 0),
            "chunk_overlap_tokens": int(settings.chunk_overlap_tokens or 0),
        }
    result = methods.partition(
        method.key,
        units,
        counter=counter,
        budget=config.tokens.model_dump(),
        boundary_embedder=boundary_embedder,
        respect_semantic_roles=settings.respect_semantic_roles,
        **options,
    )
    diagnostics = dict(result.diagnostics)
    if method.sized:
        # The benchmark's own note about the sizes it froze; the engine does
        # not know it is being benchmarked.
        diagnostics["size_configuration_note"] = (
            "Frozen for this benchmark so every arm shares one token "
            "budget; not a reproduction of any library default."
        )
    return result.rows, diagnostics, result.spans


def time_arm(
    arm: str,
    config: ChunkBenchmarkConfig,
    units: Sequence[RawDocumentUnit],
    counter: TokenCounter,
    *,
    boundary_embedder: Any | None,
    repetitions: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], Mapping[str, tuple[int, int]] | None, list[float]]:
    """Run the arm ``repetitions`` times, asserting it produced the same corpus."""
    samples: list[float] = []
    reference: list[dict[str, Any]] | None = None
    rows: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {}
    spans: Mapping[str, tuple[int, int]] | None = None
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        rows, diagnostics, spans = run_arm(
            arm, config, units, counter, boundary_embedder=boundary_embedder
        )
        samples.append((time.perf_counter_ns() - start) / 1_000_000.0)
        if reference is None:
            reference = rows
        elif rows != reference:
            raise AssertionError(f"{arm} chunking is not deterministic")
    return rows, diagnostics, spans, samples


# ---------------------------------------------------------------------------
# comparison across arms
# ---------------------------------------------------------------------------


def arm_comparison(
    output: Path, gold: RetrievalGoldSet, arms: Sequence[str] = ARMS
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Per-query ranks side by side, plus who gained and lost against whom."""
    by_arm = {
        arm: {
            row["query_id"]: row
            for row in load_jsonl_objects(output / arm / "query-results.jsonl")
        }
        for arm in arms
    }
    rows: list[dict[str, Any]] = []
    for query in gold.queries:
        entry: dict[str, Any] = {}
        for arm in arms:
            rank = by_arm[arm][query.query_id]["first_relevant_rank"]
            entry[arm] = {
                "first_relevant_rank": rank,
                "hit_at_1": rank is not None and rank <= 1,
                "hit_at_3": rank is not None and rank <= 3,
                "hit_at_5": rank is not None and rank <= 5,
                "source_evidence_coverage": by_arm[arm][query.query_id][
                    "source_evidence_coverage"
                ],
            }
        rows.append(
            {
                "query_id": query.query_id,
                "question": query.question,
                "evidence_unit_ids": query.evidence_unit_ids,
                "evidence_type": query.evidence_type,
                "difficulty": query.difficulty,
                "arms": entry,
            }
        )

    def hits(arm: str, top_k: int) -> set[str]:
        return {row["query_id"] for row in rows if row["arms"][arm][f"hit_at_{top_k}"]}

    pairwise: dict[str, Any] = {}
    for left in arms:
        for right in arms:
            if left >= right:
                continue
            gained = sorted(hits(left, 5) - hits(right, 5))
            lost = sorted(hits(right, 5) - hits(left, 5))
            pairwise[f"{left}_vs_{right}_hit_at_5"] = {"gained": gained, "lost": lost}

    covered: set[str] = set()
    for arm in arms:
        covered |= hits(arm, 5)
    return rows, {
        "pairwise_hit_at_5": pairwise,
        "missed_by_all_at_5": sorted(
            {query.query_id for query in gold.queries} - covered
        ),
    }


def by_evidence_type(
    rows: Sequence[Mapping[str, Any]], arms: Sequence[str] = ARMS
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row.get("evidence_type") or "unlabelled"
        bucket = grouped.setdefault(key, {"query_count": 0, **{arm: 0 for arm in arms}})
        bucket["query_count"] += 1
        for arm in arms:
            bucket[arm] += int(bool(row["arms"][arm]["hit_at_5"]))
    return dict(sorted(grouped.items()))


# ---------------------------------------------------------------------------
# parse timing (shared, not attributed to an arm)
# ---------------------------------------------------------------------------


def measure_parse(
    root: Path, source: SourceConfig, canonical_profile: str = "v1-frozen"
) -> dict[str, Any]:
    """Time PDF -> canonical units under the profile the arms actually chunk.

    Identical for all three arms by construction, so it is reported once as a
    shared constant. Timing a *different* extraction from the one the corpus
    came out of would be a number about nothing, so the profile is taken from
    the benchmark config rather than fixed here.
    """
    if not source.document_pdf:
        return {"measured": False, "reason": "no document_pdf configured"}
    pdf = root / source.document_pdf
    if not pdf.is_file():
        return {"measured": False, "reason": f"missing {source.document_pdf}"}
    from .prepare_full_checkpoint import (
        CANONICAL_PROFILES,
        extract_full_canonical_units,
    )

    profile = str(root / source.layout_profile) if source.layout_profile else None
    repairs = CANONICAL_PROFILES[canonical_profile]
    start = time.perf_counter_ns()
    extraction = extract_full_canonical_units(
        input_path=pdf,
        layout_profile_path=profile,
        **repairs,
    )
    elapsed = (time.perf_counter_ns() - start) / 1_000_000.0
    return {
        "measured": True,
        "parse_ms": elapsed,
        "unit_count": len(extraction.units),
        "page_count": extraction.page_count,
        "canonical_profile": canonical_profile,
        "repairs": dict(sorted(repairs.items())),
        "note": (
            "Shared by every arm and not attributed to one. Measured under the "
            "same canonical profile the arms chunk, so parse time and corpus "
            "describe one pipeline."
        ),
    }


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------


def _guard_output(config_path: Path, root: Path, output: Path, config: ChunkBenchmarkConfig) -> None:
    resolved = output.resolve()
    if (root / "evaluation").resolve() in (resolved, *resolved.parents):
        raise ValueError("refusing to write into evaluation/: those artifacts are frozen")
    inputs = [config.source.units, config.source.gold_queries]
    inputs += [entry.chunks for entry in config.appendix.values()]
    if config.source.secondary_gold_queries:
        inputs.append(config.source.secondary_gold_queries)
    for relative in inputs:
        candidate = (root / relative).resolve()
        if resolved in (candidate, *candidate.parents):
            raise ValueError(
                f"refusing an output directory that contains an input: {relative}"
            )


def measure_cold_embedding(
    root: Path,
    config: ChunkBenchmarkConfig,
    units: Sequence[RawDocumentUnit],
    counter: TokenCounter,
    arm: str = "hybrid",
) -> dict[str, Any]:
    """Time an embedding arm against an empty embedding cache.

    Cold and warm only differ for an arm that loads a model (the registry's
    ``needs_embedder``); the others are reported as ``cold_equals_warm``. The
    temporary cache keeps the shared ``.cache/boundary-embeddings`` -- which
    the frozen V1-V4 runs also use -- untouched.
    """
    with tempfile.TemporaryDirectory(prefix="amsc-cold-") as temporary:
        settings = V4Config.from_yaml(root / config.boundary_embedding.config)
        embedding = settings.boundary_embedding
        delegate = SentenceTransformerBoundaryEmbedder.from_pretrained(
            embedding.model,
            revision=embedding.revision,
            device=embedding.device,
            prefix=embedding.prefix,
            prefix_policy=embedding.prefix_policy,
            max_input_tokens_override=embedding.max_input_tokens_override,
            normalize_embeddings=embedding.normalize_embeddings,
        )
        cold = CachedSemanticBoundaryEmbedder(delegate, FileEmbeddingCache(temporary))
        start = time.perf_counter_ns()
        result = methods.partition(
            arm,
            units,
            counter=counter,
            budget=config.tokens.model_dump(),
            boundary_embedder=cold,
        )
        elapsed = (time.perf_counter_ns() - start) / 1_000_000.0
    return {
        "chunk_ms_cold": elapsed,
        "embedded_piece_count": result.diagnostics.get("embedded_piece_count"),
        "note": (
            "Empty embedding cache, model already loaded. Written to a temporary "
            "directory so the shared boundary-embedding cache is not disturbed."
        ),
    }


def run_benchmark(
    *,
    config_path: str | Path,
    output_dir: str | Path,
    boundary_embedder: Any | None = None,
    measure_parse_time: bool = True,
    measure_cold_embedding_time: bool = True,
) -> dict[str, Any]:
    config_path = Path(config_path)
    config = ChunkBenchmarkConfig.from_yaml(config_path)
    root = config_path.resolve().parent.parent
    output = Path(output_dir)
    if not output.is_absolute():
        output = root / output
    _guard_output(config_path, root, output, config)

    units_path = root / config.source.units
    if sha256_file(units_path) != config.source.units_sha256:
        raise ValueError("Frozen canonical units SHA256 mismatch")
    units = load_jsonl_units(units_path)
    gold_path = root / config.source.gold_queries
    gold = RetrievalGoldSet.model_validate_json(gold_path.read_text(encoding="utf-8"))
    _validate_gold(gold, units, config.source.units_sha256)
    counter = TiktokenTokenCounter(config.evaluation.token_counter_encoding)

    if boundary_embedder is None:
        boundary_embedder = build_boundary_embedder(
            root, config.boundary_embedding.config
        )

    output.mkdir(parents=True, exist_ok=True)
    baseline = chunk_quality.parser_baseline(units)
    _write_json(
        output / "parser-baseline.json",
        {
            "finding_count": len(baseline),
            "note": (
                "These findings depend on the canonical stream alone and are "
                "byte-identical for every arm. They measure the parser, not a "
                "chunker, and are excluded from every per-arm comparison."
            ),
            "by_rule": chunk_quality._finding_counts(baseline),
            "findings": [asdict(finding) for finding in baseline],
        },
    )

    query_embeddings = np.zeros((len(gold.queries), 1), dtype=np.float32)
    timing: dict[str, Any] = {"parse": {"measured": False, "reason": "skipped"}}
    if measure_parse_time:
        timing["parse"] = measure_parse(
            root, config.source, config.benchmark.canonical_profile
        )

    corpora: dict[str, list[dict[str, Any]]] = {}
    mappings: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    structural: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {}
    shas: dict[str, str] = {}

    for arm in ARMS:
        arm_dir = output / arm
        arm_dir.mkdir(parents=True, exist_ok=True)
        rows, arm_diagnostics, spans, samples = time_arm(
            arm,
            config,
            units,
            counter,
            boundary_embedder=boundary_embedder,
            repetitions=config.evaluation.chunking_repetitions,
        )
        normalized = [normalize_unit_ids_for_retrieval(row) for row in rows]
        _write_jsonl(arm_dir / "chunks.jsonl", normalized)
        shas[arm] = sha256_file(arm_dir / "chunks.jsonl")
        corpora[arm] = normalized
        diagnostics[arm] = arm_diagnostics

        mapping = map_chunks(units, normalized, unit_spans=spans)
        mappings[arm] = mapping
        _write_json(arm_dir / "mapping.json", mapping.as_dict())
        structural[arm] = chunk_quality.measure(
            units,
            normalized,
            mapping,
            counter=counter,
            min_tokens=config.tokens.min_tokens,
            soft_max_tokens=config.tokens.soft_max_tokens,
            hard_max_tokens=config.tokens.hard_max_tokens,
            baseline=baseline,
        )
        _write_json(arm_dir / "structural_quality.json", structural[arm])

        documents = to_documents(normalized, units, counter, mapping=mapping)
        index_start = time.perf_counter_ns()
        index = BM25OnlyIndex(
            documents, k1=config.bm25.k1, b=config.bm25.b, fold=config.bm25.fold
        )
        index_ms = (time.perf_counter_ns() - index_start) / 1_000_000.0
        metrics[arm] = _evaluate_candidate(
            candidate_id=arm,
            documents=documents,
            index=index,
            gold=gold,
            units=units,
            query_embeddings=query_embeddings,
            top_ks=config.evaluation.top_ks,
            latency_repetitions=config.evaluation.latency_repetitions,
            token_counter=counter,
            output_dir=arm_dir,
            index_build_ms=index_ms,
            shared_query_embedding_per_query_ms=0.0,
        )
        # Every measured duration lives in timing.json and nowhere else, so
        # chunks.jsonl, structural_quality.json and retrieval.json stay
        # byte-identical between runs and a reproducibility test can say so.
        latency = metrics[arm].pop("latency")
        (arm_dir / "metrics.json").unlink()
        _write_json(arm_dir / "retrieval.json", metrics[arm])

        timing[arm] = {
            "chunk_ms_median": statistics.median(samples),
            "chunk_ms_min": min(samples),
            "chunk_ms_samples": samples,
            "index_build_ms": index_ms,
            "search_p50_ms": latency["search_median_ms"],
            "search_p90_ms": latency["search_p90_ms"],
            "search_latency": latency,
            "uses_embeddings": methods.get(arm).needs_embedder,
            "cold_equals_warm": not methods.get(arm).needs_embedder,
        }
        if methods.get(arm).needs_embedder and measure_cold_embedding_time:
            timing[arm]["cold"] = measure_cold_embedding(root, config, units, counter, arm=arm)
        _write_json(arm_dir / "timing.json", timing[arm])

    comparison, comparison_summary = arm_comparison(output, gold)
    _write_jsonl(output / "query-comparison.jsonl", comparison)

    # The first gold set links every question to a single evidence unit, which
    # makes Hit@K and evidence coverage the same measurement. It is reported
    # beside the primary set for comparability with the frozen Phase 4/5 runs,
    # never as the headline.
    secondary: dict[str, Any] = {}
    if config.source.secondary_gold_queries:
        secondary_path = root / config.source.secondary_gold_queries
        secondary_gold = RetrievalGoldSet.model_validate_json(
            secondary_path.read_text(encoding="utf-8")
        )
        _validate_gold(secondary_gold, units, config.source.units_sha256)
        secondary_embeddings = np.zeros((len(secondary_gold.queries), 1), dtype=np.float32)
        for arm in ARMS:
            arm_dir = output / "secondary" / arm
            arm_dir.mkdir(parents=True, exist_ok=True)
            documents = to_documents(corpora[arm], units, counter, mapping=mappings[arm])
            metric = _evaluate_candidate(
                candidate_id=arm,
                documents=documents,
                index=BM25OnlyIndex(
                    documents, k1=config.bm25.k1, b=config.bm25.b, fold=config.bm25.fold
                ),
                gold=secondary_gold,
                units=units,
                query_embeddings=secondary_embeddings,
                top_ks=config.evaluation.top_ks,
                latency_repetitions=1,
                token_counter=counter,
                output_dir=arm_dir,
                index_build_ms=0.0,
                shared_query_embedding_per_query_ms=0.0,
            )
            metric.pop("latency")
            (arm_dir / "metrics.json").unlink()
            _write_json(arm_dir / "retrieval.json", metric)
            secondary[arm] = metric
        secondary = {
            "gold_queries": config.source.secondary_gold_queries,
            "gold_queries_sha256": sha256_file(secondary_path),
            "query_count": len(secondary_gold.queries),
            "note": (
                "Every question in this set has one evidence unit, so Hit@K and "
                "evidence coverage carry the same information. Secondary."
            ),
            "metrics": secondary,
        }

    viewer_path = chunk_viewer.write_viewer(
        output / "viewer" / f"{gold.document_id}.html",
        units,
        {arm: (corpora[arm], mappings[arm]) for arm in ARMS},
        document_id=gold.document_id,
    )

    appendix: dict[str, Any] = {}
    for name, entry in sorted(config.appendix.items()):
        appendix_dir = output / "appendix" / name
        appendix_dir.mkdir(parents=True, exist_ok=True)
        rows = [
            normalize_unit_ids_for_retrieval(row)
            for row in load_jsonl_objects(root / entry.chunks)
        ]
        mapping = map_chunks(units, rows)
        appendix[name] = {
            "structural_quality": chunk_quality.measure(
                units,
                rows,
                mapping,
                counter=counter,
                min_tokens=config.tokens.min_tokens,
                soft_max_tokens=config.tokens.soft_max_tokens,
                hard_max_tokens=config.tokens.hard_max_tokens,
                baseline=baseline,
            ),
            "note": (
                "Diagnostic reference only. Not one of the compared methods; "
                "excluded from every headline table and from every gained/lost "
                "comparison."
            ),
        }
        _write_json(appendix_dir / "structural_quality.json", appendix[name])

    summary = {
        "schema_version": "1.0",
        "benchmark_version": config.benchmark.version,
        "status": config.benchmark.status,
        "document_id": gold.document_id,
        "canonical_sha256": config.source.units_sha256,
        "gold_queries_sha256": sha256_file(gold_path),
        "query_count": len(gold.queries),
        "compared_arms": list(ARMS),
        "retrieval": {
            "profile": "bm25_only",
            "bm25": config.bm25.model_dump(mode="json"),
            "dense_leg": False,
            "reranker": False,
            "query_expansion": False,
            "note": (
                "Identical across the three arms; reproduces the production "
                "BM25OnlyRetriever. rrf_score in query-results.jsonl carries the "
                "BM25 score -- nothing is fused."
            ),
        },
        "arm_chunk_sha256": shas,
        "arm_diagnostics": diagnostics,
        "timing": timing,
        "retrieval_metrics": metrics,
        "structural_quality": structural,
        "query_comparison": comparison_summary,
        "secondary_gold": secondary,
        "evidence_type_hit_at_5": by_evidence_type(comparison),
        "parser_baseline_finding_count": len(baseline),
        "viewer": str(viewer_path.relative_to(output)).replace("\\", "/"),
        "appendix": appendix,
        "interpretation_guardrail": (
            "Yalnız chunker değişir: canonical girdi, BM25 retrieval ve gold set "
            "üç kolda da aynıdır. Bütün chunker parametreleri "
            "poc_initial_not_optimized işaretli PoC değerleridir ve ilk koşudan "
            "önce dondurulmuştur. Production kazanan ilan edilmemiştir."
        ),
    }
    _write_json(output / "benchmark-summary.json", summary)
    _write_json(output / "resolved-config.json", config.model_dump(mode="json"))
    _write_json(
        output / "manifest.json",
        {
            "config_sha256": sha256_file(config_path),
            "canonical_sha256": config.source.units_sha256,
            "gold_queries_sha256": sha256_file(gold_path),
            "arm_chunk_sha256": shas,
            "only_chunker_varies": True,
        },
    )
    (output / "benchmark-report.md").write_text(
        render_report(summary), encoding="utf-8", newline="\n"
    )
    return summary


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def render_report(summary: Mapping[str, Any]) -> str:
    metrics = summary["retrieval_metrics"]
    structural = summary["structural_quality"]
    timing = summary["timing"]

    lines = [
        f"# Chunking Benchmark — {summary['document_id']}",
        "",
        "Parser girdisi, gold set ve retrieval hattı üç kolda da aynıdır; yalnız chunker değişir.",
        "Retrieval **BM25-only**: dense bacak, reranker ve query expansion kapalı.",
        "",
        "## 1. Zaman",
        "",
        "| Kol | Chunking p50 (ms) | Chunking min (ms) | Index build (ms) | Search p50 (ms) | Search p90 (ms) | Embedding |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for arm in ARMS:
        entry = timing[arm]
        lines.append(
            "| {label} | {p50:.1f} | {low:.1f} | {index:.1f} | {s50:.3f} | {s90:.3f} | {emb} |".format(
                label=LABELS[arm],
                p50=entry["chunk_ms_median"],
                low=entry["chunk_ms_min"],
                index=entry["index_build_ms"],
                s50=entry["search_p50_ms"],
                s90=entry["search_p90_ms"],
                emb="E5 (cold≠warm)" if entry["uses_embeddings"] else "yok (cold≡warm)",
            )
        )
    cold = (timing.get("hybrid") or {}).get("cold")
    if cold:
        lines += [
            "",
            f"Hybrid, boş embedding cache ile: **{cold['chunk_ms_cold']:.0f} ms** "
            f"({cold['embedded_piece_count']} piece embed edildi, model zaten yüklü). "
            f"Warm karşılığı {timing['hybrid']['chunk_ms_median']:.0f} ms.",
        ]
    parse = timing["parse"]
    lines += [
        "",
        (
            f"Parse (PDF → canonical units) üç kolda da aynıdır ve tek bir paylaşılan sabit olarak ölçülür: "
            f"**{parse['parse_ms']:.0f} ms**, {parse['unit_count']} unit."
            if parse.get("measured")
            else f"Parse süresi ölçülmedi ({parse.get('reason')})."
        ),
        "Kola atfedilmez. Cold/warm ayrımı yalnız hybrid için anlamlıdır; diğer iki kol hiç model yüklemez.",
        "",
        "`Chunking` sütunu **bu implementasyonların** maliyetidir, yöntemlerin teorik maliyeti değil. "
        "Size-first splitter uzunluk fonksiyonu olarak token sayacını kullandığı için özyineleme ve "
        "paketleme sırasında aynı metni tekrar tekrar sayar; bu, kolun tasarımından çok kodun "
        "optimize edilmemiş olmasından gelir ve öyle okunmalıdır.",
        "",
        "## 2. Retrieval kalitesi",
        "",
        f"{summary['query_count']} soru · BM25-only · top-k 1/3/5",
        "",
        "| Kol | Chunks | Hit@1 | Hit@3 | Hit@5 | MRR | Evidence coverage@5 | Source coverage | Fragmentation* | Irrelevant tokens@5† |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        metric = metrics[arm]
        lines.append(
            "| {label} | {n} | {h1:.4f} | {h3:.4f} | {h5:.4f} | {mrr:.4f} | {cov:.4f} | {src:.4f} | {frag:.3f} | {irr:.4f} |".format(
                label=LABELS[arm],
                n=metric["chunk_count"],
                h1=metric["hit_at_1"],
                h3=metric["hit_at_3"],
                h5=metric["hit_at_5"],
                mrr=metric["mrr"],
                cov=metric["evidence_coverage_at_5"],
                src=metric["source_evidence_coverage"],
                frag=metric["evidence_fragmentation_mean_covered_queries"],
                irr=metric["retrieved_irrelevant_token_ratio_at_5"],
            )
        )
    lines += [
        "",
        "`Fragmentation*` overlap taşıyan bir kolda yapısal olarak yükselir; yöntem özelliğidir, kusur değil.",
        "`Irrelevant tokens@5†` ağırlıkla chunk boyutu ÷ evidence boyutu aritmetiğidir — retrieval kalitesi değil, **boyut vekili** olarak okunmalıdır.",
        "",
    ]

    secondary = summary.get("secondary_gold") or {}
    if secondary:
        lines += [
            f"### İkincil gold ({secondary['query_count']} soru) — yalnız karşılaştırılabilirlik için",
            "",
            "Bu sette her soru **tek** evidence unit'e bağlıdır, dolayısıyla Hit@K ile evidence coverage "
            "aynı bilgiyi taşır. İkincil olarak raporlanır, manşet değildir.",
            "",
            "| Kol | Hit@1 | Hit@3 | Hit@5 | MRR |",
            "|---|---:|---:|---:|---:|",
        ]
        for arm in ARMS:
            metric = secondary["metrics"][arm]
            lines.append(
                "| {label} | {h1:.4f} | {h3:.4f} | {h5:.4f} | {mrr:.4f} |".format(
                    label=LABELS[arm],
                    h1=metric["hit_at_1"],
                    h3=metric["hit_at_3"],
                    h5=metric["hit_at_5"],
                    mrr=metric["mrr"],
                )
            )
        lines.append("")

    lines += [
        "### evidence_type kırılımı (Hit@5)",
        "",
        "| evidence_type | Soru | " + " | ".join(LABELS[arm] for arm in ARMS) + " |",
        "|---|---:|" + "---:|" * len(ARMS),
    ]
    for kind, bucket in summary["evidence_type_hit_at_5"].items():
        cells = " | ".join(str(bucket[arm]) for arm in ARMS)
        lines.append(f"| {kind} | {bucket['query_count']} | {cells} |")

    lines += [
        "",
        "### Query-level farklar (Hit@5)",
        "",
    ]
    for key, entry in summary["query_comparison"]["pairwise_hit_at_5"].items():
        left, right = key.replace("_hit_at_5", "").split("_vs_")
        lines.append(
            f"- **{left}** vs **{right}** — kazandığı: {', '.join(entry['gained']) or 'yok'}"
            f" · kaybettiği: {', '.join(entry['lost']) or 'yok'}"
        )
    lines.append(
        f"- Üç kolun da kaçırdığı: {', '.join(summary['query_comparison']['missed_by_all_at_5']) or 'yok'}"
    )

    lines += [
        "",
        "## 3. Chunk yapısal kalitesi",
        "",
        "| Kol | Chunks | Token min/medyan/p90/maks | <min | >soft_max | Multi-section | Heading ile başlayan | Mid-word | Mid-sentence | Bölünen tablo | Duplicate token mass | Unit coverage |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        report = structural[arm]
        tokens = report["token_count"]
        bands = report["size_bands"]
        lines.append(
            "| {label} | {n} | {mn}/{md:.0f}/{p90}/{mx} | {below} | {above} | {multi} ({mr:.1%}) | {head} ({hr:.1%}) | {mw} | {ms} | {tf} | {dup:.3f} | {cov:.3f} |".format(
                label=LABELS[arm],
                n=report["chunk_count"],
                mn=tokens["min"],
                md=tokens["median"],
                p90=tokens["p90_nearest_rank"],
                mx=tokens["max"],
                below=bands["below_min_count"],
                above=bands["above_soft_max_count"],
                multi=report["structure"]["multi_section_count"],
                mr=report["structure"]["multi_section_ratio"],
                head=report["structure"]["heading_led_count"],
                hr=report["structure"]["heading_led_ratio"],
                mw=report["fragmentation"]["mid_word_split_count"],
                ms=report["fragmentation"]["mid_sentence_split_count"],
                tf=report["fragmentation"]["table_units_fragmented"],
                dup=report["duplication"]["duplicate_token_mass_ratio"],
                cov=report["coverage"]["content_unit_coverage"],
            )
        )

    lines += [
        "",
        f"Structural QA'nın **{summary['parser_baseline_finding_count']}** bulgusu yalnız canonical akışa bağlıdır ve üç kolda birebir aynıdır; "
        "parser'ı ölçer, chunker'ı değil, ve hiçbir kol karşılaştırmasına girmez (`parser-baseline.json`).",
        "",
        "| Kol | Chunk kaynaklı QA bulgusu | Chunk başına |",
        "|---|---:|---:|",
    ]
    for arm in ARMS:
        qa = structural[arm]["structural_qa"]
        lines.append(
            f"| {LABELS[arm]} | {qa['chunk_derived_finding_count']} | {qa['chunk_derived_per_chunk']:.3f} |"
        )

    hybrid = summary["arm_diagnostics"].get("hybrid") or {}
    if hybrid:
        changed = hybrid.get("arbitration_changed_boundary_count", 0)
        lines += [
            "",
            "### Hybrid: semantik hakemlik gerçekten devreye girdi mi",
            "",
            f"- Aşırı büyük section: **{hybrid.get('oversized_section_count')}** / {hybrid.get('section_count')}",
            f"- Hakemliğe giren sınır: **{hybrid.get('arbitrated_boundary_count')}** "
            f"({hybrid.get('admissible_candidate_total')} aday arasından)",
            f"- Kararı **değiştiren** sınır: **{changed}**",
            f"- Uygun aday bulunmayıp structure-only kuralına düşen section: **{hybrid.get('h1_fallback_section_count')}**",
            "",
            (
                "Hakemlik hiçbir sınırı değiştirmedi; hybrid ile structure-only arasındaki fark "
                "bu koşuda **yoktur** ve chunker bunu değiştirmek için ayarlanmamıştır."
                if changed == 0
                else "Bu sayı sıfır olsaydı rapor farkın olmadığını yazacaktı; chunker sonuç için ayarlanmaz."
            ),
        ]

    if summary.get("appendix"):
        lines += [
            "",
            "## Appendix — diagnostic referans",
            "",
            "Aşağıdaki satırlar **karşılaştırılan yöntemlerden biri değildir**; yalnız üç kolun sayılarını "
            "mevcut frozen sonuçlara bağlamak için, şema-normalize edilmiş hâlde verilir.",
            "",
            "| Referans | Chunks | Multi-section | Heading ile başlayan | Mid-word |",
            "|---|---:|---:|---:|---:|",
        ]
        for name, entry in summary["appendix"].items():
            report = entry["structural_quality"]
            lines.append(
                "| {name} | {n} | {multi} | {head} | {mw} |".format(
                    name=name,
                    n=report["chunk_count"],
                    multi=report["structure"]["multi_section_count"],
                    head=report["structure"]["heading_led_count"],
                    mw=report["fragmentation"]["mid_word_split_count"],
                )
            )

    lines += [
        "",
        "## Yorumlama sınırı",
        "",
        summary["interpretation_guardrail"],
        "",
        f"- Bu sette bir soru **{100 / summary['query_count']:.1f} puan** eder; bu büyüklüğün altındaki farklar gürültüdür.",
        "- Markdown kolunun `chunk_size`/`chunk_overlap` değerleri bu benchmark için dondurulmuş "
        "konfigürasyondur, herhangi bir kütüphanenin varsayılanı değildir.",
        "- Küçük chunk'ların birleştirilmesi bu benchmark'ın kapsamında değildir; hiçbir kol bunu yapmaz.",
        f"- Parsed Chunk Viewer (`{summary.get('viewer')}`) bir açıklanabilirlik/debug aracıdır; "
        "ana kalite metriğinin yerine geçmez.",
        "",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.chunk_benchmark",
        description=(
            "Compare markdown / hybrid / structure-only chunking on time and "
            "quality over a frozen canonical corpus."
        ),
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="output directory; required on purpose, and never under evaluation/",
    )
    parser.add_argument(
        "--skip-parse-timing",
        action="store_true",
        help="skip the shared PDF parse measurement (it loads the layout model)",
    )
    parser.add_argument(
        "--skip-cold-embedding",
        action="store_true",
        help="skip the hybrid arm's empty-cache embedding measurement",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = run_benchmark(
        config_path=args.config,
        output_dir=args.output,
        measure_parse_time=not args.skip_parse_timing,
        measure_cold_embedding_time=not args.skip_cold_embedding,
    )
    for arm in ARMS:
        metric = summary["retrieval_metrics"][arm]
        print(
            f"{LABELS[arm]:26} chunks={metric['chunk_count']:4d} "
            f"Hit@1={metric['hit_at_1']:.4f} Hit@3={metric['hit_at_3']:.4f} "
            f"Hit@5={metric['hit_at_5']:.4f} MRR={metric['mrr']:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
