from __future__ import annotations

from pathlib import Path

from amsc.evaluation import sha256_file
from amsc.io import load_jsonl_units
from amsc.retrieval_benchmark import RetrievalGoldSet, _validate_gold


ROOT = Path(__file__).resolve().parents[2]


def test_manual_retrieval_gold_matches_frozen_canonical_input() -> None:
    units_path = ROOT / "data" / "kkb-2024.units.jsonl"
    gold_path = (
        ROOT / "evaluation" / "kkb-2024" / "retrieval-benchmark" / "gold-queries.json"
    )
    units = load_jsonl_units(units_path)
    gold = RetrievalGoldSet.model_validate_json(gold_path.read_text(encoding="utf-8"))

    _validate_gold(gold, units, sha256_file(units_path))

    assert len(gold.queries) == 50
    assert all(query.expected_answer for query in gold.queries)
    assert "before any retrieval outputs" in gold.authoring_method

