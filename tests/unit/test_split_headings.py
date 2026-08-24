from __future__ import annotations

from dataclasses import dataclass

from amsc.split_headings import is_numbering_only, rejoin_split_headings


@dataclass
class Block:
    text: str
    heading_level: int | None = None
    page: int = 1
    logical_page_side: str = "left"
    physical_bbox: tuple[float, float, float, float] | None = None
    logical_bbox: tuple[float, float, float, float] | None = None


def heading(text, bbox, page=1, side="left", level=2):
    return Block(
        text=text, heading_level=level, page=page, logical_page_side=side,
        physical_bbox=bbox, logical_bbox=bbox,
    )


def body(text, bbox=(0.0, 0.0, 10.0, 10.0)):
    return Block(text=text, physical_bbox=bbox, logical_bbox=bbox)


NUMBER_BOX = (53.0, 189.0, 69.0, 197.0)
TITLE_BOX = (82.0, 188.0, 364.0, 197.0)


def test_numbering_only_recognises_a_bare_section_number():
    assert is_numbering_only("**24.**")
    assert is_numbering_only("24.")
    assert is_numbering_only("2.4.")
    assert is_numbering_only("3)")


def test_numbering_only_rejects_anything_carrying_a_title():
    assert not is_numbering_only("24. YATIRIM GELIRLERI")
    assert not is_numbering_only("YATIRIM GELIRLERI")
    assert not is_numbering_only("")
    assert not is_numbering_only("2024")  # a year is not numbering


def test_the_number_and_its_title_are_rejoined_left_to_right():
    """Column ordering emitted the title first and the number after it."""
    blocks = [
        heading("**YATIRIM FAALIYETLERINDEN GELIRLER**", TITLE_BOX),
        heading("**24.**", NUMBER_BOX),
        body("Devam eden paragraf."),
    ]

    rewritten, merged = rejoin_split_headings(blocks)

    assert len(rewritten) == 2
    assert rewritten[0].text == "**24.** **YATIRIM FAALIYETLERINDEN GELIRLER**"
    assert merged == {"**24.** **YATIRIM FAALIYETLERINDEN GELIRLER**"}
    assert rewritten[0].heading_level == 2
    assert rewritten[1].text == "Devam eden paragraf."


def test_the_merged_heading_covers_both_boxes():
    blocks = [heading("**24.**", NUMBER_BOX), heading("**BASLIK**", TITLE_BOX)]
    rewritten, _ = rejoin_split_headings(blocks)
    assert rewritten[0].physical_bbox == (53.0, 188.0, 364.0, 197.0)
    assert rewritten[0].logical_bbox == (53.0, 188.0, 364.0, 197.0)


def test_two_real_headings_side_by_side_are_never_merged():
    """A grid of service names shares a text line and must stay separate."""
    blocks = [
        heading("**LIMIT KONTROL SISTEMI**", (51.0, 100.0, 280.0, 112.0)),
        heading("**MUSTERI ITIRAZLARI**", (300.0, 100.0, 520.0, 112.0)),
    ]
    rewritten, merged = rejoin_split_headings(blocks)
    assert merged == set()
    assert len(rewritten) == 2


def test_a_number_on_a_different_text_line_is_not_merged():
    blocks = [
        heading("**24.**", (53.0, 189.0, 69.0, 197.0)),
        heading("**BASLIK**", (82.0, 300.0, 364.0, 312.0)),
    ]
    _, merged = rejoin_split_headings(blocks)
    assert merged == set()


def test_a_number_on_another_page_is_not_merged():
    blocks = [
        heading("**24.**", NUMBER_BOX, page=80),
        heading("**BASLIK**", TITLE_BOX, page=81),
    ]
    _, merged = rejoin_split_headings(blocks)
    assert merged == set()


def test_a_number_on_the_other_half_of_a_spread_is_not_merged():
    blocks = [
        heading("**24.**", NUMBER_BOX, side="left"),
        heading("**BASLIK**", TITLE_BOX, side="right"),
    ]
    _, merged = rejoin_split_headings(blocks)
    assert merged == set()


def test_horizontally_overlapping_boxes_are_two_lines_not_one():
    blocks = [
        heading("**24.**", (53.0, 189.0, 200.0, 197.0)),
        heading("**BASLIK**", (82.0, 188.0, 364.0, 197.0)),
    ]
    _, merged = rejoin_split_headings(blocks)
    assert merged == set()


def test_a_paragraph_beside_a_number_is_not_merged():
    blocks = [heading("**24.**", NUMBER_BOX), body("govde", TITLE_BOX)]
    _, merged = rejoin_split_headings(blocks)
    assert merged == set()


def test_two_numbering_fragments_are_not_merged_into_each_other():
    blocks = [heading("**24.**", NUMBER_BOX), heading("**25.**", TITLE_BOX)]
    _, merged = rejoin_split_headings(blocks)
    assert merged == set()


def test_a_stream_without_candidates_is_returned_unchanged():
    blocks = [heading("**BOLUM**", TITLE_BOX), body("govde")]
    rewritten, merged = rejoin_split_headings(blocks)
    assert merged == set()
    assert [b.text for b in rewritten] == [b.text for b in blocks]
