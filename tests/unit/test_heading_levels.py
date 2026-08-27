from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from amsc.heading_levels import (
    MAX_HEADING_LEVEL,
    SIZE_RESOLUTION,
    assign_heading_levels,
)
from amsc.models import SemanticRole, UnitType


@dataclass(frozen=True)
class Block:
    text: str
    unit_type: UnitType = UnitType.PARAGRAPH
    heading_level: int | None = None
    font_size: float | None = None
    opens_section: bool | None = None
    semantic_role: SemanticRole | None = None


def heading(text, size=None, level=2, role=None):
    return Block(
        text=text,
        unit_type=UnitType.HEADING,
        heading_level=level,
        font_size=size,
        semantic_role=role,
    )


def key(text, size):
    """A heading the role pass called a key: a bare number partitioning a section."""
    return heading(text, size, role=SemanticRole.GROUP)


def body(text="body"):
    return Block(text=text)


def levels(blocks):
    rewritten, _ = assign_heading_levels(blocks)
    return [b.heading_level for b in rewritten if b.heading_level is not None]


# ------------------------------------------------------------- safe defaults


def test_a_document_with_one_type_size_comes_out_exactly_as_it_went_in():
    """The whole point of anchoring on the document's own shallowest level."""
    blocks = [heading("A", 9.0), body(), heading("B", 9.0), body()]

    rewritten, census = assign_heading_levels(blocks)

    assert rewritten == blocks
    assert census == {2: 2}


def test_a_stream_with_no_measurable_type_is_left_alone():
    blocks = [heading("A"), body(), heading("B"), body()]

    assert assign_heading_levels(blocks)[0] == blocks


def test_a_stream_with_no_headings_at_all_is_returned_untouched():
    blocks = [body("one"), body("two")]

    assert assign_heading_levels(blocks) == (blocks, {})


def test_levels_are_relative_to_the_shallowest_level_already_present():
    blocks = [heading("Chapter", 20.0, level=1), heading("Sub", 9.0, level=1)]

    assert levels(blocks) == [1, 2]


# ---------------------------------------------------------------- nesting


def test_a_smaller_heading_nests_under_the_larger_one_before_it():
    blocks = [
        heading("8. KILOMETRE TASLARI", 20.0),
        heading("2012", 9.0),
        body(),
    ]

    assert levels(blocks) == [2, 3]


def test_a_larger_heading_closes_every_smaller_one_open_above_it():
    blocks = [
        heading("Chapter one", 20.0),
        heading("Label", 9.0),
        heading("Chapter two", 20.0),
        heading("Label", 9.0),
    ]

    assert levels(blocks) == [2, 3, 2, 3]


def test_three_descending_sizes_produce_three_tiers():
    blocks = [heading("A", 40.0), heading("B", 20.0), heading("C", 9.0)]

    assert levels(blocks) == [2, 3, 4]


def test_equal_sizes_are_siblings_not_a_deepening_chain():
    blocks = [heading("A", 9.0), heading("B", 9.0), heading("C", 9.0)]

    assert levels(blocks) == [2, 2, 2]


def test_sizes_within_one_resolution_step_are_the_same_tier():
    blocks = [heading("A", 9.0), heading("B", 9.0 - SIZE_RESOLUTION / 4)]

    assert levels(blocks) == [2, 2]


def test_an_intermediate_size_reopens_only_the_tiers_it_encloses():
    blocks = [
        heading("part", 40.0),
        heading("chapter", 20.0),
        heading("label", 9.0),
        heading("chapter two", 20.0),
    ]

    assert levels(blocks) == [2, 3, 4, 3]


# ------------------------------------------------------- numbering tie-break


def test_section_numbering_nests_inside_its_own_size_tier():
    blocks = [
        heading("**2. FINANSAL TABLOLAR**", 10.0),
        heading("**2.4 Onemli politikalar**", 10.0),
        body(),
    ]

    assert levels(blocks) == [2, 3]


def test_an_unnumbered_title_sits_under_the_numbered_one_beside_it():
    blocks = [
        heading("**2. FINANSAL TABLOLAR**", 10.0),
        heading("**2.4 Onemli politikalar**", 10.0),
        heading("**Kidem tazminati**", 10.0),
    ]

    assert levels(blocks) == [2, 3, 4]


