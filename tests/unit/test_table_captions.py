from __future__ import annotations

from dataclasses import dataclass

from amsc.models import UnitType
from amsc.table_captions import caption_cells, demote_table_captions


@dataclass
class Block:
    text: str
    unit_type: UnitType = UnitType.PARAGRAPH
    heading_level: int | None = None


def heading(text, level=2):
    return Block(text=text, unit_type=UnitType.HEADING, heading_level=level)


def body(text):
    return Block(text=text)


def table(text):
    return Block(text=text, unit_type=UnitType.TABLE)


PERIOD_TABLE = (
    "|**31 Aralik 2024**|||\n"
    "|---|---|---|\n"
    "|Vadeler|Defter degeri|Nakit cikislari|\n"
    "|Ticari borclar|308.201|103.492|\n"
    "|**31 Aralik 2023**|||\n"
    "|Vadeler|Defter degeri|Nakit cikislari|"
)


def test_a_row_with_one_filled_cell_is_a_caption_cell():
    assert caption_cells(PERIOD_TABLE) == {"31 aralik 2024", "31 aralik 2023"}


def test_a_data_row_is_not_a_caption_cell():
    assert "vadeler" not in caption_cells(PERIOD_TABLE)


def test_the_divider_row_is_not_a_caption_cell():
    assert caption_cells("|A|\n|---|\n|deger|") == {"a", "deger"}


def test_a_caption_before_its_table_is_demoted():
    blocks = [
        heading("**b) Likidite riski:**"),
        heading("**31 Aralik 2024**"),
        table(PERIOD_TABLE),
    ]
    rewritten, demoted = demote_table_captions(blocks)
    assert demoted == {"**31 Aralik 2024**"}
    assert rewritten[1].unit_type == UnitType.PARAGRAPH
    assert rewritten[1].heading_level is None
    assert rewritten[0].unit_type == UnitType.HEADING


def test_a_caption_after_its_table_is_demoted():
    """The layout model emits the second period label below the table box."""
    blocks = [table(PERIOD_TABLE), heading("**31 Aralik 2023**")]
    rewritten, demoted = demote_table_captions(blocks)
    assert demoted == {"**31 Aralik 2023**"}
    assert rewritten[1].heading_level is None


def test_emphasis_differences_do_not_hide_the_duplication():
    blocks = [heading("31 Aralik 2024"), table(PERIOD_TABLE)]
    _, demoted = demote_table_captions(blocks)
    assert demoted == {"31 Aralik 2024"}


def test_a_heading_not_repeated_in_the_table_is_kept():
    blocks = [heading("**9. MADDI DURAN VARLIKLAR**"), table(PERIOD_TABLE)]
    rewritten, demoted = demote_table_captions(blocks)
    assert demoted == set()
    assert rewritten[0].unit_type == UnitType.HEADING


def test_a_heading_next_to_a_paragraph_is_never_a_caption():
    blocks = [heading("**31 Aralik 2024**"), body("|**31 Aralik 2024**|||")]
    _, demoted = demote_table_captions(blocks)
    assert demoted == set()


def test_a_non_adjacent_table_does_not_demote_the_heading():
    blocks = [
        heading("**31 Aralik 2024**"),
        body("Araya giren paragraf."),
        table(PERIOD_TABLE),
    ]
    _, demoted = demote_table_captions(blocks)
    assert demoted == set()


def test_nothing_is_dropped_or_reordered():
    blocks = [heading("**31 Aralik 2024**"), table(PERIOD_TABLE), body("son")]
    rewritten, _ = demote_table_captions(blocks)
    assert [b.text for b in rewritten] == [b.text for b in blocks]


def test_a_stream_without_tables_is_returned_unchanged():
    blocks = [heading("BOLUM"), body("govde")]
    rewritten, demoted = demote_table_captions(blocks)
    assert demoted == set()
    assert [(b.text, b.unit_type, b.heading_level) for b in rewritten] == [
        (b.text, b.unit_type, b.heading_level) for b in blocks
    ]
