from __future__ import annotations

import json
from pathlib import Path

from amsc.evaluation import load_jsonl_objects


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "evaluation" / "kkb-2024" / "phase3c-semantic-comparators"
BASELINE = ROOT / "evaluation" / "kkb-2024" / "baseline" / "v3"


def test_c0_is_byte_identical_authoritative_v3() -> None:
    for name in (
        "chunks.jsonl",
        "boundaries.jsonl",
        "metrics.json",
        "resolved-config.json",
    ):
        assert (RESEARCH / "c0" / name).read_bytes() == (BASELINE / name).read_bytes()


def test_comparator_provenance_is_deterministic_and_parameter_free() -> None:
    c1 = load_jsonl_objects(RESEARCH / "c1" / "comparator-provenance.jsonl")
    c2 = load_jsonl_objects(RESEARCH / "c2" / "comparator-provenance.jsonl")
    assert len(c1) == len(c2) == 1328
    assert {row["boundary_index"] for row in c1} == set(range(1328))
    assert {row["boundary_index"] for row in c2} == set(range(1328))
    assert {row["method_id"] for row in c1} == {"local_semantic_prominence"}
    assert {row["method_id"] for row in c2} == {"cosine_kernel_change_point"}
    assert {row["threshold_estimator"] for row in c1 + c2} == {
        "frozen_hierarchical_adaptive"
    }
    assert {row["window_size"] for row in c2} == {1, 2, 3}


def test_phase3c_summary_distinguishes_metric_gain_from_semantic_rescue() -> None:
    summary = json.loads((RESEARCH / "summary.json").read_text(encoding="utf-8"))
    assert summary["gold_parameter_tuning"] is False
    assert summary["validated"] is False
    assert summary["winner_for_c3"] == "c2"
    assert summary["runs"]["c0"]["plus_minus_one"]["f1"] == 0.5517241379310344
    assert summary["runs"]["c2"]["plus_minus_one"]["f1"] == 0.6451612903225806
    assert summary["runs"]["c3"]["plus_minus_one"]["f1"] == 0.6666666666666666
    assert summary["genuine_semantic_rescues"] == {
        "c1": [],
        "c2": [],
        "c3": [],
    }
    assert summary["regressed_previously_matched_high"]["c2"] == []
    assert summary["regressed_previously_matched_high"]["c3"] == []


def test_c3_preserves_frozen_hard_limit_merge_ban() -> None:
    chunks = load_jsonl_objects(RESEARCH / "c3" / "chunks.jsonl")
    decisions = {
        item["proposal_id"]: item
        for chunk in chunks
        for item in chunk.get("merge_decisions") or []
    }
    assert len(decisions) == 7
    assert sum(item["accepted"] for item in decisions.values()) == 3
    assert not any(
        item["accepted"]
        and item["boundary_original_reason"] == "hard_limit_fallback"
        for item in decisions.values()
    )
