from __future__ import annotations

import json
from pathlib import Path

from amsc.evaluation import load_jsonl_objects


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "evaluation" / "kkb-2024" / "v5-scale-calibration"
BASELINE = ROOT / "evaluation" / "kkb-2024" / "baseline" / "v3"


def test_b0_core_artifacts_are_byte_identical_to_authoritative_v3() -> None:
    for name in (
        "chunks.jsonl",
        "boundaries.jsonl",
        "metrics.json",
        "resolved-config.json",
    ):
        assert (RESEARCH / "b0" / name).read_bytes() == (BASELINE / name).read_bytes()


def test_b1_is_diagnostic_only_and_has_per_scale_provenance() -> None:
    assert (RESEARCH / "b1" / "chunks.jsonl").read_bytes() == (
        BASELINE / "chunks.jsonl"
    ).read_bytes()
    assert (RESEARCH / "b1" / "boundaries.jsonl").read_bytes() == (
        BASELINE / "boundaries.jsonl"
    ).read_bytes()
    rows = load_jsonl_objects(RESEARCH / "b1" / "scale-calibration.jsonl")
    boundaries = load_jsonl_objects(BASELINE / "boundaries.jsonl")
    assert len(rows) == len(boundaries)
    interior = next(row for row in rows if row["available_scales"] == [1, 2, 3])
    for scale in (1, 2, 3):
        assert f"shift_{scale}" in interior
        assert f"threshold_{scale}" in interior
        assert f"candidate_{scale}" in interior
        assert f"calibrated_evidence_{scale}" in interior
    assert "fused_evidence" in interior


def test_research_summary_preserves_control_and_rejects_validation_claim() -> None:
    summary = json.loads((RESEARCH / "summary.json").read_text(encoding="utf-8"))
    assert summary["b0_byte_identical"] is True
    assert summary["runs"]["b0"]["plus_minus_one"]["f1"] == 0.5517241379310344
    assert summary["runs"]["b1"]["plus_minus_one"]["f1"] == 0.5517241379310344
    assert summary["validation_claim"] == "not_validated_requires_second_document_holdout"
    assert summary["hypothesis_supported"] is False
    assert summary["suppression_case_count"] == 5
    assert summary["suppression_semantic_rescued_b2"] == 0
    assert summary["suppression_semantic_rescued_b3"] == 0


def test_b3_keeps_frozen_hard_limit_merge_ban() -> None:
    chunks = load_jsonl_objects(RESEARCH / "b3" / "chunks.jsonl")
    accepted_hard_limit = [
        decision
        for chunk in chunks
        for decision in chunk.get("merge_decisions") or []
        if decision.get("accepted")
        and decision.get("boundary_original_reason") == "hard_limit_fallback"
    ]
    assert accepted_hard_limit == []
