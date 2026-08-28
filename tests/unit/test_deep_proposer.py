"""The proposer's contract: what is asked, what is accepted, what is refused.

The failures this file exists to prevent are the ones the first live run
produced: a prompt that leaks size into a question about meaning, a marker
offered at a boundary the deterministic layer already forbids, and a parser
that refuses a whole call because the model wrote a role value on the wrong
side of the boundary.
"""

from __future__ import annotations

from amsc import deep_analysis as da
from amsc import deep_proposer as dp
from amsc.models import UnitType

from _chunk_fixtures import WhitespaceCounter, heading, unit, words

COUNTER = WhitespaceCounter()
CONFIG = da.DeepConfig(min_tokens=50, target_tokens=150, soft_max_tokens=160, hard_max_tokens=1000)


def corpus():
    units = [heading("h-1", "BIR", 1)]
    units.append(unit("p-11", words(120, "A"), order=2, section=("BIR",)))
    units.append(unit("p-12", words(20, "B") + " şöyle:", order=3, section=("BIR",)))
    units.append(unit("l-13", "- " + words(30, "C"), order=4, section=("BIR",), type=UnitType.LIST))
    units.append(unit("p-14", words(80, "D"), order=5, section=("BIR",)))
    return units


def test_the_plan_offers_only_deterministically_clean_boundaries():
    units = corpus()
    plans = dp.plan_calls(units, counter=COUNTER, config=CONFIG)
    assert plans
    offered = {b.cut_after_unit_id for plan in plans for b in plan.boundaries}
    # p-12 ends with a colon: cutting there strands a lead-in, so it is never
    # put to the model.
    assert "p-12" not in offered
    assert "p-11" in offered


def test_the_prompt_never_mentions_size():
    units = corpus()
    prompt = dp.plan_calls(units, counter=COUNTER, config=CONFIG)[0].prompt
    lowered = prompt.lower()
    for forbidden in ("token", "chunk", "word count", "length in", "budget"):
        assert forbidden not in lowered
    assert "[B1]" in prompt and "[U1]" in prompt


def test_the_plan_is_deterministic_and_hashes_its_prompt():
    units = corpus()
    first = dp.plan_calls(units, counter=COUNTER, config=CONFIG)
    second = dp.plan_calls(units, counter=COUNTER, config=CONFIG)
    assert [p.prompt_sha256 for p in first] == [p.prompt_sha256 for p in second]
    assert all(p.prompt_sha256 == dp._digest(p.prompt) for p in first)


def test_a_well_formed_answer_parses():
    payload = (
        '{"boundaries": [{"id": "B1", "strength": 3, "before": "finished", '
        '"after": "standalone"}]}'
    )
    parsed, status = dp.parse_proposal(payload, ["B1"])
    assert status == "ok"
    assert parsed["B1"] == (3, da.ROLE_COMPLETE, da.ROLE_COMPLETE)


def test_a_role_written_on_the_wrong_side_is_read_as_neutral():
    """``after: introduces_next`` describes that piece's *other* boundary."""
    payload = (
        '{"boundaries": [{"id": "B1", "strength": 2, "before": "continues_previous", '
        '"after": "introduces_next"}]}'
    )
    parsed, status = dp.parse_proposal(payload, ["B1"])
    assert status == "ok"
    assert parsed["B1"] == (2, da.ROLE_COMPLETE, da.ROLE_COMPLETE)


def test_the_older_key_names_still_parse():
    payload = '{"boundaries": [{"id": "B1", "strength": 0, "left": "complete", "right": "complete"}]}'
    parsed, status = dp.parse_proposal(payload, ["B1"])
    assert status == "ok" and parsed["B1"][0] == 0


def test_a_partial_or_invented_answer_is_refused_whole():
    two = ["B1", "B2"]
    assert dp.parse_proposal('{"boundaries": [{"id": "B1", "strength": 1, "before": "finished", "after": "standalone"}]}', two)[1] == "incomplete"
    assert dp.parse_proposal('{"boundaries": [{"id": "B9", "strength": 1, "before": "finished", "after": "standalone"}]}', ["B1"])[1] == "unknown_or_duplicate_id"
    assert dp.parse_proposal('{"boundaries": [{"id": "B1", "strength": 7, "before": "finished", "after": "standalone"}]}', ["B1"])[1] == "malformed_row"
    assert dp.parse_proposal('{"boundaries": [{"id": "B1", "strength": 1, "before": "maybe", "after": "standalone"}]}', ["B1"])[1] == "malformed_row"
    assert dp.parse_proposal("not json at all", ["B1"])[1] == "unparsable"
    assert dp.parse_proposal(None, ["B1"])[1] == "no_response"


def test_votes_are_folded_per_boundary_with_an_audit():
    units = corpus()
    plans = dp.plan_calls(units, counter=COUNTER, config=CONFIG)
    plan = plans[0]
    body = ", ".join(
        f'{{"id": "{b.label}", "strength": 3, "before": "introduces_next", "after": "standalone"}}'
        for b in plan.boundaries
    )
    outcomes = [dp.CallOutcome(plan.call_id, "ok", f'{{"boundaries": [{body}]}}')]
    votes, audit = dp.votes_from_outcomes([plan], outcomes)
    assert set(votes) == {b.cut_after_unit_id for b in plan.boundaries}
    assert all(vote.forbidden for vote in votes.values())
    assert audit[0].status == "ok"
    assert audit[0].forbidden == len(plan.boundaries)
    summary = dp.summarise(audit)
    assert summary["call_status"] == {"ok": 1}
    assert summary["prompt_template_version"] == dp.PROMPT_TEMPLATE_VERSION


def test_a_failed_call_yields_no_votes_and_is_recorded():
    units = corpus()
    plan = dp.plan_calls(units, counter=COUNTER, config=CONFIG)[0]
    votes, audit = dp.votes_from_outcomes(
        [plan], [dp.CallOutcome(plan.call_id, "provider_error", None)]
    )
    assert votes == {}
    assert audit[0].status == "no_response" and audit[0].transport == "provider_error"
