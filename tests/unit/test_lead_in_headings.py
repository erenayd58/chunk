from __future__ import annotations

from dataclasses import dataclass

from amsc.lead_in_headings import demote_lead_ins, is_lead_in
from amsc.models import UnitType


@dataclass
class Block:
    text: str
    unit_type: UnitType = UnitType.PARAGRAPH
    heading_level: int | None = None


def heading(text, level=2):
    return Block(text=text, unit_type=UnitType.HEADING, heading_level=level)


def body(text, unit_type=UnitType.PARAGRAPH):
    return Block(text=text, unit_type=unit_type)


def test_a_heading_left_open_by_a_semicolon_is_a_lead_in():
    assert is_lead_in("Uygulamayla;")
    assert is_lead_in("KKB IBAN Dogrulama Hizmeti ile;")
    assert is_lead_in("Bunlarin yaninda;")


def test_a_trailing_colon_is_a_labelled_sub_heading_not_a_lead_in():
    """Demoting these would merge the financial-note subsections."""
    assert not is_lead_in("**b) Likidite riski:**")
    assert not is_lead_in("**1. Guclu Finansal Yonetim:**")
    assert not is_lead_in("_Mainframe:_")


def test_an_ordinary_title_is_not_a_lead_in():
    assert not is_lead_in("KREDILER ANALIZ PORTALI (KAP)")
    assert not is_lead_in("CEK ANALIZ PORTALI")
    assert not is_lead_in("")


def test_trailing_markdown_emphasis_does_not_hide_the_semicolon():
    assert is_lead_in("_Risk Merkezi Uye ve Urun Yonetimi Ekibi;_")
    assert is_lead_in("**Uygulamayla;**")
    assert is_lead_in("Uygulamayla;  ")


def test_the_lead_in_becomes_body_text_in_its_original_position():
    blocks = [
        heading("KREDILER ANALIZ PORTALI (KAP)"),
        body("Portal aciklamasi."),
        heading("Uygulamayla;"),
        body("- birinci madde", UnitType.LIST),
        body("- ikinci madde", UnitType.LIST),
    ]

    rewritten, demoted = demote_lead_ins(blocks)

    assert demoted == {"Uygulamayla;"}
    assert [b.text for b in rewritten] == [b.text for b in blocks]
    assert rewritten[2].unit_type == UnitType.PARAGRAPH
    assert rewritten[2].heading_level is None
    # The real title is untouched.
    assert rewritten[0].unit_type == UnitType.HEADING
    assert rewritten[0].heading_level == 2


def test_nothing_is_dropped():
    blocks = [heading("Uygulamayla;"), body("govde")]
    rewritten, _ = demote_lead_ins(blocks)
    assert len(rewritten) == len(blocks)


def test_a_paragraph_ending_in_a_semicolon_is_left_alone():
    """Only a heading can be mistaken for a section start."""
    blocks = [body("Su kalemler soyledir;"), body("- madde", UnitType.LIST)]
    rewritten, demoted = demote_lead_ins(blocks)
    assert demoted == set()
    assert rewritten[0].unit_type == UnitType.PARAGRAPH


def test_a_stream_without_lead_ins_is_returned_unchanged():
    blocks = [heading("BOLUM"), body("govde")]
    rewritten, demoted = demote_lead_ins(blocks)
    assert demoted == set()
    assert [(b.text, b.unit_type, b.heading_level) for b in rewritten] == [
        (b.text, b.unit_type, b.heading_level) for b in blocks
    ]


def test_two_lead_ins_are_both_demoted():
    blocks = [
        heading("BOLUM A"),
        heading("Uygulamayla;"),
        heading("BOLUM B"),
        heading("Bunlarin yaninda;"),
    ]
    rewritten, demoted = demote_lead_ins(blocks)
    assert demoted == {"Uygulamayla;", "Bunlarin yaninda;"}
    assert [b.heading_level for b in rewritten] == [2, None, 2, None]
