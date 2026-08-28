"""The Deep Analysis boundary judge, held to its contract.

The load-bearing claims: with no judge (or an all-KEEP judge, or a broken
judge) the output is byte-identical to the structural chunker; the model is
consulted only at plain budget cuts with a real choice, and a whole decision
window costs exactly ONE provider call however many candidates it holds; the
model answers per candidate and never selects the final cut; nothing
free-text ever steers the algorithm; and no API key can reach a prompt or an
audit row.
"""

from __future__ import annotations

import json
import re

import pytest

from amsc.llm_boundary_judge import (
    ELISION,
    JUDGE_ADAPTER_STATUS,
    JudgeConfig,
    OpenAICompatibleJudgeProvider,
    ProductChunkingMode,
    audit_rows,
    chunk_units_with_judge,
    chunk_with_product_mode,
    parse_window_decisions,
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


def wide_corpus(piece_words: int, piece_count: int):
    """One oversized section of equal pieces -- windows with many candidates."""
    units = [heading("h-2", "BUYUK", 1)]
    for index in range(1, piece_count + 1):
        units.append(
            unit(
                f"p-{index}",
                words(piece_words, f"q{index}v"),
                order=index + 1,
                section=("BUYUK",),
            )
        )
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
    """Scripted judge: a static answer, or a callable over the prompt."""

    model_id = "test:fake-judge@1"

    def __init__(self, answer):
        self.answer = answer
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answer(prompt) if callable(self.answer) else self.answer


CANDIDATE_MARKER = re.compile(r"\[CANDIDATE (C\d+) \| cut before \w+ ([\w#-]+)\]")


def scripted(decide):
    """A well-formed judge: one decision per candidate marker in the prompt."""

    def answer(prompt):
        rows = []
        for candidate_id, unit_id in CANDIDATE_MARKER.findall(prompt):
            decision = decide(candidate_id, unit_id)
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "decision": decision,
                    "reason_code": "TOPIC_SHIFT"
                    if decision == "SPLIT"
                    else "CONTINUATION",
                }
            )
        return json.dumps(rows)

    return answer


KEEP_ALL = scripted(lambda candidate_id, unit_id: "KEEP")
SPLIT_ALL = scripted(lambda candidate_id, unit_id: "SPLIT")


def split_before(target_unit_id):
    """SPLIT exactly the candidate that would cut before ``target_unit_id``."""
    return scripted(
        lambda candidate_id, unit_id: "SPLIT"
        if unit_id == target_unit_id
        else "KEEP"
    )


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


def test_a_malformed_candidate_list_refuses_the_whole_window():
    """Missing, duplicate, or unknown candidate ids never half-apply."""
    row = {"candidate_id": "C1", "decision": "SPLIT", "reason_code": "OTHER"}
    for broken in (
        json.dumps([row]),  # missing C2
        json.dumps([row, row]),  # duplicate C1
        json.dumps([row, {**row, "candidate_id": "C9"}]),  # unknown id
        json.dumps([row, "SPLIT"]),  # non-object entry
    ):
        result = chunk_units_with_judge(
            corpus(), counter=COUNTER, judge=FakeJudge(broken), config=CONFIG
        )
        assert result.chunks == structural(corpus())
        assert all(entry.fallback == "parse_error" for entry in result.audit)
        assert all(entry.decisions == () for entry in result.audit)


# --- when the model is consulted --------------------------------------------


def test_the_judge_is_consulted_only_at_ambiguous_budget_cuts():
    judge = FakeJudge(KEEP_ALL)
    chunk_units_with_judge(corpus(), counter=COUNTER, judge=judge, config=CONFIG)

    # One decision window (after the greedy cut the remainder fits the
    # target), offering two admissible cuts -- and exactly ONE provider call.
    assert len(judge.prompts) == 1
    prompt = judge.prompts[0]
    assert "[CANDIDATE C1 | cut before paragraph p-2]" in prompt
    assert "[CANDIDATE C2 | cut before paragraph p-3]" in prompt
    # The small section's text never reaches the model.
    assert SMALL not in prompt
    assert "BUYUK" in prompt


def test_one_window_with_five_candidates_is_one_provider_call():
    # Pieces of 20 tokens against [50, 150]: the first overflow offers the
    # cuts after pieces 3..7 -- five candidates, one window, one call.
    units = wide_corpus(20, 9)
    judge = FakeJudge(KEEP_ALL)
    result = chunk_units_with_judge(units, counter=COUNTER, judge=judge, config=CONFIG)

    assert len(judge.prompts) == 1
    assert result.audit[0].candidate_count == 5
    for ordinal in range(1, 6):
        assert f"[CANDIDATE C{ordinal} | cut before " in judge.prompts[0]
    assert result.diagnostics["provider_call_count"] == 1
    assert result.diagnostics["candidate_decision_count"] == 5
    assert result.chunks == structural(units)


