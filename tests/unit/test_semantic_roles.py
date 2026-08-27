from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from amsc.models import ROLE_OPENS_SECTION, SemanticRole
from amsc.semantic_roles import assign_semantic_roles, is_numbered
from amsc.models import UnitType

SECTION = SemanticRole.SECTION
GROUP = SemanticRole.GROUP
ITEM = SemanticRole.ITEM
DISPLAY = SemanticRole.DISPLAY


@dataclass(frozen=True)
class Block:
    text: str
    unit_type: UnitType = UnitType.PARAGRAPH
    heading_level: int | None = None
    font_size: float | None = None
    page: int = 1
    logical_page_side: str = "single"
    semantic_role: SemanticRole | None = None
    opens_section: bool | None = None
    role_reason: str | None = None


def heading(text, size, page=1):
    return Block(text, UnitType.HEADING, heading_level=2, font_size=size, page=page)


def body(text="govde metni", size=9.0, page=1):
    return Block(text, UnitType.PARAGRAPH, font_size=size, page=page)


def roles(blocks):
    rewritten, _ = assign_semantic_roles(blocks)
    return [b.semantic_role for b in rewritten if b.unit_type == UnitType.HEADING]


def opens(blocks):
    rewritten, _ = assign_semantic_roles(blocks)
    return [b.opens_section for b in rewritten if b.unit_type == UnitType.HEADING]


# ------------------------------------------------------------ the invariant


def test_opens_section_is_exactly_what_the_role_implies():
    blocks = [
        heading("1. BOLUM", 20.0), body(),
        heading("2014", 9.0), body(),
        heading("Bir odul", 9.0), body(),
        heading("Baska odul", 9.0), body(),
        heading("Ucuncu odul", 9.0), body(),
    ]

    rewritten, _ = assign_semantic_roles(blocks)

    for block in rewritten:
        if block.unit_type != UnitType.HEADING:
            continue
        assert block.opens_section == ROLE_OPENS_SECTION[block.semantic_role]


def test_a_heading_that_does_not_open_a_section_is_still_a_heading():
    blocks = [heading("1. BOLUM", 20.0), body()] + [
        b for i in range(3) for b in (heading("Kart %d" % i, 9.0), body())
    ]

    rewritten, _ = assign_semantic_roles(blocks)

    assert [b.unit_type for b in rewritten] == [b.unit_type for b in blocks]
    assert [b.text for b in rewritten] == [b.text for b in blocks]


# ------------------------------------------------------------ safe defaults


def test_a_corpus_with_no_measured_type_is_returned_untouched():
    blocks = [Block("Baslik", UnitType.HEADING, heading_level=2), body(size=None)]

    assert assign_semantic_roles(blocks) == (blocks, {})


def test_a_stream_with_no_headings_is_returned_untouched():
    blocks = [body("bir"), body("iki")]

    assert assign_semantic_roles(blocks) == (blocks, {})


def test_two_labels_are_a_coincidence_and_stay_sections():
    blocks = [
        heading("1. BOLUM", 20.0), body(),
        heading("Bir kart", 9.0), body(),
        heading("Iki kart", 9.0), body(),
    ]

    assert roles(blocks) == [SECTION, SECTION, SECTION]


# ------------------------------------------------------------------- item


def test_three_body_sized_labels_in_one_scope_are_a_list_of_items():
    blocks = [heading("1. BOLUM", 20.0), body()] + [
        b for name in ("Bir", "Iki", "Uc") for b in (heading(name, 9.0), body())
    ]

    assert roles(blocks) == [SECTION, ITEM, ITEM, ITEM]


def test_a_label_set_larger_than_the_body_is_not_an_item():
    blocks = [heading("1. BOLUM", 20.0), body()] + [
        b for name in ("Bir", "Iki", "Uc") for b in (heading(name, 12.0), body())
    ]

    assert roles(blocks) == [SECTION] * 4


def test_a_numbered_label_is_never_demoted_to_an_item():
    """The document's own numbering outranks every layout signal."""
    blocks = [heading("2. ESASLAR", 10.0), body(size=10.0)] + [
        b
        for name in ("2.1 Ilki", "2.2 Ikincisi", "2.3 Ucuncusu", "2.4 Dorduncusu")
        for b in (heading(name, 10.0), body(size=10.0))
    ]

    assert roles(blocks) == [SECTION] * 5
    assert all(opens(blocks))


def test_items_in_two_different_scopes_are_counted_separately():
    blocks = (
        [heading("1. BIR", 20.0), body()]
        + [b for n in ("a", "b") for b in (heading(n, 9.0), body())]
        + [heading("2. IKI", 20.0), body()]
        + [b for n in ("c", "d") for b in (heading(n, 9.0), body())]
    )

    # Two per scope is below the run threshold in both, so nothing is demoted.
    assert roles(blocks) == [SECTION] * 6


