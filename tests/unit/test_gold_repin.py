from __future__ import annotations

import json

import pytest

from amsc.gold_repin import (
    repin,
    repin_across_renumbering,
    repin_against_text,
    write,
)

from _chunk_fixtures import unit


SHA = "a" * 64


def gold(**overrides):
    payload = {
        "schema_version": "1.0",
        "document_id": "doc",
        "source_units_file": "data/doc.units.jsonl",
        "source_units_sha256": "b" * 64,
        "queries": [
            {
                "query_id": "d001",
                "question": "Soru?",
                "evidence_unit_ids": ["p-1", "p-2"],
                "evidence_pages": [4],
                "expected_answer": "Cevap",
            }
        ],
    }
    payload.update(overrides)
    return payload


def corpus(*, page=4, second_text="beta"):
    first = unit("p-1", "alpha", order=1)
    second = unit("p-2", second_text, order=2)
    first.source.page = page
    second.source.page = page
    return [first, second]


# ------------------------------------------------------------------ accepted


def test_an_unmoved_gold_set_is_repinned_onto_the_new_canonical():
    result = repin(gold(), corpus(), units_path="data/doc.units.v2.jsonl", units_sha256=SHA)

    assert result.ok
    assert result.gold["source_units_sha256"] == SHA
    assert result.gold["source_units_file"] == "data/doc.units.v2.jsonl"
    assert result.checked_unit_ids == ("p-1", "p-2")


def test_the_questions_and_answers_are_carried_over_untouched():
    result = repin(gold(), corpus(), units_path="x", units_sha256=SHA)

    assert result.gold["queries"] == gold()["queries"]


def test_the_original_pin_is_recorded_beside_the_gold_set_not_inside_it():
    """The frozen RetrievalGoldSet forbids unknown keys, so provenance is a sibling."""
    result = repin(gold(), corpus(), units_path="x", units_sha256=SHA)

    assert set(result.gold) == set(gold())
    assert result.provenance["repinned_from"]["source_units_sha256"] == "b" * 64
    assert result.provenance["repinned_from"]["source_units_file"] == "data/doc.units.jsonl"
    assert result.provenance["evidence_unit_ids_verified"] == ["p-1", "p-2"]


# ------------------------------------------------------------------ refused


def test_a_gold_set_whose_evidence_disappeared_is_refused():
    result = repin(gold(), corpus()[:1], units_path="x", units_sha256=SHA)

    assert not result.ok
    assert result.mismatches[0].unit_id == "p-2"
    assert "gone" in result.mismatches[0].reason


def test_a_gold_set_whose_evidence_moved_page_is_refused():
    result = repin(gold(), corpus(page=9), units_path="x", units_sha256=SHA)

    assert not result.ok
    assert {m.unit_id for m in result.mismatches} == {"p-1", "p-2"}


def test_changed_evidence_text_is_only_caught_by_the_stricter_check():
    before, after = corpus(), corpus(second_text="beta rewritten")

    loose = repin(gold(), after, units_path="x", units_sha256=SHA)
    strict = repin_against_text(gold(), before, after, units_path="x", units_sha256=SHA)

    assert loose.ok
    assert not strict.ok
    assert strict.mismatches[0].reason == "evidence text changed"


def test_writing_an_unverified_repin_raises_rather_than_writing(tmp_path):
    result = repin(gold(), corpus()[:1], units_path="x", units_sha256=SHA)
    destination = tmp_path / "gold.json"

    with pytest.raises(ValueError, match="cannot be re-pinned"):
        write(result, destination)
    assert not destination.exists()


def test_writing_a_verified_repin_is_deterministic_json(tmp_path):
    result = repin(gold(), corpus(), units_path="x", units_sha256=SHA)

    destination = write(result, tmp_path / "nested" / "gold.json")
    payload = destination.read_text(encoding="utf-8")

    assert json.loads(payload)["source_units_sha256"] == SHA
    assert payload.endswith("\n")
    assert write(result, tmp_path / "nested" / "again.json").read_text(
        encoding="utf-8"
    ) == payload


def test_the_provenance_lands_next_to_the_gold_file(tmp_path):
    result = repin(gold(), corpus(), units_path="x", units_sha256=SHA)

    destination = write(result, tmp_path / "gold.json")
    sibling = destination.with_suffix(".provenance.json")

    assert sibling.is_file()
    assert json.loads(sibling.read_text(encoding="utf-8"))["repinned_to"][
        "source_units_sha256"
    ] == SHA


# --- carrying a gold set across a renumbering -------------------------------
#
# ``unit_id`` encodes ``order``, so a repair that drops one unit shifts the id
# of every unit after it. The evidence has not moved; only its label has.