def test_a_multi_part_number_needs_no_trailing_terminator():
    """``2.4 Onemli politikalar`` is printed without one in the corpus."""
    blocks = [
        heading("**2. FINANSAL TABLOLAR**", 10.0),
        heading("**2.4 Onemli politikalar**", 10.0),
        heading("**2.4. Ayni sey noktali**", 10.0),
    ]

    assert levels(blocks) == [2, 3, 3]


@pytest.mark.parametrize(
    "text",
    [
        "2024 Findeks Verileri",  # a bare year: no terminator, one part
        "1.300 potansiyel sorun tespit edildi",  # a thousands separator
        "31 Aralik 2024",
    ],
)
def test_text_that_only_looks_numbered_is_not_read_as_section_numbering(text):
    blocks = [heading(text, 9.0), heading("Baska baslik", 9.0)]

    assert levels(blocks) == [2, 2]


def test_emphasis_markers_do_not_hide_the_numbering():
    plain = [heading("2. Bolum", 10.0), heading("2.4 Alt", 10.0)]
    bold = [heading("**2. Bolum**", 10.0), heading("**2.4 Alt**", 10.0)]

    assert levels(plain) == levels(bold) == [2, 3]


# ------------------------------------------------------------ missing sizes


def test_an_unmeasurable_heading_becomes_a_sibling_of_the_one_before_it():
    blocks = [
        heading("Chapter", 20.0),
        heading("Label", 9.0),
        heading("Unmeasurable", None),
    ]

    assert levels(blocks) == [2, 3, 3]


def test_an_unmeasurable_first_heading_is_the_outermost_one():
    blocks = [heading("Unmeasurable", None), heading("Chapter", 20.0)]

    assert levels(blocks) == [2, 2]


# ------------------------------------------------------------------ census


def test_the_census_counts_every_heading_by_the_level_it_was_given():
    blocks = [
        heading("A", 40.0),
        heading("B", 20.0),
        heading("C", 20.0),
        heading("D", 9.0),
    ]

    _, census = assign_heading_levels(blocks)

    assert census == {2: 1, 3: 2, 4: 1}


def test_body_blocks_keep_their_identity_and_their_place():
    blocks = [heading("A", 20.0), body("first"), heading("B", 9.0), body("second")]

    rewritten, _ = assign_heading_levels(blocks)

    assert [b.text for b in rewritten] == ["A", "first", "B", "second"]
    assert rewritten[1] is blocks[1] and rewritten[3] is blocks[3]


def test_a_block_type_without_a_font_size_attribute_still_works():
    @dataclass(frozen=True)
    class Bare:
        text: str
        heading_level: int | None = None

    blocks = [Bare("A", 2), Bare("body"), Bare("B", 2)]

    assert assign_heading_levels(blocks)[0] == blocks


@pytest.mark.parametrize("size", [0.0, -1.0])
def test_a_degenerate_size_is_still_ordered_rather_than_crashing(size):
    blocks = [heading("A", 20.0), heading("B", size)]

    assert levels(blocks) == [2, 3]


def test_more_tiers_than_markdown_has_merge_into_the_deepest_level():
    """The schema stops at six; the tail of the tree is what gives way."""
    sizes = [68.0, 52.0, 40.0, 24.0, 20.0, 15.0, 12.0, 10.0, 9.0]
    blocks = [heading("h%d" % i, size) for i, size in enumerate(sizes)]

    # Nine tiers into five levels: the five nearest the root each keep one, and
    # everything below the cap shares it.
    assert levels(blocks) == [2, 3, 4, 5, 6, 6, 6, 6, 6]
    assert max(levels(blocks)) <= MAX_HEADING_LEVEL


def test_a_chapter_stays_above_the_labels_inside_it():
    """What makes merging the tail safe: display type cannot out-rank a chapter."""
    blocks = [
        heading("part", 68.0),
        heading("division", 52.0),
        heading("standfirst", 40.0),
        heading("**12. UST YONETIM**", 20.0),
        heading("**Bir komite**", 9.0),
        body(),
    ]

    chapter, label = levels(blocks)[-2:]
    assert chapter < label