def test_a_fifteen_candidate_window_parses_steers_and_keeps_the_hard_cap():
    # Pieces of 7 tokens against [50, 150]: cuts after pieces 7..21 are all
    # admissible -- the real corpus maximum of 15 candidates in one window.
    units = wide_corpus(7, 24)
    judge = FakeJudge(split_before("p-8"))
    result = chunk_units_with_judge(units, counter=COUNTER, judge=judge, config=CONFIG)

    assert len(judge.prompts) == 1
    assert result.audit[0].candidate_count == 15
    assert result.diagnostics["candidate_decision_count"] == 15
    assert result.diagnostics["split_votes"] == 1
    # The single SPLIT (earliest candidate) moves the cut away from greedy...
    assert result.diagnostics["changed_from_greedy_count"] == 1
    assert result.chunks != structural(units)
    # ...while the hard budget and full unit coverage both hold.
    assert all(
        chunk["token_count"] <= CONFIG.hard_max_tokens for chunk in result.chunks
    )
    covered = [
        unit_id for chunk in result.chunks for unit_id in chunk["unit_ids"]
    ]
    assert covered == [u.unit_id for u in units if not u.unit_id.startswith("h-")]


def test_the_window_prompt_shares_context_and_stays_bounded():
    """Long pieces are excerpted once each, never repeated per candidate."""
    long_words = lambda count, prefix: " ".join(
        f"{prefix}{'x' * 30}{index}" for index in range(count)
    )
    units = [heading("h-2", "BUYUK", 1)]
    for index in range(1, 4):
        units.append(
            unit(
                f"p-{index}",
                long_words(60, f"p{index}"),
                order=index + 1,
                section=("BUYUK",),
            )
        )
    judge = FakeJudge(KEEP_ALL)
    chunk_units_with_judge(units, counter=COUNTER, judge=judge, config=CONFIG)

    assert len(judge.prompts) == 1
    prompt = judge.prompts[0]
    assert ELISION in prompt  # the middle of a long shared piece is elided
    raw_chars = sum(len(u.text) for u in units)
    assert raw_chars > 6000
    assert len(prompt) < 6000
    # Each piece's text appears once; candidates share it instead of
    # repeating it.
    assert prompt.count("[paragraph p-2]") == 1


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
    # The moved cut opens a second window over the remainder: two windows,
    # two calls -- still one call per window.
    assert len(judge.prompts) == 2
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
    assert len(judge.prompts) == 1


# --- the parser -------------------------------------------------------------


def test_parse_window_decisions_contract():
    expected = ["C1", "C2"]
    valid = (
        '[{"candidate_id": "C1", "decision": "split", "reason_code": "harika"},'
        ' {"candidate_id": "C2", "decision": "KEEP",'
        ' "reason_code": "continuation"}]'
    )
    # Decisions are case-insensitive; an unknown reason becomes OTHER because
    # it never steers anything.
    assert parse_window_decisions(valid, expected) == {
        "C1": ("SPLIT", "OTHER"),
        "C2": ("KEEP", "CONTINUATION"),
    }
    # Provider variations that stay safely parseable: markdown fences, an
    # object wrapper, surrounding prose.
    assert parse_window_decisions(f"```json\n{valid}\n```", expected) is not None
    assert (
        parse_window_decisions('{"decisions": ' + valid + "}", expected) is not None
    )
    assert parse_window_decisions(f"Cevap: {valid} olur", expected) is not None
    # Everything that steers is strict: the whole window refuses.
    c1 = '{"candidate_id": "C1", "decision": "SPLIT"}'
    assert parse_window_decisions(f"[{c1}]", expected) is None  # missing C2
    assert parse_window_decisions(f"[{c1}, {c1}]", expected) is None  # duplicate
    assert (
        parse_window_decisions(
            f'[{c1}, {{"candidate_id": "C9", "decision": "KEEP"}}]', expected
        )
        is None
    )  # unknown id
    assert (
        parse_window_decisions(
            f'[{c1}, {{"candidate_id": "C2", "decision": "MAYBE"}}]', expected
        )
        is None
    )  # invalid decision
    assert parse_window_decisions("düz metin, json yok", expected) is None
    assert parse_window_decisions("", expected) is None


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


# --- audit and diagnostics ---------------------------------------------------


def test_the_audit_is_structured_and_serialisable():
    judge = FakeJudge(split_before("p-2"))
    result = chunk_units_with_judge(corpus(), counter=COUNTER, judge=judge, config=CONFIG)

    rows = audit_rows(result)
    payload = json.dumps(rows, ensure_ascii=False)
    assert rows[0]["model_id"] == "test:fake-judge@1"
    assert rows[0]["candidate_count"] == len(rows[0]["decisions"]) == 2
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


def test_diagnostics_count_windows_calls_and_candidate_decisions():
    judge = FakeJudge(KEEP_ALL)
    result = chunk_units_with_judge(corpus(), counter=COUNTER, judge=judge, config=CONFIG)

    diagnostics = result.diagnostics
    assert diagnostics["decision_window_count"] == 1
    assert diagnostics["provider_call_count"] == 1 == len(judge.prompts)
    assert diagnostics["candidate_decision_count"] == 2
    # The v1 spellings stay aliased for downstream readers (chat_rag).
    assert diagnostics["consulted_boundary_count"] == diagnostics["decision_window_count"]
    assert diagnostics["llm_call_count"] == diagnostics["provider_call_count"]
    assert (
        diagnostics["split_votes"] + diagnostics["keep_votes"]
        == diagnostics["candidate_decision_count"]
    )


def test_the_judged_walk_is_deterministic():
    def run():
        result = chunk_units_with_judge(
            corpus(),
            counter=COUNTER,
            judge=FakeJudge(split_before("p-2")),
            config=CONFIG,
        )
        return json.dumps(
            {
                "chunks": result.chunks,
                "audit": audit_rows(result),
                "diagnostics": result.diagnostics,
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    assert run() == run()


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
