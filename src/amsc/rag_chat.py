"""The RAG chat engine behind the viewer's Sorgu tab.

    catalog (documents x chunking arms)  ->  one ChunkIndex per (doc, arm)
    question  ->  hybrid retrieval  ->  context assembly  ->  grounded answer

The same embedding model, the same fusion and the same context rules serve
every arm, so asking one question across Markdown / Hybrid / Structure-only /
Agentic compares the chunkers and nothing else. Chunking happened at ingest;
nothing here calls the proposer, the verifier or the boundary judge.

The catalog is written by :mod:`amsc.viewer_v2` beside the HTML, so the
chat serves exactly the arms the viewer shows. Providers come from a plain
YAML config that names models, endpoints and the environment variables the
keys are read from -- never the keys. Every response is a JSON-serialisable
dict: the server dumps it, the CLI prints it.

Failure policy: an answer-model error returns the retrieved sources with
``status: answer_error`` and a readable message; an embedding failure while
building an index falls back to lexical retrieval for that index and says
so; a bad request (unknown document, empty question) is a ``ValueError`` the
server maps to HTTP 400.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .rag_answer import AnswerProvider, answer as generate_answer, build_answer_provider
from .rag_context import AssembledContext, ContextSettings, assemble_context
from .rag_embeddings import CachedEmbeddings, build_embedding_provider
from .rag_index import ChunkIndex, IndexedChunk, RetrievalSettings, index_rows
from .retrieval_pipeline import RetrievalHit

ARM_LABELS = {
    "markdown": "Markdown",
    "hybrid": "Hybrid",
    "structure-only": "Structure-only",
    "agentic": "Agentic Chunker",
}
ARM_ORDER = ("markdown", "hybrid", "structure-only", "agentic")

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient"
STATUS_NO_ANSWER_MODEL = "no_answer_model"
STATUS_ANSWER_ERROR = "answer_error"


@dataclass(frozen=True)
class ArmSpec:
    arm: str
    kind: str
    chunks: Path
    label: str


@dataclass(frozen=True)
class DocumentSpec:
    doc_id: str
    label: str
    units: Path
    canonical_sha256: str | None
    arms: dict[str, ArmSpec]


@dataclass
class Catalog:
    documents: dict[str, DocumentSpec]
    path: Path | None = None

    @classmethod
    def load(cls, path: str | Path, *, root: str | Path = ".") -> "Catalog":
        path = Path(path)
        root = Path(root)
        payload = json.loads(path.read_text(encoding="utf-8"))
        documents: dict[str, DocumentSpec] = {}
        for doc_id, doc in (payload.get("documents") or {}).items():
            arms = {
                arm: ArmSpec(
                    arm=arm,
                    kind=str(spec.get("kind") or arm),
                    chunks=root / spec["chunks"],
                    label=str(spec.get("label") or ARM_LABELS.get(arm, arm)),
                )
                for arm, spec in (doc.get("arms") or {}).items()
            }
            documents[doc_id] = DocumentSpec(
                doc_id=doc_id,
                label=str(doc.get("label") or doc_id),
                units=root / doc["units"],
                canonical_sha256=doc.get("canonical_sha256"),
                arms=arms,
            )
        return cls(documents=documents, path=path)

    def describe(self) -> dict[str, Any]:
        return {
            doc_id: {
                "label": doc.label,
                "arms": {
                    arm: {"kind": spec.kind, "label": spec.label}
                    for arm, spec in doc.arms.items()
                },
            }
            for doc_id, doc in self.documents.items()
        }


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_config(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    import yaml

    with Path(path).open("r", encoding="utf-8") as handle:
        return dict(yaml.safe_load(handle) or {})


@dataclass
class ChatEngine:
    catalog: Catalog
    retrieval: RetrievalSettings = RetrievalSettings()
    context: ContextSettings = ContextSettings()
    embedder: CachedEmbeddings | None = None
    answerer: AnswerProvider | None = None
    _indexes: dict[tuple[str, str], ChunkIndex] = field(default_factory=dict, repr=False)
    _locks: dict[tuple[str, str], threading.Lock] = field(default_factory=dict, repr=False)
    _guard: threading.Lock = field(default_factory=threading.Lock, repr=False)
    notes: dict[str, str] = field(default_factory=dict)

    # -- construction -------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        catalog: Catalog,
        config: Mapping[str, Any],
        *,
        root: str | Path = ".",
        dense: bool = True,
        answers: bool = True,
    ) -> "ChatEngine":
        root = Path(root)
        embedder: CachedEmbeddings | None = None
        if dense:
            embedding = dict(config.get("embedding") or {})
            cache_dir = embedding.pop("cache_dir", ".cache/rag-embeddings")
            embedder = CachedEmbeddings(
                build_embedding_provider(embedding),
                root / cache_dir if cache_dir else None,
            )
        answerer = build_answer_provider(dict(config.get("answer") or {})) if answers else None
        return cls(
            catalog=catalog,
            retrieval=RetrievalSettings.from_mapping(config.get("retrieval")),
            context=ContextSettings.from_mapping(config.get("context")),
            embedder=embedder,
            answerer=answerer,
        )

    # -- lookups --------------------------------------------------------------

    def _spec(self, doc: str, arm: str) -> tuple[DocumentSpec, ArmSpec]:
        document = self.catalog.documents.get(doc)
        if document is None:
            raise ValueError(f"unknown document {doc!r}")
        spec = document.arms.get(arm)
        if spec is None:
            raise ValueError(f"document {doc!r} has no arm {arm!r}")
        return document, spec

    def index(self, doc: str, arm: str) -> ChunkIndex:
        key = (doc, arm)
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            built = self._indexes.get(key)
            if built is not None:
                return built
            _document, spec = self._spec(doc, arm)
            rows = load_rows(spec.chunks)
            embedder = self.embedder
            try:
                built = index_rows(arm, spec.kind, rows, settings=self.retrieval, embedder=embedder)
            except RuntimeError as error:
                if embedder is None:
                    raise
                # The demo must keep answering when the embedding endpoint
                # is down: lexical retrieval, flagged on every response.
                self.notes[f"{doc}/{arm}"] = f"dense retrieval unavailable ({error}); BM25 only"
                built = index_rows(arm, spec.kind, rows, settings=self.retrieval, embedder=None)
            self._indexes[key] = built
            return built

    def chunk(self, doc: str, arm: str, chunk_id: str) -> dict[str, Any]:
        built = self.index(doc, arm)
        chunk = built.by_id().get(chunk_id)
        if chunk is None:
            raise ValueError(f"unknown chunk {chunk_id!r} in {doc}/{arm}")
        return _chunk_payload(chunk, arm)

    # -- the pipeline ---------------------------------------------------------

    def retrieve(
        self, doc: str, arm: str, question: str, *, top_k: int | None = None
    ) -> dict[str, Any]:
        question = (question or "").strip()
        if not question:
            raise ValueError("the question is empty")
        _document, spec = self._spec(doc, arm)
        started = time.perf_counter()
        built = self.index(doc, arm)
        note = self.notes.get(f"{doc}/{arm}")
        try:
            hits = built.search(question, top_k=top_k)
        except RuntimeError as error:
            if built.embedder is None:
                raise
            # Query embedding failed: answer lexically for this question.
            lexical = ChunkIndex(
                arm=arm, kind=spec.kind, chunks=built.chunks, settings=self.retrieval, embedder=None
            ).build()
            hits = lexical.search(question, top_k=top_k)
            note = f"query embedding failed ({error}); this answer used BM25 only"
        context = assemble_context(hits, built.chunks, kind=spec.kind, settings=self.context)
        seconds = time.perf_counter() - started
        return {
            "document": doc,
            "arm": arm,
            "arm_kind": spec.kind,
            "arm_label": spec.label,
            "question": question,
            "hits": [_hit_payload(hit) for hit in hits],
            "context": context.as_dict(),
            "sources": [_source_payload(block, built.by_id()[block.chunk_id], arm) for block in context.blocks],
            "retrieval": {
                "dense": built.dense,
                "embedding_model": built.embedder.model_id if built.embedder else None,
                "top_k": top_k or self.retrieval.top_k,
                "fusion": "rrf",
                "note": note,
            },
            "timing_seconds": {"retrieval": round(seconds, 3)},
            "_context": context,
        }

    def ask(self, doc: str, arm: str, question: str, *, top_k: int | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        retrieved = self.retrieve(doc, arm, question, top_k=top_k)
        context: AssembledContext = retrieved.pop("_context")
        response = dict(retrieved)
        response["models"] = {
            "embedding": retrieved["retrieval"]["embedding_model"],
            "answer": self.answerer.model_id if self.answerer else None,
        }
        if not context.blocks:
            response["answer"] = {
                "text": "Bu dokümanda soruyla ilgili bir parça bulunamadı.",
                "sufficient": False,
                "sources_used": [],
                "parsed": True,
            }
            response["status"] = STATUS_INSUFFICIENT
        elif self.answerer is None:
            response["answer"] = None
            response["status"] = STATUS_NO_ANSWER_MODEL
            response["error"] = "Cevap modeli yapılandırılmadı; yalnız kaynaklar gösteriliyor."
        else:
            try:
                result = generate_answer(
                    question, context.blocks, context.render(), provider=self.answerer
                )
            except RuntimeError as error:
                response["answer"] = None
                response["status"] = STATUS_ANSWER_ERROR
                response["error"] = (
                    "Cevap modeline ulaşılamadı; kaynak parçalar yine de gösteriliyor. "
                    f"({error})"
                )
            else:
                parse = result.parse
                used = set(parse.sources_used)
                for source in response["sources"]:
                    source["used"] = source["label"] in used
                response["answer"] = {
                    "text": parse.answer,
                    "sufficient": parse.sufficient,
                    "sources_used": parse.sources_used,
                    "parsed": parse.parsed,
                }
                response["status"] = (
                    STATUS_INSUFFICIENT if parse.sufficient is False else STATUS_OK
                )
                response["timing_seconds"]["answer"] = result.seconds
                response["usage"] = result.usage
                response["prompt_version"] = result.prompt_version
        response["timing_seconds"]["total"] = round(time.perf_counter() - started, 3)
        return response

    def compare(
        self,
        doc: str,
        question: str,
        *,
        arms: Sequence[str] | None = None,
        top_k: int | None = None,
        answers: bool = True,
    ) -> dict[str, Any]:
        document = self.catalog.documents.get(doc)
        if document is None:
            raise ValueError(f"unknown document {doc!r}")
        chosen = [arm for arm in (arms or ARM_ORDER) if arm in document.arms]
        results: dict[str, Any] = {}
        for arm in chosen:
            if answers:
                results[arm] = self.ask(doc, arm, question, top_k=top_k)
            else:
                retrieved = self.retrieve(doc, arm, question, top_k=top_k)
                retrieved.pop("_context", None)
                results[arm] = retrieved
        # The comparison's own reading: which chunks each arm surfaced, and
        # how much of the retrieved context they agree on at the unit level.
        unit_sets = {
            arm: {u for source in result["sources"] for u in source.get("unit_ids", [])}
            for arm, result in results.items()
        }
        overlap: dict[str, float] = {}
        for arm, units in unit_sets.items():
            others = set().union(*(s for a, s in unit_sets.items() if a != arm)) if len(unit_sets) > 1 else set()
            overlap[arm] = round(len(units & others) / len(units), 3) if units else 0.0
        return {
            "document": doc,
            "question": question,
            "arms": results,
            "unit_overlap_with_other_arms": overlap,
        }

    def warm(self, docs: Sequence[str] | None = None) -> dict[str, Any]:
        report: dict[str, Any] = {}
        for doc_id, document in self.catalog.documents.items():
            if docs and doc_id not in docs:
                continue
            for arm in document.arms:
                built = self.index(doc_id, arm)
                stats = built.stats.__dict__ if built.stats else {}
                report[f"{doc_id}/{arm}"] = {**stats, "note": self.notes.get(f"{doc_id}/{arm}")}
        return report

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "documents": self.catalog.describe(),
            "embedding_model": self.embedder.model_id if self.embedder else None,
            "answer_model": self.answerer.model_id if self.answerer else None,
            "dense": self.embedder is not None,
            "retrieval": {**self.retrieval.__dict__},
            "context": {**self.context.__dict__},
            "indexes_built": sorted(f"{d}/{a}" for d, a in self._indexes),
            "notes": dict(self.notes),
        }


# --------------------------------------------------------------------------
# payload shaping (JSON-safe, no secrets, chunk text included on purpose)
# --------------------------------------------------------------------------


def _hit_payload(hit: RetrievalHit) -> dict[str, Any]:
    return {
        "rank": hit.rank,
        "chunk_id": hit.chunk_id,
        "rrf_score": round(hit.rrf_score, 6),
        "dense_rank": hit.dense_rank,
        "bm25_rank": hit.bm25_rank,
        "dense_score": round(float(hit.dense_score), 6),
        "bm25_score": round(float(hit.bm25_score), 6),
    }


def _chunk_payload(chunk: IndexedChunk, arm: str) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "index": chunk.index,
        "arm": arm,
        "arm_label": ARM_LABELS.get(arm, arm),
        "heading": chunk.heading,
        "section_path": list(chunk.section_path),
        "pages": list(chunk.pages),
        "token_count": chunk.token_count,
        "unit_ids": list(chunk.unit_ids),
        "text": chunk.text,
    }


def _source_payload(block, chunk: IndexedChunk, arm: str) -> dict[str, Any]:
    payload = _chunk_payload(chunk, arm)
    payload.update(block.as_dict())
    payload["used"] = False
    return payload


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.rag_chat",
        description="Ask a document through one chunking arm, or warm the indexes",
    )
    parser.add_argument("command", choices=("ask", "warm", "compare"))
    parser.add_argument("--question", "-q", help="the question, for ask and compare")
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=Path("configs/rag-poc.yaml"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--doc")
    parser.add_argument("--arm", default="agentic")
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--lexical", action="store_true", help="BM25 only, no embedding calls")
    parser.add_argument("--no-answer", action="store_true", help="retrieve, do not generate")
    args = parser.parse_args(argv)

    catalog = Catalog.load(args.catalog, root=args.root)
    engine = ChatEngine.from_config(
        catalog, load_config(args.config), root=args.root,
        dense=not args.lexical, answers=not args.no_answer,
    )
    if args.command == "warm":
        payload: Any = engine.warm([args.doc] if args.doc else None)
    elif args.command == "compare":
        if not args.doc or not args.question:
            parser.error("compare needs --doc and a question")
        payload = engine.compare(args.doc, args.question, top_k=args.top_k, answers=not args.no_answer)
    else:
        if not args.doc or not args.question:
            parser.error("ask needs --doc and a question")
        payload = engine.ask(args.doc, args.arm, args.question, top_k=args.top_k)
    print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