def test_display_type_may_not_out_rank_the_chapter_it_sits_under():
    """A standfirst set larger than its own chapter title is typography, not structure."""
    blocks = [
        heading("**2. ORTAKLIK YAPISI**", 20.0),
        heading("Turkiye'nin onde gelen bankalarindan gelen guc", 40.0),
        body(),
    ]

    chapter, standfirst = levels(blocks)
    assert chapter < standfirst


def test_a_heading_that_does_not_bear_hierarchy_never_moves_the_others():
    from dataclasses import replace as _replace

    bearing = [heading("**1. BOLUM**", 20.0), heading("**1.1 Alt**", 20.0)]
    with_label = [
        bearing[0],
        _replace(heading("Bir kart", 40.0), opens_section=False),
        bearing[1],
    ]

    assert levels(bearing) == [2, 3]
    assert levels(with_label) == [2, 3, 3]


def test_the_deep_end_keeps_one_level_per_tier_when_everything_fits():
    blocks = [heading("a", 40.0), heading("b", 20.0), heading("c", 9.0)]

    assert levels(blocks) == [2, 3, 4]


def test_rewriting_is_a_copy_not_a_mutation():
    blocks = [heading("A", 20.0), heading("B", 9.0)]
    before = [replace(b) for b in blocks]

    assign_heading_levels(blocks)

    assert blocks == before


def test_two_chapters_at_the_same_numbering_depth_are_siblings_whatever_their_size():
    """``29.`` arrives merged with its standfirst at 40pt; ``30.`` is set at 20pt."""
    blocks = [
        heading("**29. IC KONTROL** Guvenilir surecler icin", 40.0),
        body(),
        heading("**30. YASAL UYUM**", 20.0),
        body(),
        heading("**31. KOMITELER**", 20.0),
        body(),
    ]

    assert levels(blocks) == [2, 2, 2]


def test_a_deeper_number_still_nests_under_a_shallower_one():
    blocks = [heading("**2. ESASLAR**", 20.0), heading("**2.4 Alt**", 10.0), body()]

    assert levels(blocks) == [2, 3]


# ------------------------------------------------------------------- keys


def test_two_keys_of_one_partition_are_siblings_however_they_are_printed():
    """Page 15's timeline: the year labels are set at four different sizes."""
    blocks = [
        heading("**8. KILOMETRE TASLARI**", 20.0),
        key("1995", 14.0),
        body(),
        key("2009", 11.0),
        body(),
        key("2016", 12.5),
        body(),
        key("2022", 9.0),
        body(),
    ]

    assert levels(blocks) == [2, 3, 3, 3, 3]


def test_without_the_role_decision_the_same_labels_still_nest():
    """The rule reads a decision the role pass made; it invents none of its own."""
    blocks = [
        heading("**8. KILOMETRE TASLARI**", 20.0),
        heading("1995", 14.0),
        heading("2009", 11.0),
        heading("2016", 12.5),
    ]

    assert levels(blocks) == [2, 3, 4, 4]


def test_a_key_printed_deeper_than_the_run_keeps_its_own_tier():
    """``2.4`` under ``2`` is the document stating the nesting, not the layout."""
    blocks = [
        heading("**2. ESASLAR**", 20.0),
        key("2", 12.0),
        key("2.4", 10.0),
        key("2.5", 9.0),
    ]

    assert levels(blocks) == [2, 3, 4, 4]


def test_a_thousands_separator_does_not_make_a_key_look_nested():
    blocks = [
        heading("**8. BOLUM**", 20.0),
        key("2014", 12.0),
        key("1.300", 10.0),
    ]

    assert levels(blocks) == [2, 3, 3]


def test_a_heading_that_is_not_a_key_closes_the_run():
    together = [
        heading("**8. BOLUM**", 20.0),
        key("1995", 12.0),
        key("2009", 9.0),
    ]
    interrupted = [
        together[0],
        together[1],
        heading("Bir alt baslik", 10.0),
        together[2],
    ]

    assert levels(together) == [2, 3, 3]
    assert levels(interrupted) == [2, 3, 4, 5]


def test_a_key_never_lifts_a_later_section_to_its_own_tier():
    """The run only ever rewrites a key's own prominence."""
    blocks = [
        heading("**8. BOLUM**", 20.0),
        key("1995", 12.0),
        key("2009", 9.0),
        heading("**9. BOLUM**", 20.0),
        body(),
    ]

    assert levels(blocks) == [2, 3, 3, 2]
