from __future__ import annotations

from dataclasses import dataclass

from amsc.models import UnitType
from amsc.numbered_headings import (
    is_missed_heading,
    numbering_depth,
    promote_numbered_headings,
)


@dataclass
class Block:
    text: str
    unit_type: UnitType = UnitType.PARAGRAPH
    heading_level: int | None = None


def heading(text, level=2):
    return Block(text=text, unit_type=UnitType.HEADING, heading_level=level)


def body(text, unit_type=UnitType.PARAGRAPH):
    return Block(text=text, unit_type=unit_type)


def test_a_fully_bold_single_line_numbered_title_is_a_missed_heading():
    assert is_missed_heading("**7. ILISKILI TARAFLARLA OLAN ISLEMLER**")
    assert is_missed_heading("**9. MADDI DURAN VARLIKLAR**")
    assert is_missed_heading("**2. FINANSAL TABLOLARIN SUNUMU (devami)**")


def test_an_emphasised_sentence_is_not_a_heading():
    assert not is_missed_heading(
        "**2024 yilinda bankalarin ticari musterilerinin belgeleri "
        "dijital ortama tasinmistir**"
    )
    assert not is_missed_heading("**Guvenle Farkli Bir Gelecege**")
    assert not is_missed_heading("**30**")


def test_partial_emphasis_is_not_a_heading():
    """A paragraph that merely opens in bold stays a paragraph."""
    assert not is_missed_heading("**7. ILISKILI TARAFLAR** hakkinda aciklama.")
    assert not is_missed_heading("7. ILISKILI TARAFLAR")


def test_a_multi_line_block_is_not_a_heading():
    assert not is_missed_heading("**7. ILISKILI TARAFLAR**\n\nAciklama metni.")


def test_a_numbered_list_item_is_not_a_heading():
    assert not is_missed_heading("- **7. ILISKILI TARAFLAR**")


def test_a_numbered_line_ending_as_a_sentence_is_not_a_heading():
    assert not is_missed_heading("**1. Sirket bu donemde buyumustur.**")


def test_depth_follows_the_section_numbering():
    assert numbering_depth("**7. ILISKILI TARAFLAR**") == 1
    assert numbering_depth("**2.4. Onemli muhasebe politikalari**") == 2
    assert numbering_depth("**2.4.1. Alt baslik**") == 3
    assert numbering_depth("Sade metin") is None


def test_numbering_must_close_with_its_own_terminator():
    """Without it, any bold line opening with a year would be promoted."""
    assert numbering_depth("**2024 Findeks Verileri**") is None
    assert numbering_depth("**2.4 Onemli muhasebe politikalari**") is None


def test_the_promoted_heading_becomes_a_sibling_of_the_existing_ones():
    blocks = [
        heading("**8. STOKLAR**", level=2),
        body("Stok aciklamasi."),
        body("**9. MADDI DURAN VARLIKLAR**"),
        body("Varlik aciklamasi."),
    ]

    rewritten, promoted = promote_numbered_headings(blocks)

    assert promoted == {"**9. MADDI DURAN VARLIKLAR**"}
    assert rewritten[2].unit_type == UnitType.HEADING
    assert rewritten[2].heading_level == 2
    assert [b.text for b in rewritten] == [b.text for b in blocks]


def test_a_deeper_number_nests_one_level_down():
    blocks = [
        heading("**2. ESASLAR**", level=2),
        body("**2.4. Onemli muhasebe politikalari**"),
    ]
    rewritten, _ = promote_numbered_headings(blocks)
    assert rewritten[1].heading_level == 3


def test_the_base_level_is_the_shallowest_heading_in_the_stream():
    blocks = [
        heading("BOLUM", level=1),
        heading("ALT BOLUM", level=3),
        body("**7. ILISKILI TARAFLAR**"),
    ]
    rewritten, _ = promote_numbered_headings(blocks)
    assert rewritten[2].heading_level == 1


def test_without_any_heading_the_promoted_block_opens_the_hierarchy():
    rewritten, _ = promote_numbered_headings([body("**7. ILISKILI TARAFLAR**")])
    assert rewritten[0].heading_level == 1


def test_an_existing_heading_is_never_touched():
    blocks = [heading("**7. ILISKILI TARAFLAR**", level=2)]
    rewritten, promoted = promote_numbered_headings(blocks)
    assert promoted == set()
    assert rewritten[0].heading_level == 2


def test_nothing_is_dropped_or_reordered():
    blocks = [body("a"), body("**1. BASLIK**"), body("b"), body("c")]
    rewritten, _ = promote_numbered_headings(blocks)
    assert [b.text for b in rewritten] == ["a", "**1. BASLIK**", "b", "c"]


def test_a_stream_without_candidates_is_returned_unchanged():
    blocks = [heading("BOLUM"), body("govde metni")]
    rewritten, promoted = promote_numbered_headings(blocks)
    assert promoted == set()
    assert [(b.text, b.unit_type, b.heading_level) for b in rewritten] == [
        (b.text, b.unit_type, b.heading_level) for b in blocks
    ]