# ------------------------------------------------------------------ group


def test_a_bare_year_inside_a_section_is_a_grouping_key():
    blocks = [heading("5. ODULLER", 20.0), body(), heading("2018", 9.0), body()]

    assert roles(blocks) == [SECTION, GROUP]
    assert opens(blocks) == [True, True]


def test_a_bare_number_with_nothing_above_it_is_a_numeral_not_a_key():
    blocks = [heading("10", 250.0), body()]

    assert roles(blocks) == [DISPLAY]
    assert opens(blocks) == [False]


@pytest.mark.parametrize("text", ["2014", "10", "1.300", "2.4"])
def test_number_shapes_that_count_as_a_key(text):
    blocks = [heading("1. BOLUM", 20.0), body(), heading(text, 9.0), body()]

    assert roles(blocks)[1] == GROUP


def test_a_percentage_is_a_value_not_a_key():
    blocks = [heading("1. BOLUM", 20.0), body(), heading("%18,18", 9.0), body()]

    assert roles(blocks)[1] is not GROUP


# ---------------------------------------------------------------- display


def test_a_standfirst_set_under_its_own_chapter_title_is_display():
    blocks = [
        heading("2. ORTAKLIK YAPISI", 20.0),
        heading("Turkiye'nin onde gelen bankalarindan gelen guc", 40.0),
        body(),
    ]

    assert roles(blocks) == [SECTION, DISPLAY]
    assert opens(blocks) == [True, False]


def test_a_repeated_size_that_labels_content_is_a_subheading_tier_not_display():
    """Vizyon / Misyon / Temel Stratejiler are set large and are real headings."""
    blocks = [
        heading("3. VIZYON, MISYON VE STRATEJILER", 20.0),
        heading("Vizyon", 40.0), body(),
        heading("Misyon", 40.0), body(),
        heading("Temel Stratejiler", 40.0), body(),
    ]

    assert roles(blocks) == [SECTION, SECTION, SECTION, SECTION]


def test_a_size_tier_that_labels_nothing_on_the_page_is_decorative():
    blocks = [
        heading("5. ODULLER", 20.0),
        heading("Gururla ve heyecanla", 40.0),
        heading("2018", 9.0), body(),
        heading("Odullerle", 40.0),
        heading("2019", 9.0), body(),
    ]

    assert roles(blocks) == [SECTION, DISPLAY, GROUP, DISPLAY, GROUP]


def test_display_type_on_a_different_page_from_the_heading_above_it_is_left_alone():
    blocks = [
        heading("1. BOLUM", 20.0, page=8), body(page=8),
        heading("FINANSAL BILGILER", 68.0, page=56), body(page=56),
    ]

    assert roles(blocks) == [SECTION, SECTION]


def test_a_banner_leading_several_pages_is_furniture():
    blocks = []
    for page in (61, 62, 63, 64):
        blocks += [heading("KKB KREDI KAYIT BUROSU A.S.", 20.0, page=page),
                   body(page=page)]

    assert roles(blocks) == [DISPLAY] * 4
    assert opens(blocks) == [False] * 4


def test_a_numbered_chapter_repeated_as_a_banner_keeps_its_section():
    """Deleting it was what lost two real chapter titles; demoting it must not."""
    blocks = []
    for page in (27, 28, 29, 30):
        blocks += [heading("15. URUN VE HIZMETLER", 20.0, page=page), body(page=page)]

    assert roles(blocks) == [SECTION] * 4
    assert all(opens(blocks))


# ------------------------------------------------------------------ census


def test_the_census_counts_every_heading_by_the_role_it_was_given():
    blocks = [heading("1. BOLUM", 20.0), body()] + [
        b for n in ("a", "b", "c") for b in (heading(n, 9.0), body())
    ]

    _, census = assign_semantic_roles(blocks)

    assert census == {"section": 1, "item": 3}


def test_every_heading_carries_the_reason_it_was_classified():
    blocks = [heading("1. BOLUM", 20.0), body(), heading("2014", 9.0), body()]

    rewritten, _ = assign_semantic_roles(blocks)

    reasons = [b.role_reason for b in rewritten if b.unit_type == UnitType.HEADING]
    assert all(reasons)
    assert "bare number" in reasons[1]


def test_rewriting_is_a_copy_not_a_mutation():
    blocks = [heading("1. BOLUM", 20.0), body()]
    before = [replace(b) for b in blocks]

    assign_semantic_roles(blocks)

    assert blocks == before


@pytest.mark.parametrize(
    "text,expected",
    [
        ("7. ILISKILI TARAFLAR", True),
        ("**2.4 Onemli politikalar**", True),
        ("2024 Findeks Verileri", False),
        ("31 Aralik 2024", False),
        ("Disiplin Komitesi", False),
    ],
)
def test_what_counts_as_the_document_numbering_itself(text, expected):
    assert is_numbered(text) is expected
