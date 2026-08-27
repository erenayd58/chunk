from __future__ import annotations

from dataclasses import dataclass

from amsc.split_headings import (
    continues_mid_word,
    ends_mid_word,
    is_numbering_only,
    rejoin_hyphenated_headings,
    rejoin_split_headings,
)


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


# --- the hyphenated wrap ---------------------------------------------------
#
# A heading too long for its column breaks mid-word and each printed line
# arrives as its own heading box. These boxes are *stacked*, which is exactly
# what the side-by-side pass above refuses to touch.

WRAP_TOP = (306.0, 597.0, 539.0, 605.0)
WRAP_BOTTOM = (306.0, 608.0, 332.0, 616.0)


def test_ends_mid_word_needs_a_letter_before_the_hyphen():
    assert ends_mid_word("Devam Eden Da-")
    assert ends_mid_word("**Devam Eden Da-**")
    assert not ends_mid_word("-")             # a bullet, not a broken word
    assert not ends_mid_word("2019-")         # an open range
    assert not ends_mid_word("Devam Eden")


def test_continues_mid_word_needs_a_lowercase_start():
    assert continues_mid_word("valar")
    assert continues_mid_word("**valar**")
    assert not continues_mid_word("Valar")    # a new heading
    assert not continues_mid_word("12. UST YONETIM")
    assert not continues_mid_word("")


def test_a_wrapped_heading_is_rejoined_without_its_hyphen():
    blocks = [
        heading("Birim Nezdinde Takibi Yurutulen Devam Eden Da-", WRAP_TOP),
        heading("valar", WRAP_BOTTOM),
        body("31.12.2024 tarihi itibariyla..."),
    ]

    rewritten, merged = rejoin_hyphenated_headings(blocks)

    assert len(rewritten) == 2
    assert rewritten[0].text == "Birim Nezdinde Takibi Yurutulen Devam Eden Davalar"
    assert merged == {"Birim Nezdinde Takibi Yurutulen Devam Eden Davalar"}
    assert rewritten[0].heading_level == 2
    # The surviving box spans both printed lines.
    assert rewritten[0].physical_bbox == (306.0, 597.0, 539.0, 616.0)


def test_emphasis_ends_up_around_the_joined_title_not_inside_it():
    blocks = [
        heading("**Devam Eden Da-**", WRAP_TOP),
        heading("**valar**", WRAP_BOTTOM),
    ]

    rewritten, _ = rejoin_hyphenated_headings(blocks)

    assert rewritten[0].text == "**Devam Eden Davalar**"


def test_a_heading_wrapped_twice_comes_out_as_one_heading():
    blocks = [
        heading("Devam Eden Da-", (306.0, 597.0, 539.0, 605.0)),
        heading("va-", (306.0, 606.0, 332.0, 614.0)),
        heading("lar", (306.0, 615.0, 332.0, 623.0)),
    ]

    rewritten, _ = rejoin_hyphenated_headings(blocks)

    assert len(rewritten) == 1
    assert rewritten[0].text == "Devam Eden Davalar"


def test_a_capitalised_line_below_is_a_new_heading_not_a_continuation():
    blocks = [
        heading("Kredi Limit-", WRAP_TOP),
        heading("Risk Bildirimi", WRAP_BOTTOM),
    ]

    _, merged = rejoin_hyphenated_headings(blocks)

    assert merged == set()


def test_a_subtitle_set_below_a_heading_is_left_alone():
    """No hyphen, so nothing claims the two lines are one word."""
    blocks = [
        heading("Kurumsal", WRAP_TOP),
        heading("Yonetisim", WRAP_BOTTOM),
    ]

    _, merged = rejoin_hyphenated_headings(blocks)

    assert merged == set()


def test_a_paragraph_below_a_hyphenated_heading_is_not_pulled_in():
    blocks = [
        heading("Devam Eden Da-", WRAP_TOP),
        body("valarin listesi asagidadir.", WRAP_BOTTOM),
    ]

    _, merged = rejoin_hyphenated_headings(blocks)

    assert merged == set()


def test_a_line_further_down_the_column_is_too_far_to_be_a_continuation():
    """The next paragraph clears a heading by a leading of its own."""
    blocks = [
        heading("Devam Eden Da-", (306.0, 597.0, 539.0, 605.0)),
        heading("valar", (306.0, 660.0, 332.0, 668.0)),
    ]

    _, merged = rejoin_hyphenated_headings(blocks)

    assert merged == set()


def test_a_fragment_beside_the_heading_is_not_a_continuation():
    """Horizontally disjoint means side by side -- the other pass's case."""
    blocks = [
        heading("Devam Eden Da-", (51.0, 597.0, 200.0, 605.0)),
        heading("valar", (306.0, 606.0, 332.0, 614.0)),
    ]

    _, merged = rejoin_hyphenated_headings(blocks)

    assert merged == set()


def test_the_two_passes_do_not_see_each_others_pairs():
    """A stacked wrap and a side-by-side number never cross-match."""
    wrap = [
        heading("Devam Eden Da-", WRAP_TOP),
        heading("valar", WRAP_BOTTOM),
    ]
    numbered = [
        heading("**YATIRIM FAALIYETLERINDEN GELIRLER**", TITLE_BOX),
        heading("**24.**", NUMBER_BOX),
    ]

    assert rejoin_split_headings(wrap)[1] == set()
    assert rejoin_hyphenated_headings(numbered)[1] == set()
