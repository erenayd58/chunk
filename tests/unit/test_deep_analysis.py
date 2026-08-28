"""The Deep Analysis selector, held to its safety contract.

The guarantees under test are the ones the product claim rests on: Standard's
own partition is reproduced exactly (so "Standard wins ties" means something),
coverage and order never change, the hard cap holds, no section ever comes out
with a smell type Standard did not have, and a model vote can only choose
among partitions the deterministic contract already accepts.
"""

from __future__ import annotations

import json

import pytest

from amsc import boundary_quality as bq
from amsc import deep_analysis as da
from amsc.structural_chunker import RENDER_SEPARATOR, _render, _sections
from amsc.structural_chunker import chunk_units as structural_chunk_units

from amsc.models import UnitType

from _chunk_fixtures import WhitespaceCounter, heading, unit, words

COUNTER = WhitespaceCounter()
CONFIG = da.DeepConfig(min_tokens=50, target_tokens=150, soft_max_tokens=160, hard_max_tokens=1000)


def structural(units):
    return structural_chunk_units(
        units,
        counter=COUNTER,
        min_tokens=CONFIG.min_tokens,
        target_tokens=CONFIG.target_tokens,
        soft_max_tokens=CONFIG.soft_max_tokens,
        hard_max_tokens=CONFIG.hard_max_tokens,
        respect_semantic_roles=True,
    )


def deep(units, votes=None):
    return da.chunk_units(units, counter=COUNTER, config=CONFIG, votes=votes)


def replay_standard(units):
    """Assemble Standard's rows out of :func:`standard_groups` alone."""
    rows = []
    for section in _sections(units, COUNTER, CONFIG.hard_max_tokens, True):
        for group in da.standard_groups(section, counter=COUNTER, config=CONFIG):
            rows.append(
                (
                    RENDER_SEPARATOR.join(_render(section.heading, block) for block in group),
                    [piece.unit_id for block in group for piece in block],
                )
            )
    return rows


def plain_corpus():
    """Two oversized sections of ordinary paragraphs: nothing to improve."""
    units = [heading("h-1", "BIR", 1)]
    order = 2
    for index, prefix in enumerate(("A", "B", "C", "D"), start=1):
        units.append(unit(f"p-1{index}", words(60, prefix), order=order, section=("BIR",)))
        order += 1
    units.append(heading("h-2", "IKI", order))
    order += 1
    for index, prefix in enumerate(("E", "F", "G"), start=1):
        units.append(unit(f"p-2{index}", words(60, prefix), order=order, section=("IKI",)))
        order += 1
    return units


def lead_in_corpus():
    """A section whose greedy cut strands a lead-in from its list."""
    units = [heading("h-1", "BIR", 1)]
    units.append(unit("p-11", words(120, "A"), order=2, section=("BIR",)))
    units.append(unit("p-12", words(20, "B") + " şöyle:", order=3, section=("BIR",)))
    units.append(unit("l-13", "- " + words(30, "C"), order=4, section=("BIR",), type=UnitType.LIST))
    units.append(unit("l-14", "- " + words(30, "D"), order=5, section=("BIR",), type=UnitType.LIST))
    return units


def test_standard_groups_reproduce_the_frozen_walk_byte_for_byte():
    for units in (plain_corpus(), lead_in_corpus()):
        expected = structural(units)
        replayed = replay_standard(units)
        assert len(replayed) == len(expected)
        for chunk, (text, unit_ids) in zip(expected, replayed):
            assert chunk["text"] == text
            assert chunk["unit_ids"] == unit_ids


def test_a_corpus_with_nothing_to_improve_is_left_alone():
    units = plain_corpus()
    rows, audit = deep(units)
    expected = structural(units)
    assert audit["sections_moved"] == 0
    assert [row["text"] for row in rows] == [chunk["text"] for chunk in expected]
    assert [row["unit_ids"] for row in rows] == [chunk["unit_ids"] for chunk in expected]


def test_the_selector_keeps_a_lead_in_with_what_it_introduces():
    units = lead_in_corpus()
    standard = structural(units)
    rows, audit = deep(units)
    assert audit["sections_moved"] == 1
    before = bq.measure(units, standard, counter=COUNTER, config=CONFIG.quality())
    after = bq.measure(units, rows, counter=COUNTER, config=CONFIG.quality())
    assert before["totals"]["lead_in_cut"] == 1
    assert after["totals"]["lead_in_cut"] == 0


