"""The product entry point: modes, statuses and the failure policy.

What a caller must be able to rely on: Standard is the frozen walk; Deep
without a usable model is the deterministic contract and says so; a
provider that fails on every call degrades to the same partition rather
than raising; and a well-formed model answer reaches the selector.
"""

from __future__ import annotations

import json

import pytest

from amsc import deep_analysis as da
from amsc import deep_pipeline as pipe
from amsc.deep_run import write_tree
from amsc.models import UnitType
from amsc.structural_chunker import chunk_units as structural_chunk_units

from _chunk_fixtures import WhitespaceCounter, heading, unit, words

COUNTER = WhitespaceCounter()
CONFIG = da.DeepConfig(min_tokens=50, target_tokens=150, soft_max_tokens=160, hard_max_tokens=1000)
SETTINGS = pipe.DeepAnalysisSettings(config=CONFIG, api_key_env="AMSC_TEST_KEY_THAT_IS_UNSET")


def corpus():
    units = [heading("h-1", "BIR", 1)]
    units.append(unit("p-11", words(120, "A"), order=2, section=("BIR",)))
    units.append(unit("p-12", words(20, "B") + " şöyle:", order=3, section=("BIR",)))
    units.append(unit("l-13", "- " + words(30, "C"), order=4, section=("BIR",), type=UnitType.LIST))
    units.append(unit("p-14", words(80, "D"), order=5, section=("BIR",)))
    units.append(unit("p-15", words(70, "E"), order=6, section=("BIR",)))
    return units


def standard(units):
    return structural_chunk_units(
        units,
        counter=COUNTER,
        min_tokens=CONFIG.min_tokens,
        target_tokens=CONFIG.target_tokens,
        soft_max_tokens=CONFIG.soft_max_tokens,
        hard_max_tokens=CONFIG.hard_max_tokens,
        respect_semantic_roles=True,
    )


class FailingProvider:
    model_id = "test/failing@1"

    def complete(self, prompt: str) -> str:
        raise ConnectionError("endpoint unreachable")


class AnsweringProvider:
    """Answers every marked boundary with a neutral, complete vote."""

    model_id = "test/answering@1"

    def __init__(self):
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if "DIVISION ONE" in prompt:
            return '{"better": "EQUAL"}'
        labels = sorted(set(__import__("re").findall(r"\[(B\d+)\]", prompt)))
        rows = [
            {"id": label, "strength": 2, "before": "finished", "after": "standalone"}
            for label in labels
        ]
        return json.dumps({"boundaries": rows})


def test_standard_mode_is_the_frozen_walk():
    units = corpus()
    result = pipe.chunk_document(units, mode="standard", settings=SETTINGS, counter=COUNTER)
    assert result.status == pipe.STATUS_OK and result.mode == "standard"
    assert [row["unit_ids"] for row in result.rows] == [row["unit_ids"] for row in standard(units)]
    assert result.report["uses_llm"] is False and result.deep is None


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        pipe.chunk_document(corpus(), mode="turbo", settings=SETTINGS, counter=COUNTER)


def test_deep_without_a_key_falls_back_to_the_deterministic_contract(monkeypatch):
    monkeypatch.delenv(SETTINGS.api_key_env, raising=False)
    units = corpus()
    result = pipe.chunk_document(units, mode="deep", settings=SETTINGS, counter=COUNTER)
    deterministic, _ = da.chunk_units(units, counter=COUNTER, config=CONFIG)
    assert result.status == pipe.STATUS_FALLBACK_NO_PROVIDER
    assert result.error and "never stored" in result.error
    assert [row["unit_ids"] for row in result.rows] == [row["unit_ids"] for row in deterministic]
    assert result.report["structural_regression_count"] == 0
    assert result.report["uses_llm"] is False
    assert "fallback_reason" in result.report


def test_a_provider_that_always_fails_degrades_without_raising():
    units = corpus()
    result = pipe.chunk_document(
        units, mode="deep", settings=SETTINGS, counter=COUNTER, provider=FailingProvider()
    )
    deterministic, _ = da.chunk_units(units, counter=COUNTER, config=CONFIG)
    assert result.status == pipe.STATUS_FALLBACK_PROVIDER_ERROR
    assert [row["unit_ids"] for row in result.rows] == [row["unit_ids"] for row in deterministic]
    assert result.report["proposer"]["transport_status"] == {"provider_error": result.report["proposer"]["call_count"]}


def test_a_well_formed_answer_reaches_the_selector_and_the_verifier():
    units = corpus()
    provider = AnsweringProvider()
    result = pipe.chunk_document(
        units, mode="deep", settings=SETTINGS, counter=COUNTER, provider=provider
    )
    assert result.status == pipe.STATUS_OK
    assert result.report["uses_llm"] is True
    assert result.report["proposer"]["call_status"] == {"ok": result.report["proposer"]["call_count"]}
    assert provider.calls >= result.report["proposer"]["call_count"]
    # Every guarantee survives a model in the loop.
    assert result.report["structural_regression_count"] == 0
    assert all(row["token_count"] <= CONFIG.hard_max_tokens for row in result.rows)
    assert [i for row in result.rows for i in row["unit_ids"]] == [
        i for row in standard(units) for i in row["unit_ids"]
    ]
    assert "llm_effect" in result.report


def test_the_report_carries_no_prompt_text_or_secret(monkeypatch):
    monkeypatch.setenv("AMSC_TEST_KEY_PRESENT", "sk-test-secret-value")
    settings = pipe.DeepAnalysisSettings(config=CONFIG, api_key_env="AMSC_TEST_KEY_PRESENT")
    result = pipe.chunk_document(
        corpus(), mode="deep", settings=settings, counter=COUNTER, provider=AnsweringProvider()
    )
    dumped = json.dumps(result.report, ensure_ascii=False)
    assert "sk-test-secret-value" not in dumped
    assert "[U1]" not in dumped and "DIVISION" not in dumped


def test_build_providers_refuses_without_a_key_and_names_the_variable(monkeypatch):
    monkeypatch.delenv(SETTINGS.api_key_env, raising=False)
    with pytest.raises(RuntimeError) as error:
        pipe.build_providers(SETTINGS)
    assert SETTINGS.api_key_env in str(error.value)
    assert pipe.build_providers(pipe.DeepAnalysisSettings(config=CONFIG, use_llm=False)) == (None, None)


def test_write_tree_writes_the_runner_layout(tmp_path):
    units = corpus()
    result = pipe.run_deep_analysis(
        units,
        counter=COUNTER,
        settings=pipe.DeepAnalysisSettings(config=CONFIG),
        provider=AnsweringProvider(),
    )
    summary = write_tree(result, tmp_path / "tree", units_path=tmp_path / "doc.jsonl")
    for name in (
        "chunks.jsonl", "selection-audit.json", "quality-vs-standard.json", "summary.json",
        "proposer/calls.jsonl", "proposer/responses.jsonl", "proposer/audit.jsonl",
    ):
        assert (tmp_path / "tree" / name).is_file(), name
    assert summary["mode"] == "live" and summary["status"] == pipe.STATUS_OK
    calls = (tmp_path / "tree" / "proposer" / "calls.jsonl").read_text(encoding="utf-8")
    assert "prompt_sha256" in calls and "[U1]" not in calls
