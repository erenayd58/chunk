from __future__ import annotations

from amsc.models import RawDocumentUnit
from amsc.units import HeadingAttachmentBuilder, RenderedTokenBudgeter
from conftest import WordTokenCounter


def raw(**changes):
    payload = {
        "document_id": "doc",
        "unit_id": "p1",
        "order": 1,
        "text": "one two three",
        "type": "paragraph",
        "section_path": ["A"],
        "source": {"page": 1, "block": 1},
    }
    payload.update(changes)
    return RawDocumentUnit.model_validate(payload)


def test_consecutive_headings_attach_but_are_not_semantic_text() -> None:
    budgeter = RenderedTokenBudgeter(WordTokenCounter(), hard_max_tokens=20)
    builder = HeadingAttachmentBuilder(budgeter)
    units = builder.build(
        [
            raw(unit_id="h1", order=1, text="Main", type="heading", heading_level=1),
            raw(unit_id="h2", order=2, text="Sub", type="heading", heading_level=2),
            raw(unit_id="p1", order=3, text="body words"),
        ]
    )
    assert len(units) == 1
    assert units[0].text_for_embedding == "body words"
    assert units[0].rendered_text == "Main\nSub\n\nbody words"
    assert units[0].raw_unit_ids == ("h1", "h2", "p1")


def test_heading_budget_is_applied_before_content_split() -> None:
    counter = WordTokenCounter()
    budgeter = RenderedTokenBudgeter(counter, hard_max_tokens=10)
    builder = HeadingAttachmentBuilder(budgeter)
    units = builder.build(
        [
            raw(
                unit_id="h1",
                order=1,
                text="heading takes three",
                type="heading",
                heading_level=1,
            ),
            raw(unit_id="p1", order=2, text=" ".join(f"w{i}" for i in range(12))),
        ]
    )
    assert len(units) >= 2
    assert all(counter.count(unit.rendered_text) <= 10 for unit in units)
    assert units[0].heading_text == "heading takes three"
    assert all(not unit.heading_text for unit in units[1:])


def test_dangling_heading_becomes_nonsemantic_unit() -> None:
    budgeter = RenderedTokenBudgeter(WordTokenCounter(), hard_max_tokens=10)
    units = HeadingAttachmentBuilder(budgeter).build(
        [
            raw(unit_id="p1", order=1),
            raw(unit_id="h1", order=2, text="Tail", type="heading", heading_level=2),
        ]
    )
    assert units[-1].text_for_embedding is None
    assert units[-1].rendered_text == "Tail"


def test_oversized_heading_is_split_under_cap() -> None:
    counter = WordTokenCounter()
    budgeter = RenderedTokenBudgeter(counter, hard_max_tokens=4)
    units = HeadingAttachmentBuilder(budgeter).build(
        [
            raw(
                unit_id="h1",
                order=1,
                text="one two three four five six",
                type="heading",
                heading_level=1,
            )
        ]
    )
    assert len(units) == 2
    assert all(unit.forced_split_reason == "oversized_heading_split" for unit in units)
    assert all(counter.count(unit.rendered_text) <= 4 for unit in units)

