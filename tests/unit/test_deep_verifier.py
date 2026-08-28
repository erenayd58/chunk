"""The verifier's contract: unanimity, both orders, and a free revert.

Position bias is not hypothetical here -- on KKB 2024 the two orders
disagreed on 23 of 46 groups, so a single-order check would have accepted
whatever happened to be printed second half the time.
"""

from __future__ import annotations

from amsc import deep_verifier as dv
from amsc.agentic_chunker import CallOutcome
from amsc.structural_chunker import Section, Piece


def piece(unit_id: str, text: str, tokens: int = 10) -> Piece:
    return Piece(unit_id, text, tokens, 1, ("S",), "whole")


def section() -> Section:
    return Section(
        heading="S",
        section_path=("S",),
        pieces=[piece(f"p-{index}", f"metin {index}") for index in range(6)],
    )


def test_change_groups_are_the_spans_between_shared_cuts():
    groups = dv.change_groups((2, 4), (2, 5), 6, section_index=3, heading="S")
    assert len(groups) == 1
    group = groups[0]
    assert (group.start, group.end) == (2, 6)
    assert group.base_cuts == (4,) and group.proposed_cuts == (5,)
    assert group.section_index == 3


def test_identical_partitions_have_no_groups():
    assert dv.change_groups((2, 4), (2, 4), 6, section_index=0, heading=None) == []


def test_each_group_is_asked_twice_in_both_orders():
    groups = dv.change_groups((2,), (3,), 6, section_index=0, heading="S")
    plans = dv.plan_comparisons([section()], groups)
    assert len(plans) == 2
    assert {plan.first for plan in plans} == {"base", "proposed"}
    assert plans[0].prompt != plans[1].prompt
    assert all("DIVISION ONE" in plan.prompt and "DIVISION TWO" in plan.prompt for plan in plans)
    # No scores, no marker ids, no arm names leak into the question.
    for plan in plans:
        assert "strength" not in plan.prompt and "deterministic" not in plan.prompt


def _outcomes(plans, answers):
    return [
        CallOutcome(plan.call_id, "ok", None if answer is None else '{"better": "%s"}' % answer)
        for plan, answer in zip(plans, answers)
    ]


def _decide(answers):
    groups = dv.change_groups((2,), (3,), 6, section_index=0, heading="S")
    plans = dv.plan_comparisons([section()], groups)
    verdicts = dv.decide(groups, plans, _outcomes(plans, answers))
    return groups, verdicts[0]


def test_a_proposal_is_kept_only_when_it_wins_both_orders():
    # order 1 shows base first, order 2 shows proposed first
    _groups, verdict = _decide(["TWO", "ONE"])
    assert verdict.accepted and verdict.reason == "unanimous"


def test_an_order_dependent_answer_reverts():
    _groups, verdict = _decide(["ONE", "ONE"])
    assert not verdict.accepted and verdict.reason == "order_dependent"


def test_a_preference_for_the_baseline_reverts():
    _groups, verdict = _decide(["ONE", "TWO"])
    assert not verdict.accepted and verdict.reason == "base_preferred"


def test_equal_and_missing_answers_revert():
    assert _decide(["EQUAL", "EQUAL"])[1].reason == "equal"
    assert not _decide([None, "ONE"])[1].accepted


def test_merge_takes_the_proposal_only_inside_accepted_groups():
    groups = dv.change_groups((2, 4), (2, 5), 6, section_index=0, heading="S")
    accepted = {groups[0].key: True}
    assert dv.merge_cuts((2, 4), (2, 5), groups, accepted) == (2, 5)
    assert dv.merge_cuts((2, 4), (2, 5), groups, {groups[0].key: False}) == (2, 4)


def test_parsing_is_strict():
    assert dv.parse_comparison('{"better": "ONE"}') == ("ONE", "ok")
    assert dv.parse_comparison('noise {"better":"two"} tail')[0] == "TWO"
    assert dv.parse_comparison('{"better": "THREE"}')[1] == "malformed"
    assert dv.parse_comparison("not json")[1] == "unparsable"
    assert dv.parse_comparison(None)[1] == "no_response"


def test_summary_counts_reasons():
    groups = dv.change_groups((2,), (3,), 6, section_index=0, heading="S")
    plans = dv.plan_comparisons([section()], groups)
    verdicts = dv.decide(groups, plans, _outcomes(plans, ["TWO", "ONE"]))
    summary = dv.summarise(verdicts)
    assert summary["accepted"] == 1 and summary["reverted"] == 0
    assert summary["reasons"] == {"unanimous": 1}
    assert summary["prompt_template_version"] == dv.PROMPT_TEMPLATE_VERSION
