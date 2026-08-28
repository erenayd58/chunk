"""Retrieval + structural quality for the Agentic Chunker -- a separate runner.

The frozen three-arm benchmark (`amsc.chunk_benchmark`, its configs and the
`artifacts/chunk-benchmark-v5` trees) is methodology and is not reopened:
this runner evaluates ONE extra corpus -- the agentic chunks -- under
byte-identical settings read from the frozen tree's own
``resolved-config.json`` (BM25 parameters, top_ks, token counter, budgets,
gold sets), using the same frozen metric implementations by import. The
frozen arms' numbers are never recomputed here; ``comparison-summary.json``
copies them verbatim from ``benchmark-summary.json`` and records that file's
sha256.

The four load-bearing reuse conditions from ``chunk_benchmark`` apply
unchanged: frozen ``RetrievalHit``, ``top_ks == [1, 3, 5]``, int/float
casts, ``documents`` passed separately. Chunk rows are normalized to
canonical unit ids before scoring (the fragment-id trap).

Claim discipline: agentic results are model-dependent and only
replay-deterministic; per-arm BM25 indexes legitimately differ (each arm is
indexed over its own chunks -- methodology, not contamination); no winner is
declared; every knob stays ``poc_initial_not_optimized``. Timing for this
arm is provider-bound and cache-dependent, so only local search latency is
recorded and chunking time is explicitly not comparable with the frozen
arms' ``chunk_ms``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .chunk_benchmark import (
    BM25OnlyIndex,
    RetrievalGoldSet,
    _evaluate_candidate,
    _validate_gold,
    normalize_unit_ids_for_retrieval,
    to_documents,
)
from . import chunk_quality
from .chunk_mapping import map_chunks
from .evaluation import sha256_file
from .io import load_jsonl_units
from .tokenization import TokenCounter

CANDIDATE_ID = "agentic"

HEDGES = {
    "model_dependent": True,
    "determinism": "replay_deterministic_only",
    "tuning_status": "poc_initial_not_optimized",
    "winner_declared": False,
    "resolution_note": (
        "47 primary queries; differences of a few questions are within "
        "resolution and are not read as a ranking"
    ),
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")


def _load_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _guard_trees(agentic_tree: Path, frozen_tree: Path) -> None:
    agentic = agentic_tree.resolve()
    frozen = frozen_tree.resolve()
    if "evaluation" in agentic.parts:
        raise ValueError("refusing to write into evaluation/ -- frozen results live there")
    if agentic == frozen or str(agentic).startswith(str(frozen) + "\\") or str(
        agentic
    ).startswith(str(frozen) + "/"):
        raise ValueError("the agentic tree must not live inside the frozen benchmark tree")
    for name in ("resolved-config.json", "benchmark-summary.json"):
        if not (frozen / name).is_file():
            raise ValueError(f"{frozen_tree} is not a completed benchmark tree ({name} missing)")
    if not (agentic / "agentic" / "chunks.jsonl").is_file():
        raise ValueError(f"{agentic_tree} carries no agentic/chunks.jsonl; build it first")


def _evaluate_gold(
    *,
    gold_path: Path,
    units,
    units_sha: str,
    rows: list[dict[str, Any]],
    mapping,
    counter: TokenCounter,
    frozen_config: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    gold = RetrievalGoldSet.model_validate_json(gold_path.read_text(encoding="utf-8"))
    _validate_gold(gold, units, units_sha)
    documents = to_documents(rows, units, counter, mapping=mapping)
    bm25 = frozen_config["bm25"]
    index_start = time.perf_counter_ns()
    index = BM25OnlyIndex(documents, k1=bm25["k1"], b=bm25["b"], fold=bm25["fold"])
    index_ms = (time.perf_counter_ns() - index_start) / 1_000_000.0
    evaluation = frozen_config["evaluation"]
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = _evaluate_candidate(
        candidate_id=CANDIDATE_ID,
        documents=documents,
        index=index,
        gold=gold,
        units=units,
        query_embeddings=np.zeros((len(gold.queries), 1), dtype=np.float32),
        top_ks=list(evaluation["top_ks"]),
        latency_repetitions=int(evaluation["latency_repetitions"]),
        token_counter=counter,
        output_dir=output_dir,
        index_build_ms=index_ms,
        shared_query_embedding_per_query_ms=0.0,
    )
    # Mirror chunk_benchmark: durations live in timing.json only, so
    # retrieval.json stays byte-identical between runs.
    latency = metrics.pop("latency")
    (output_dir / "metrics.json").unlink()
    _write_json(output_dir / "retrieval.json", metrics)
    _write_json(
        output_dir / "timing.json",
        {
            "index_build_ms": index_ms,
            "search_p50_ms": latency["search_median_ms"],
            "search_p90_ms": latency["search_p90_ms"],
            "search_latency": latency,
            "uses_llm": True,
            "chunking_note": (
                "agentic chunking time is provider-bound and cache-dependent; "
                "it is deliberately not comparable with the frozen arms' "
                "local chunk_ms and is not recorded here"
            ),
        },
    )
    return metrics


def run_agentic_benchmark(
    *,
    agentic_tree: Path,
    frozen_tree: Path,
    root: Path,
    counter: TokenCounter | None = None,
    secondary: bool = True,
) -> dict[str, Any]:
    """Evaluate the agentic chunks under the frozen tree's exact settings."""
    _guard_trees(agentic_tree, frozen_tree)
    frozen_config = _read_json(frozen_tree / "resolved-config.json")
    agentic_config = _read_json(agentic_tree / "resolved-config.json")
    manifest = _read_json(agentic_tree / "manifest.json")

    if agentic_config.get("pages"):
        raise ValueError(
            "the agentic tree is a page-sliced smoke run; full-document gold "
            "sets cannot score it -- build a full-document tree first"
        )

    source = frozen_config["source"]
    units_path = root / source["units"]
    units_sha = sha256_file(units_path)
    if units_sha != source["units_sha256"]:
        raise ValueError("frozen canonical units sha mismatch under --root")
    if manifest.get("canonical_sha256") != units_sha:
        raise ValueError(
            "the agentic tree was built from a different canonical corpus "
            "than the frozen benchmark; refusing to compare"
        )
    units = load_jsonl_units(units_path)

    if counter is None:
        from .tokenization import TiktokenTokenCounter

        counter = TiktokenTokenCounter(
            frozen_config["evaluation"]["token_counter_encoding"]
        )

    agentic_dir = agentic_tree / "agentic"
    rows = [normalize_unit_ids_for_retrieval(row) for row in _load_rows(agentic_dir / "chunks.jsonl")]
    mapping = map_chunks(units, rows)
    stored_mapping = _read_json(agentic_dir / "mapping.json")
    if mapping.as_dict() != stored_mapping:
        raise ValueError(
            "the agentic tree's mapping.json is stale for its chunks.jsonl; "
            "re-run amsc.agentic_chunker before benchmarking"
        )

    tokens = frozen_config["tokens"]
    baseline = chunk_quality.parser_baseline(units)
    structural = chunk_quality.measure(
        units,
        rows,
        mapping,
        counter=counter,
        min_tokens=tokens["min_tokens"],
        soft_max_tokens=tokens["soft_max_tokens"],
        hard_max_tokens=tokens["hard_max_tokens"],
        baseline=baseline,
    )
    _write_json(agentic_dir / "structural_quality.json", structural)

    metrics = _evaluate_gold(
        gold_path=root / source["gold_queries"],
        units=units,
        units_sha=units_sha,
        rows=rows,
        mapping=mapping,
        counter=counter,
        frozen_config=frozen_config,
        output_dir=agentic_dir,
    )

    secondary_metrics: dict[str, Any] | None = None
    if secondary and source.get("secondary_gold_queries"):
        secondary_metrics = _evaluate_gold(
            gold_path=root / source["secondary_gold_queries"],
            units=units,
            units_sha=units_sha,
            rows=rows,
            mapping=mapping,
            counter=counter,
            frozen_config=frozen_config,
            output_dir=agentic_tree / "secondary" / CANDIDATE_ID,
        )

    summary_path = frozen_tree / "benchmark-summary.json"
    frozen_summary = _read_json(summary_path)
    comparison = {
        "agentic": {
            "chunk_count": len(rows),
            "retrieval": metrics,
            "secondary_retrieval": secondary_metrics,
            "structural_quality": structural,
            "mode": manifest.get("mode"),
            "model_id": manifest.get("model_id"),
        },
        "frozen_reference": {
            "tree": frozen_tree.as_posix(),
            "benchmark_summary_sha256": hashlib.sha256(
                summary_path.read_bytes()
            ).hexdigest(),
            # Copied verbatim, never recomputed.
            "retrieval_metrics": frozen_summary.get("retrieval_metrics"),
            "structural_quality": frozen_summary.get("structural_quality"),
        },
        "hedges": HEDGES,
    }
    _write_json(agentic_tree / "comparison-summary.json", comparison)
    return comparison


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Score the agentic chunks under the frozen benchmark's "
        "exact settings; never touches the frozen tree"
    )
    parser.add_argument("--agentic-tree", required=True, type=Path)
    parser.add_argument("--frozen-tree", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--no-secondary", action="store_true")
    args = parser.parse_args(argv)
    comparison = run_agentic_benchmark(
        agentic_tree=args.agentic_tree,
        frozen_tree=args.frozen_tree,
        root=args.root,
        secondary=not args.no_secondary,
    )
    print(
        json.dumps(
            {
                "agentic_hit_at_5": comparison["agentic"]["retrieval"].get("hit_at_5"),
                "chunk_count": comparison["agentic"]["chunk_count"],
                "written": "comparison-summary.json",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
