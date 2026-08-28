"""The separate agentic evaluation runner, held to its discipline.

It scores the agentic chunks under settings read from the frozen tree's own
resolved-config, copies the frozen numbers verbatim instead of recomputing
them, and refuses every configuration that could contaminate or misread the
comparison (page-sliced smoke trees, mismatched canonicals, stale mappings,
outputs inside frozen surfaces).
"""

from __future__ import annotations

import hashlib
import json

import pytest

from amsc.agentic_benchmark import run_agentic_benchmark
from amsc.agentic_chunker import AgenticConfig, build_artifact
from amsc.models import SourceSpan

from _chunk_fixtures import WhitespaceCounter, heading, unit, words

COUNTER = WhitespaceCounter()

CONFIG = AgenticConfig(
    min_tokens=50,
    target_tokens=150,
    soft_max_tokens=160,
    hard_max_tokens=1000,
    respect_semantic_roles=False,
)


def corpus_with_pages():
    units = [
        heading("h-1", "KUCUK", 1),
        unit("p-0", words(30, "s"), order=2, section=("KUCUK",)),
        heading("h-2", "BUYUK", 3),
    ]
    for index in range(1, 5):
        units.append(
            unit(f"p-{index}", words(60, "abcd"[index - 1]), order=index + 3, section=("BUYUK",))
        )
    return [
        u.model_copy(update={"source": SourceSpan(page=1 + (i // 3))})
        for i, u in enumerate(units)
    ]


def write_units(tmp_path, units):
    path = tmp_path / "doc.units.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for u in units:
            handle.write(u.model_dump_json(exclude_none=True))
            handle.write("\n")
    return path


def write_gold(tmp_path, units, units_sha):
    by_id = {u.unit_id: u for u in units}
    evidence_pool = ["p-0", "p-1", "p-2", "p-3", "p-4"]
    queries = []
    for index in range(20):
        evidence = evidence_pool[index % len(evidence_pool)]
        queries.append(
            {
                "query_id": f"q-{index + 1:03d}",
                "question": f"{by_id[evidence].text.split()[0]} nedir {index}?",
                "evidence_unit_ids": [evidence],
                "evidence_pages": [by_id[evidence].source.page],
                "evidence_type": "narrative",
            }
        )
    gold = {
        "schema_version": "1.0",
        "document_id": "doc",
        "source_units_file": "doc.units.jsonl",
        "source_units_sha256": units_sha,
        "annotation_status": "manual_development_checkpoint",
        "authoring_method": "synthetic_test_fixture",
        "queries": queries,
    }
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")
    return path


def write_frozen_tree(tmp_path, units_sha):
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    (frozen / "resolved-config.json").write_text(
        json.dumps(
            {
                "source": {
                    "units": "doc.units.jsonl",
                    "units_sha256": units_sha,
                    "gold_queries": "gold.json",
                },
                "bm25": {"k1": 1.5, "b": 0.75, "fold": "turkish_diacritics_v1"},
                "evaluation": {
                    "top_ks": [1, 3, 5],
                    "latency_repetitions": 1,
                    "token_counter_encoding": "cl100k_base",
                },
                "tokens": {
                    "min_tokens": 50,
                    "target_tokens": 150,
                    "soft_max_tokens": 160,
                    "hard_max_tokens": 1000,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (frozen / "benchmark-summary.json").write_text(
        json.dumps(
            {
                "retrieval_metrics": {"markdown": {"hit_at_5": 0.5}},
                "structural_quality": {"planted": True},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return frozen


class SplitProvider:
    model_id = "test:benchmark-fixture@1"

    def complete(self, prompt: str) -> str:
        import re

        rows = []
        for cid, uid in re.findall(
            r"\[CANDIDATE (C\d+) \| cut before \w+ ([\w#-]+)\]", prompt
        ):
            decision = "SPLIT" if uid == "p-2" else "KEEP"
            rows.append(
                {
                    "candidate_id": cid,
                    "decision": decision,
                    "reason_code": "TOPIC_SHIFT" if decision == "SPLIT" else "CONTINUATION",
                }
            )
        return json.dumps(rows)


@pytest.fixture()
def trees(tmp_path):
    units = corpus_with_pages()
    units_path = write_units(tmp_path, units)
    units_sha = hashlib.sha256(units_path.read_bytes()).hexdigest()
    write_gold(tmp_path, units, units_sha)
    frozen = write_frozen_tree(tmp_path, units_sha)
    agentic = tmp_path / "agentic-tree"
    build_artifact(
        units_path=units_path,
        output=agentic,
        provider=SplitProvider(),
        config=CONFIG,
        counter=COUNTER,
    )
    return tmp_path, agentic, frozen


def test_the_runner_scores_agentic_and_copies_frozen_numbers_verbatim(trees):
    root, agentic, frozen = trees
    comparison = run_agentic_benchmark(
        agentic_tree=agentic, frozen_tree=frozen, root=root, counter=COUNTER
    )

    for name in ("retrieval.json", "query-results.jsonl", "structural_quality.json", "timing.json"):
        assert (agentic / "agentic" / name).is_file(), name
    assert not (agentic / "agentic" / "metrics.json").exists()
    assert not (agentic / "secondary").exists()  # no secondary gold configured

    retrieval = json.loads(
        (agentic / "agentic" / "retrieval.json").read_text(encoding="utf-8")
    )
    assert retrieval["candidate_id"] == "agentic"
    assert retrieval["query_count"] == 20
    assert 0.0 <= retrieval["hit_at_5"] <= 1.0

    # The frozen numbers are the planted ones, byte for byte, with the
    # summary file's sha recorded beside them.
    reference = comparison["frozen_reference"]
    assert reference["retrieval_metrics"] == {"markdown": {"hit_at_5": 0.5}}
    assert reference["structural_quality"] == {"planted": True}
    assert reference["benchmark_summary_sha256"] == hashlib.sha256(
        (frozen / "benchmark-summary.json").read_bytes()
    ).hexdigest()
    assert comparison["hedges"]["winner_declared"] is False
    assert comparison["agentic"]["model_id"] == "test:benchmark-fixture@1"

    timing = json.loads((agentic / "agentic" / "timing.json").read_text(encoding="utf-8"))
    assert timing["uses_llm"] is True
    assert "chunk_ms_median" not in timing  # provider-bound, deliberately absent


def test_reruns_are_byte_identical_outside_timing(trees):
    root, agentic, frozen = trees
    run_agentic_benchmark(agentic_tree=agentic, frozen_tree=frozen, root=root, counter=COUNTER)
    first = {
        name: (agentic / name).read_bytes()
        for name in (
            "comparison-summary.json",
            "agentic/retrieval.json",
            "agentic/query-results.jsonl",
            "agentic/structural_quality.json",
        )
    }
    run_agentic_benchmark(agentic_tree=agentic, frozen_tree=frozen, root=root, counter=COUNTER)
    for name, payload in first.items():
        assert (agentic / name).read_bytes() == payload, name


def test_a_page_sliced_smoke_tree_is_refused(trees):
    root, agentic, frozen = trees
    resolved = json.loads((agentic / "resolved-config.json").read_text(encoding="utf-8"))
    resolved["pages"] = [68, 75]
    (agentic / "resolved-config.json").write_text(
        json.dumps(resolved, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="page-sliced smoke"):
        run_agentic_benchmark(
            agentic_tree=agentic, frozen_tree=frozen, root=root, counter=COUNTER
        )


def test_a_different_canonical_is_refused(trees):
    root, agentic, frozen = trees
    manifest = json.loads((agentic / "manifest.json").read_text(encoding="utf-8"))
    manifest["canonical_sha256"] = "0" * 64
    (agentic / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="different canonical"):
        run_agentic_benchmark(
            agentic_tree=agentic, frozen_tree=frozen, root=root, counter=COUNTER
        )


def test_a_stale_mapping_is_refused(trees):
    root, agentic, frozen = trees
    mapping_path = agentic / "agentic" / "mapping.json"
    stale = json.loads(mapping_path.read_text(encoding="utf-8"))
    stale["health"] = {"tampered": True}
    mapping_path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="stale"):
        run_agentic_benchmark(
            agentic_tree=agentic, frozen_tree=frozen, root=root, counter=COUNTER
        )


def test_frozen_surface_guards(trees, tmp_path):
    root, agentic, frozen = trees
    with pytest.raises(ValueError, match="inside the frozen benchmark tree"):
        run_agentic_benchmark(
            agentic_tree=frozen / "agentic",
            frozen_tree=frozen,
            root=root,
            counter=COUNTER,
        )
    incomplete = tmp_path / "not-a-benchmark"
    incomplete.mkdir()
    with pytest.raises(ValueError, match="not a completed benchmark tree"):
        run_agentic_benchmark(
            agentic_tree=agentic, frozen_tree=incomplete, root=root, counter=COUNTER
        )
