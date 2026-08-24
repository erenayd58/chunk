from __future__ import annotations

from dataclasses import dataclass

from amsc.models import UnitType
from amsc.sentence_headings import demote_sentence_headings, is_sentence


@dataclass
class Block:
    text: str
    unit_type: UnitType = UnitType.PARAGRAPH
    heading_level: int | None = None


def heading(text, level=2):
    return Block(text=text, unit_type=UnitType.HEADING, heading_level=level)


def body(text, unit_type=UnitType.PARAGRAPH):
    return Block(text=text, unit_type=unit_type)


STANDFIRST = (
    "KKB, Genc Yetenekler Programi ile gelecegin liderlerini yetistirmekte "
    "ve istihdama katki saglamaktadir."
)


def test_a_standfirst_sentence_is_recognised():
    assert is_sentence(STANDFIRST)
    assert is_sentence("**Sirket bu donemde buyumustur.**")


def test_a_title_is_not_a_sentence():
    assert not is_sentence("26. INSAN KAYNAKLARI")
    assert not is_sentence("**9. MADDI DURAN VARLIKLAR**")
    assert not is_sentence("")


def test_an_abbreviation_is_not_a_sentence():
    assert not is_sentence("T. Garanti Bankasi A.S.")
    assert not is_sentence("KKB Kredi Kayit Burosu A.S.")


def test_numbering_is_not_a_sentence():
    """A bare section number is a broken heading, not a sentence."""
    assert not is_sentence("**24.**")
    assert not is_sentence("2.4.")


def test_too_few_words_to_be_a_sentence():
    assert not is_sentence("Devam.")
    assert not is_sentence("Not ekle.")
    assert is_sentence("Bu bir cumledir.")


def test_a_rhetorical_title_keeps_its_heading():
    """Only a full stop demotes; a question mark is a common title style."""
    assert not is_sentence("BIZ KIMIZ?")
    assert not is_sentence("Nasil calisiyoruz!")


def test_the_standfirst_becomes_body_text_under_the_chapter_title():
    blocks = [
        heading("26. INSAN KAYNAKLARI"),
        heading(STANDFIRST),
        body("- ilk madde", UnitType.LIST),
    ]

    rewritten, demoted = demote_sentence_headings(blocks)

    assert demoted == {STANDFIRST}
    assert rewritten[1].unit_type == UnitType.PARAGRAPH
    assert rewritten[1].heading_level is None
    assert rewritten[0].unit_type == UnitType.HEADING
    assert [b.text for b in rewritten] == [b.text for b in blocks]


def test_a_paragraph_ending_in_a_full_stop_is_left_alone():
    blocks = [body("Bu bir govde cumlesidir.")]
    rewritten, demoted = demote_sentence_headings(blocks)
    assert demoted == set()
    assert rewritten[0].unit_type == UnitType.PARAGRAPH


def test_nothing_is_dropped():
    blocks = [heading(STANDFIRST), body("govde")]
    rewritten, _ = demote_sentence_headings(blocks)
    assert len(rewritten) == 2


def test_a_stream_without_candidates_is_returned_unchanged():
    blocks = [heading("BOLUM"), body("govde")]
    rewritten, demoted = demote_sentence_headings(blocks)
    assert demoted == set()
    assert [(b.text, b.unit_type, b.heading_level) for b in rewritten] == [
        (b.text, b.unit_type, b.heading_level) for b in blocks
    ]