def renumbered(*, page=4, second_text="beta"):
    """The same two evidence units after a unit before them was dropped."""
    first = unit("p-0", "alpha", order=0)
    second = unit("p-1", second_text, order=1)
    first.source.page = page
    second.source.page = page
    return [first, second]


def test_a_renumbered_gold_set_is_carried_across_with_new_ids():
    result = repin_across_renumbering(
        gold(), corpus(), renumbered(),
        units_path="data/doc.units.v3.jsonl", units_sha256=SHA,
    )

    assert result.ok
    assert result.gold["queries"][0]["evidence_unit_ids"] == ["p-0", "p-1"]
    assert result.gold["source_units_sha256"] == SHA
    assert result.provenance["evidence_unit_ids_remapped"] == {"p-1": "p-0", "p-2": "p-1"}
    # The question and its answer are never touched.
    assert result.gold["queries"][0]["question"] == "Soru?"
    assert result.gold["queries"][0]["expected_answer"] == "Cevap"


def test_evidence_whose_text_changed_is_refused_not_renamed():
    result = repin_across_renumbering(
        gold(), corpus(), renumbered(second_text="beta rewritten"),
        units_path="data/doc.units.v3.jsonl", units_sha256=SHA,
    )

    assert not result.ok
    assert [m.reason for m in result.mismatches] == ["evidence is gone"]
    with pytest.raises(ValueError):
        write(result, "unused.json")


def test_evidence_that_moved_page_is_refused():
    result = repin_across_renumbering(
        gold(), corpus(), renumbered(page=9),
        units_path="data/doc.units.v3.jsonl", units_sha256=SHA,
    )

    assert not result.ok
    assert len(result.mismatches) == 2


def test_an_ambiguous_anchor_is_as_fatal_as_a_missing_one():
    """Boilerplate printed twice on one page cannot anchor an answer key."""
    twin = unit("p-2", "alpha", order=2)
    twin.source.page = 4
    after = renumbered() + [twin]

    result = repin_across_renumbering(
        gold(), corpus(), after,
        units_path="data/doc.units.v3.jsonl", units_sha256=SHA,
    )

    assert not result.ok
    assert result.mismatches[0].unit_id == "p-1"
    assert "share its page and text" in result.mismatches[0].reason


def test_ids_that_did_not_move_are_not_reported_as_remapped():
    result = repin_across_renumbering(
        gold(), corpus(), corpus(),
        units_path="data/doc.units.v3.jsonl", units_sha256=SHA,
    )

    assert result.ok
    assert result.provenance["evidence_unit_ids_remapped"] == {}
    assert result.gold["queries"][0]["evidence_unit_ids"] == ["p-1", "p-2"]


def test_the_resolved_unit_is_the_same_evidence_field_for_field():
    """The remap is an id change and nothing else.

    Stated as its own test because it is the whole safety claim: the answer key
    still points at the same page, the same unit type and byte-identical text.
    """
    before, after = corpus(), renumbered()
    result = repin_across_renumbering(
        gold(), before, after,
        units_path="data/doc.units.v3.jsonl", units_sha256=SHA,
    )
    assert result.ok

    old_by_id = {u.unit_id: u for u in before}
    new_by_id = {u.unit_id: u for u in after}
    original = gold()["queries"][0]["evidence_unit_ids"]
    resolved = result.gold["queries"][0]["evidence_unit_ids"]
    assert len(original) == len(resolved)
    for old_id, new_id in zip(original, resolved):
        a, b = old_by_id[old_id], new_by_id[new_id]
        assert a.text == b.text
        assert a.type == b.type
        assert a.source.page == b.source.page


def test_evidence_that_changed_type_is_refused():
    """A heading demoted to a paragraph is not the same evidence."""
    demoted = renumbered()
    demoted[1].type = "heading"

    result = repin_across_renumbering(
        gold(), corpus(), demoted,
        units_path="data/doc.units.v3.jsonl", units_sha256=SHA,
    )

    assert not result.ok
    assert [m.unit_id for m in result.mismatches] == ["p-2"]


def test_id_matching_alone_cannot_see_a_renumbering_for_what_it_is():
    """Why the renumbering-aware repin exists, stated as a test.

    After a shift, ``p-1`` still resolves -- to the unit that used to be
    ``p-2``, on the same page. Id matching reports one mismatch, for the id
    that ran off the end, and says nothing at all about the evidence now
    pointing at the wrong text. Anchoring on the text is what catches it.
    """
    shifted = renumbered()

    lenient = repin(gold(), shifted, units_path="p", units_sha256=SHA)
    assert [(m.unit_id, m.reason) for m in lenient.mismatches] == [
        ("p-2", "unit id is gone")
    ]

    strict = repin_across_renumbering(gold(), corpus(), shifted, units_path="p", units_sha256=SHA)
    assert strict.ok
    assert strict.gold["queries"][0]["evidence_unit_ids"] == ["p-0", "p-1"]
