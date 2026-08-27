"""The Deep Analysis boundary judge, held to its contract.

The load-bearing claims: with no judge (or an all-KEEP judge, or a broken
judge) the output is byte-identical to the structural chunker; the model is
consulted only at plain budget cuts with a real choice; label seams stay
structural; nothing free-text ever steers the algorithm; and no API key can
reach a prompt or an audit row.
"""

from __future__ import annotations

import json

import pytest

from amsc.llm_boundary_judge import (
    JUDGE_ADAPTER_STATUS,
    JudgeConfig,
    OpenAICompatibleJudgeProvider,
    ProductChunkingMode,
    audit_rows,
    chunk_units_with_judge,
    chunk_with_product_mode,
    parse_decision,
)
from amsc.models import RawDocumentUnit, UnitType
from amsc.structural_chunker import chunk_units as structural_chunk_units

from _chunk_fixtures import WhitespaceCounter, heading, unit, words

COUNTER = WhitespaceCounter()

CONFIG = JudgeConfig(
    min_tokens=50,
    target_tokens=150,
    soft_max_tokens=160,
    hard_max_tokens=1000,
    respect_semantic_roles=False,
)

BODIES = [words(60, "a"), words(60, "b"), words(60, "c"), words(60, "d")]
SMALL = words(30, "s")


def corpus():
    """A small section that fits, then an oversized one that must split."""
    units = [heading("h-1", "KUCUK", 1), unit("p-0", SMALL, order=2, section=("KUCUK",))]
    units.append(heading("h-2", "BUYUK", 3))
    for index, body in enumerate(BODIES, start=1):
        units.append(unit(f"p-{index}", body, order=index + 3, section=("BUYUK",)))
    return units


def structural(units, *, respect=False):
    return structural_chunk_units(
        units,
        counter=COUNTER,
        min_tokens=50,
        target_tokens=150,
        soft_max_tokens=160,
        hard_max_tokens=1000,
        respect_semantic_roles=respect,
    )


class FakeJudge:
    """Scripted judge: decides from the candidate's after-unit id."""

    model_id = "test:fake-judge@1"

    def __init__(self, answer):
        self.answer = answer
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answer(prompt) if callable(self.answer) else self.answer


KEEP_ALL = '{"decision": "KEEP", "reason_code": "CONTINUATION"}'
SPLIT_ALL = '{"decision": "SPLIT", "reason_code": "TOPIC_SHIFT"}'


def split_before(unit_id):
    def answer(prompt):
        if f"after the candidate boundary [paragraph {unit_id}]" in prompt:
            return SPLIT_ALL
        return KEEP_ALL

    return answer


# --- fallback skeleton: byte-identical to structure-only --------------------


def test_no_judge_is_byte_identical_to_structure_only():
    result = chunk_units_with_judge(corpus(), counter=COUNTER, judge=None, config=CONFIG)
    assert result.chunks == structural(corpus())
    assert result.mode is ProductChunkingMode.STANDARD
    assert result.audit == ()


def test_an_all_keep_judge_changes_nothing_and_the_audit_says_why():
    judge = FakeJudge(KEEP_ALL)
    result = chunk_units_with_judge(corpus(), counter=COUNTER, judge=judge, config=CONFIG)

    assert result.chunks == structural(corpus())
    assert result.diagnostics["changed_from_greedy_count"] == 0
    assert result.diagnostics["fallback_count"] == 0
    assert all(entry.fallback == "forced_greedy_all_keep" for entry in result.audit)
    assert all(entry.chosen_equals_greedy for entry in result.audit)


def test_garbage_output_falls_back_to_the_structural_cut():
    judge = FakeJudge("elbette! bu sınırda ...")
    result = chunk_units_with_judge(corpus(), counter=COUNTER, judge=judge, config=CONFIG)

    assert result.chunks == structural(corpus())
    assert result.diagnostics["fallback_count"] == len(result.audit) > 0
    assert all(entry.fallback == "parse_error" for entry in result.audit)


def test_a_raising_provider_falls_back_to_the_structural_cut():
    class Broken(FakeJudge):
        def complete(self, prompt):
            raise RuntimeError("gateway down")

    result = chunk_units_with_judge(
        corpus(), counter=COUNTER, judge=Broken(KEEP_ALL), config=CONFIG
    )

    assert result.chunks == structural(corpus())
    assert all(entry.fallback == "provider_error" for entry in result.audit)


# --- when the model is consulted --------------------------------------------


def test_the_judge_is_consulted_only_at_ambiguous_budget_cuts():
    judge = FakeJudge(KEEP_ALL)
    chunk_units_with_judge(corpus(), counter=COUNTER, judge=judge, config=CONFIG)

    # One planning step (after the greedy cut the remainder fits the
    # target), offering exactly two admissible cuts.
    assert len(judge.prompts) == 2
    # The small section's text never reaches the model.
    assert all(SMALL not in prompt for prompt in judge.prompts)
    assert all("BUYUK" in prompt for prompt in judge.prompts)


def test_a_label_seam_is_structures_own_cut_and_never_consults_the_model():
    label = RawDocumentUnit(
        document_id="doc",
        unit_id="h-9",
        order=4,
        text="ARA ETIKET",
        type=UnitType.HEADING,
        heading_level=3,
        section_path=["BUYUK"],
        semantic_role="item",
        opens_section=False,
    )
    units = [heading("h-2", "BUYUK", 1)]
    units.append(unit("p-1", BODIES[0], order=2, section=("BUYUK",)))
    units.append(unit("p-2", BODIES[1], order=3, section=("BUYUK",)))
    units.append(label)
    units.append(unit("p-3", BODIES[2], order=5, section=("BUYUK",)))

    judge = FakeJudge(SPLIT_ALL)
    result = chunk_units_with_judge(
        units,
        counter=COUNTER,
        judge=judge,
        config=JudgeConfig(**{**CONFIG.__dict__, "respect_semantic_roles": True}),
    )

    assert judge.prompts == []  # the only cut is the label seam
    assert result.chunks == structural(units, respect=True)