def test_coverage_and_order_are_never_touched():
    for units in (plain_corpus(), lead_in_corpus()):
        rows, _ = deep(units)
        assert [i for row in rows for i in row["unit_ids"]] == [
            i for chunk in structural(units) for i in chunk["unit_ids"]
        ]


def test_no_section_is_left_structurally_worse():
    for units in (plain_corpus(), lead_in_corpus()):
        rows, _ = deep(units)
        report = bq.compare(
            units, structural(units), rows, counter=COUNTER, config=CONFIG.quality()
        )
        assert report["structural_regression_count"] == 0
        assert report["verdicts_tiered"][bq.VERDICT_WORSE] == 0


def test_the_hard_cap_holds():
    units = lead_in_corpus()
    rows, _ = deep(units)
    assert all(row["token_count"] <= CONFIG.hard_max_tokens for row in rows)


def test_the_result_is_deterministic():
    units = lead_in_corpus()
    first, audit_first = deep(units)
    second, audit_second = deep(units)
    assert first == second
    assert audit_first == audit_second


def test_a_forbidding_vote_removes_a_cut_the_contract_allows():
    units = plain_corpus()
    baseline, _ = deep(units)
    cut_after = baseline[0]["unit_ids"][-1]
    votes = {
        cut_after: da.BoundaryVote(cut_after, strength=0, left=da.ROLE_INTRODUCES_NEXT),
    }
    voted, audit = deep(units, votes=votes)
    assert audit["forbidden_vote_count"] == 1
    assert [row["unit_ids"] for row in voted] != [row["unit_ids"] for row in baseline]
    assert [i for row in voted for i in row["unit_ids"]] == [
        i for row in baseline for i in row["unit_ids"]
    ]


def test_a_vote_cannot_buy_a_smelly_boundary():
    """Strength sits below every smell term, so no vote can strand a lead-in."""
    units = lead_in_corpus()
    without, _ = deep(units)
    lead_in_id = "p-12"
    votes = {lead_in_id: da.BoundaryVote(lead_in_id, strength=3)}
    with_vote, _ = deep(units, votes=votes)
    assert [row["unit_ids"] for row in with_vote] == [row["unit_ids"] for row in without]
    after = bq.measure(units, with_vote, counter=COUNTER, config=CONFIG.quality())
    assert after["totals"]["lead_in_cut"] == 0


def test_a_vote_breaks_a_tie_between_equally_clean_partitions():
    units = plain_corpus()
    baseline, _ = deep(units)
    boundary = baseline[0]["unit_ids"][0]
    votes = {boundary: da.BoundaryVote(boundary, strength=3)}
    voted, audit = deep(units, votes=votes)
    assert audit["vote_count"] == 1
    assert [row["unit_ids"] for row in voted] != [row["unit_ids"] for row in baseline]


def test_cli_refuses_to_write_into_evaluation(tmp_path):
    units_path = tmp_path / "doc.units.jsonl"
    with units_path.open("w", encoding="utf-8") as handle:
        for item in plain_corpus():
            handle.write(item.model_dump_json(exclude_none=True) + "\n")
    with pytest.raises(SystemExit):
        da.main(
            [
                "--input", str(units_path),
                "--output", str(tmp_path / "evaluation" / "out"),
            ]
        )


def test_cli_writes_chunks_and_audit(tmp_path):
    units_path = tmp_path / "doc.units.jsonl"
    with units_path.open("w", encoding="utf-8") as handle:
        for item in lead_in_corpus():
            handle.write(item.model_dump_json(exclude_none=True) + "\n")
    out = tmp_path / "deep"
    da.main(
        [
            "--input", str(units_path), "--output", str(out),
            "--min-tokens", "50", "--target-tokens", "150",
            "--soft-max-tokens", "160", "--hard-max-tokens", "1000",
        ]
    )
    rows = [json.loads(line) for line in (out / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    audit = json.loads((out / "audit.json").read_text(encoding="utf-8"))
    assert rows and audit["section_count"] >= 1
