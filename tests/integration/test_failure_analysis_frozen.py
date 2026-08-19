from __future__ import annotations

import json
from pathlib import Path

import pytest

from amsc.evaluation import sha256_file


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("relative_path", "expected_sha256", "exact_f1", "plus_minus_one_f1"),
    [
        (
            "evaluation/kkb-2024/baseline/v3/metrics.json",
            "080e14f870b2c4a00386bbc9380cde4192d20ac653aa4cd16ff5c5d7ced2e1ee",
            0.4137931034482759,
            0.5517241379310344,
        ),
        (
            "evaluation/kkb-2024/v4-ablation/a1/metrics.json",
            "441e0f60bbe51dce4f01ab62ab5e604bce8607827ed4f6b50da34a9f5489d8ff",
            0.42857142857142855,
            0.5714285714285715,
        ),
        (
            "evaluation/kkb-2024/v4-ablation/a2/metrics.json",
            "2d1199b33fbe30a30904a3a35e8652b7be208b66cb5f048723cad9724baa8702",
            0.4137931034482759,
            0.5517241379310344,
        ),
        (
            "evaluation/kkb-2024/v4-ablation/a3/metrics.json",
            "526574458997e03a27b9382298146c003e1dbf6dc0b703d1e5a48c4b17f1c570",
            0.42857142857142855,
            0.5714285714285715,
        ),
        (
            "evaluation/kkb-2024/v4-ablation/a4/metrics.json",
            "3c4c7074564a4d6bc6b57ac9514c148fd67d070bf98ec58f5f1c2b960a7296e7",
            0.4444444444444445,
            0.5925925925925926,
        ),
    ],
)
def test_authoritative_a0_a4_metrics_remain_byte_and_value_frozen(
    relative_path: str,
    expected_sha256: str,
    exact_f1: float,
    plus_minus_one_f1: float,
) -> None:
    path = ROOT / relative_path
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert sha256_file(path) == expected_sha256
    assert payload["boundary_metrics"]["secondary_exact"]["f1"] == exact_f1
    assert (
        payload["boundary_metrics"]["primary_plus_minus_one"]["f1"]
        == plus_minus_one_f1
    )


def test_failure_analysis_sources_remain_frozen() -> None:
    assert sha256_file(ROOT / "data/kkb-2024.units.jsonl") == (
        "2776742d5bddad7dcf2a03320dca36e6b384e2ba042ab99ccdecce61612720d5"
    )
    assert sha256_file(
        ROOT / "evaluation/kkb-2024/checkpoint.annotations.json"
    ) == "215db8aed2c4992b4e50dc081824e0cac85ae1aa9381834e8dd52f37bc6e9b9f"