# --- how a SPLIT steers the cut ---------------------------------------------


def test_a_split_vote_moves_the_cut_to_the_approved_candidate():
    judge = FakeJudge(split_before("p-2"))
    result = chunk_units_with_judge(corpus(), counter=COUNTER, judge=judge, config=CONFIG)

    big = [chunk for chunk in result.chunks if chunk["heading"] == "BUYUK"]
    assert [chunk["unit_ids"] for chunk in big] == [["p-1"], ["p-2", "p-3"], ["p-4"]]
    assert result.diagnostics["changed_from_greedy_count"] == 1
    # Greedy would have taken [p-1, p-2] -- pinned against the real baseline.
    greedy_big = [c for c in structural(corpus()) if c["heading"] == "BUYUK"]
    assert greedy_big[0]["unit_ids"] == ["p-1", "p-2"]


def test_among_several_splits_the_latest_wins():
    judge = FakeJudge(SPLIT_ALL)
    result = chunk_units_with_judge(corpus(), counter=COUNTER, judge=judge, config=CONFIG)

    # Every candidate approved => the greedy position is chosen at every step.
    assert result.chunks == structural(corpus())
    assert result.diagnostics["changed_from_greedy_count"] == 0
    assert result.diagnostics["split_votes"] == 2


# --- the parser -------------------------------------------------------------


def test_parse_decision_contract():
    assert parse_decision('{"decision": "SPLIT", "reason_code": "TOPIC_SHIFT"}') == (
        "SPLIT",
        "TOPIC_SHIFT",
    )
    assert parse_decision('Cevap: {"decision": "keep", "reason_code": "continuation"} olur') == (
        "KEEP",
        "CONTINUATION",
    )
    assert parse_decision('{"decision": "SPLIT", "reason_code": "harika"}') == (
        "SPLIT",
        "OTHER",
    )
    assert parse_decision('{"decision": "MAYBE"}') is None
    assert parse_decision("düz metin, json yok") is None
    assert parse_decision("") is None


# --- product mode -----------------------------------------------------------


def test_standard_product_mode_is_structure_only():
    result = chunk_with_product_mode(
        corpus(), counter=COUNTER, mode=ProductChunkingMode.STANDARD, config=CONFIG
    )
    assert result.chunks == structural(corpus())
    assert result.diagnostics["llm_boundary_judge"] is False


def test_deep_analysis_without_a_judge_is_an_error():
    with pytest.raises(ValueError, match="needs a boundary judge"):
        chunk_with_product_mode(
            corpus(),
            counter=COUNTER,
            mode=ProductChunkingMode.DEEP_ANALYSIS,
            config=CONFIG,
        )


# --- audit ------------------------------------------------------------------


def test_the_audit_is_structured_and_serialisable():
    judge = FakeJudge(split_before("p-2"))
    result = chunk_units_with_judge(corpus(), counter=COUNTER, judge=judge, config=CONFIG)

    rows = audit_rows(result)
    payload = json.dumps(rows, ensure_ascii=False)
    assert rows[0]["model_id"] == "test:fake-judge@1"
    assert rows[0]["decisions"][0]["decision"] in ("SPLIT", "KEEP")
    assert rows[0]["decisions"][0]["reason_code"] in (
        "TOPIC_SHIFT",
        "CONTINUATION",
        "LIST_CONTINUATION",
        "TABLE_CONTINUATION",
        "NEW_SUBTOPIC",
        "OTHER",
    )
    # No free text travels: every field is an id, an enum, a count or a flag.
    allowed = {
        "section_heading", "section_path", "step", "candidate_count",
        "decisions", "chosen_after_unit_id", "chosen_equals_greedy",
        "fallback", "model_id",
    }
    assert set(rows[0]) == allowed
    assert "elbette" not in payload


# --- the adapter and the key ------------------------------------------------


def test_the_adapter_is_marked_not_verified_and_hardcodes_no_model():
    assert OpenAICompatibleJudgeProvider.status == JUDGE_ADAPTER_STATUS
    with pytest.raises(TypeError):
        OpenAICompatibleJudgeProvider(endpoint="https://example.invalid/v1")  # model required


def test_the_key_env_is_configurable_and_a_missing_key_is_loud(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    provider = OpenAICompatibleJudgeProvider(
        "company/minimax-class-model",
        endpoint="https://gateway.example.invalid/v1/chat/completions",
        api_key_env="MINIMAX_API_KEY",
    )
    with pytest.raises(RuntimeError, match="MINIMAX_API_KEY"):
        provider.complete("prompt")


def test_no_key_reaches_prompts_or_audit(monkeypatch):
    sentinel = "sk-JUDGE-SENTINEL-NEVER-PERSIST"
    monkeypatch.setenv("OPENROUTER_API_KEY", sentinel)

    judge = FakeJudge(KEEP_ALL)
    result = chunk_units_with_judge(corpus(), counter=COUNTER, judge=judge, config=CONFIG)

    surface = "\n".join(judge.prompts) + json.dumps(audit_rows(result)) + json.dumps(
        result.diagnostics
    )
    assert sentinel not in surface
