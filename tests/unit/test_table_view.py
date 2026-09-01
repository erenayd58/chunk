"""The readable rendering of a chunk's table.

A table reaches the answer context as the markdown a layout model produced. On
a report's financial note that markdown can carry no single line on which a row
label, its value and its period appear together -- and the one line that *does*
pair a label with a value pairs it with the wrong period's. The contract here
is that a second representation is derived for reading, that it is derived only
where the table's own structure makes every pairing certain, and that the raw
markdown is never rewritten.
"""

from __future__ import annotations

import pytest

from amsc.deep_pipeline import MODE_DEEP, MODE_STANDARD, DeepAnalysisSettings, chunk_document
from amsc.models import RawDocumentUnit
from amsc.table_view import enrich_rows, table_view_for, view_lines


# The shape this exists for. Column 3 has its whole run of values written
# inside its own header cell; column 2 has its values spread over data rows,
# the first of which carries no label at all; and the row labels are stacked
# inside the label column's header. The only label-and-value pair sharing a
# line is "Satisiadeleri(-)" beside the *2023* deduction.
FINANCIAL_NOTE = "\n".join([
    "|**Satislar ve satislarin maliyeti**<br>Satis gelirleri<br>Satisiadeleri(-)"
    "|**1 Ocak-**<br>**31 Aralik 2024**"
    "|**1 Ocak-**<br>**31 Aralik 2023**<br>1.772.898.429<br>(6.682.818)<br>**1.766.215.611**|",
    "|---|---|---|",
    "||3.560.086.540<br>(16.923.281)||",
    "|**Toplam**|**3.543.163.259**||",
])

ORDINARY_TABLE = "\n".join([
    "|**Personelin ogrenim durumu**|**Personelin ogrenim durumu**|**Personelin ogrenim durumu**|",
    "|---|---|---|",
    "|**Ogrenim**||**Toplam icinde**|",
    "|**durumu**|**Kisi**|**Oran (%)**|",
    "|Lisans|212|77|",
    "|Yuksek lisans<br>ve doktora|41|15|",
    "|**Kadin**|||",
    "|Kadin personel|118|43|",
])


def _unit(order, unit_id, unit_type, text, *, level=None, path=(), document_id="probe-doc"):
    row = {
        "document_id": document_id, "unit_id": unit_id, "order": order, "text": text,
        "type": unit_type, "section_path": list(path), "source": {"page": 1, "block": order},
    }
    if level is not None:
        row.update(heading_level=level, semantic_role="section", opens_section=True)
    return RawDocumentUnit.model_validate(row)


def _units_with(table_text):
    path = ["18. SATISLAR VE SATISLARIN MALIYETI"]
    units = [_unit(1, "h-0001", "heading", "18. SATISLAR VE SATISLARIN MALIYETI",
                   level=1, path=path)]
    for order in range(2, 8):
        units.append(_unit(order, f"p-{order:04d}", "paragraph",
                           ("Satislar ve satislarin maliyeti detaylari asagidaki gibidir. " * 10).strip(),
                           path=path))
    units.append(_unit(8, "t-0008", "table", table_text, path=path))
    return units


# --- what the reading keeps -------------------------------------------------


def test_each_period_keeps_its_own_values():
    """The whole point: a value is written under the column it was printed in,
    never under the one whose label happens to share its line."""
    lines = view_lines(FINANCIAL_NOTE)
    assert lines is not None

    twenty_four = next(line for line in lines if "2024" in line.split(":")[0])
    twenty_three = next(line for line in lines if "2023" in line.split(":")[0])

    assert "Satis gelirleri = 3.560.086.540" in twenty_four
    assert "Satisiadeleri(-) = (16.923.281)" in twenty_four
    assert "Toplam = 3.543.163.259" in twenty_four
    # The 2023 deduction is the number a reader crosses columns to reach; it
    # belongs to 2023 and to nothing else.
    assert "(6.682.818)" not in twenty_four
    assert "Satisiadeleri(-) = (6.682.818)" in twenty_three
    assert "Satis gelirleri = 1.772.898.429" in twenty_three
    assert "(16.923.281)" not in twenty_three


def test_the_labels_come_from_the_header_the_layout_model_stacked_them_in():
    """The unlabelled data row's labels are the ones stacked at the end of the
    label column's own header, in the order they were printed."""
    lines = view_lines(FINANCIAL_NOTE)
    body = lines[0].split(":", 1)[1]
    assert body.index("Satis gelirleri") < body.index("Satisiadeleri(-)")
    # The table's own title is not a row label and is not paired with a value.
    assert "Satislar ve satislarin maliyeti =" not in lines[0]


def test_an_ordinary_table_reads_column_by_column():
    lines = view_lines(ORDINARY_TABLE)
    assert lines == [
        "Kisi: Lisans = 212; Yuksek lisans ve doktora = 41; Kadin personel = 118",
        "Toplam icinde Oran (%): Lisans = 77; Yuksek lisans ve doktora = 15;"
        " Kadin personel = 43",
    ]


# --- what it refuses to say -------------------------------------------------


@pytest.mark.parametrize("table_text", [
    "",
    "not a table at all",
    "|||\n|---|",
    # A label column with one more label than the column has values: the
    # pairing is not determined, so nothing is claimed.
    "|Donem|2024|\n|---|---|\n|Gelir|100|\n|Gider|",
    # A word where a value should be: not a data row this can read.
    "|Donem|2024|\n|---|---|\n|Gelir|(2023) Baslangic|",
])
def test_a_table_it_cannot_pair_with_certainty_yields_nothing(table_text):
    assert view_lines(table_text) is None


# A band header carries its members' values while the members are named on the
# label-only rows beneath it. Read with a column this can name, so the shape is
# what is under test and not the column header.
BAND = "\n".join([
    "|Kalem|Tutar (TL)|",
    "|---|---|",
    "|Uretim maliyeti|(1)<br>(2)<br>(3)|",
    "|Personel||",
    "|Amortisman||",
    "|Diger||",
])


def test_an_unaccounted_for_item_in_the_label_stack_refuses():
    """The unlabelled row borrows its labels from the label column's header
    stack, which may hold the table's own name ahead of them and nothing else.
    One item more and there is no telling which labels the values belong to --
    so nothing is claimed rather than the likeliest guess being written down."""
    crowded = FINANCIAL_NOTE.replace(
        "|**Satislar ve satislarin maliyeti**<br>",
        "|**Satislar ve satislarin maliyeti**<br>Ucuncu bir kalem<br>")
    assert view_lines(crowded) is None
    assert view_lines(FINANCIAL_NOTE) is not None, "the shape it perturbs still reads"


def test_a_band_must_account_for_every_member_row_beneath_it():
    """Its values pair with the members named below it, so the run of those
    rows must be exactly as long as the run of values -- neither shorter, which
    leaves a value unnamed, nor longer, which leaves a member unpaired."""
    assert view_lines(BAND) == ["Tutar (TL): Personel = (1); Amortisman = (2); Diger = (3)"]

    short = BAND.replace("\n".join(["|Diger||"]), "")
    assert view_lines(short) is None

    long = BAND + "\n".join(["", "|Fazladan||"])
    assert view_lines(long) is None


def test_a_chunk_carrying_two_tables_gets_no_reading():
    """With two tables a ``label = value`` line no longer says which table it
    came from, and an unattributed number is the problem, not the fix."""
    tables = [_unit(1, "t-0008", "table", FINANCIAL_NOTE),
              _unit(2, "t-0009", "table", ORDINARY_TABLE)]
    assert table_view_for(tables) is None
    assert table_view_for(tables[:1]) is not None


def test_only_chunks_that_carry_a_readable_table_are_enriched():
    units = _units_with(FINANCIAL_NOTE)
    rows = [
        {"chunk_id": "c1", "text": "prose", "unit_ids": ["p-0002", "p-0003"]},
        {"chunk_id": "c2", "text": FINANCIAL_NOTE, "unit_ids": ["p-0004", "t-0008"]},
    ]
    assert enrich_rows(rows, units) == 1
    assert "table_view" not in rows[0]
    assert "3.560.086.540" in rows[1]["table_view"]
    assert rows[1]["text"] == FINANCIAL_NOTE, "the raw table is never rewritten"


# --- which pipeline produces it ---------------------------------------------


def test_deep_produces_a_reading_and_standard_does_not():
    units = _units_with(FINANCIAL_NOTE)
    settings = DeepAnalysisSettings(use_llm=False, verify=False)

    standard = chunk_document(units, mode=MODE_STANDARD, settings=settings)
    assert all("table_view" not in row for row in standard.rows)

    deep = chunk_document(units, mode=MODE_DEEP, settings=settings)
    carrying = [row for row in deep.rows if row.get("table_view")]
    assert carrying, "the chunk holding the table carries a reading"
    assert deep.report["table_view_chunks"] == len(carrying)
    for row in carrying:
        assert "Satisiadeleri(-) = (16.923.281)" in row["table_view"]
        assert row["table_view"] not in row["text"], "the two representations stay apart"


# --- the Viewer's own answer context -----------------------------------------


def test_the_indexed_chunk_carries_the_reading_but_never_indexes_it():
    """Retrieval reads the chunk's text and its search rendering; the table
    reading is an answer-context aid and stays out of both legs."""
    from amsc.rag_index import IndexedChunk

    chunk = IndexedChunk.from_row(0, {
        "chunk_id": "c1", "text": "|Lisans|77|", "token_count": 4, "unit_ids": [],
        "search_text": "Lisans: Oran (%) = 77",
        "table_view": "Oran (%): Lisans = 77",
    })
    assert chunk.table_view == "Oran (%): Lisans = 77"
    assert "Oran (%): Lisans = 77" not in chunk.retrieval_text
    assert "Lisans: Oran (%) = 77" in chunk.retrieval_text, "the search rendering still is"

    plain = IndexedChunk.from_row(0, {"chunk_id": "c2", "text": "abc", "unit_ids": []})
    assert plain.table_view is None


def _block(**kwargs):
    from amsc.rag_context import ContextBlock

    base = dict(label="S1", chunk_id="c1", index=0, text="|Lisans|77|", token_count=4,
                heading="Personel", section_path=("Personel",), pages=(3,),
                role="hit", seed_chunk_id="c1", rank=1)
    base.update(kwargs)
    return ContextBlock(**base)


def test_the_viewer_context_renders_the_reading_beneath_the_raw_table():
    from amsc.rag_context import AssembledContext
    from amsc.table_view import CONTEXT_HEADER

    text = AssembledContext(
        blocks=[_block(table_view="Oran (%): Lisans = 77")], total_tokens=4, budget=100
    ).render()
    assert "|Lisans|77|" in text, "the document's own table is still there"
    assert CONTEXT_HEADER in text, "and the reading says it is derived"
    assert text.index("|Lisans|77|") < text.index(CONTEXT_HEADER)
    assert text.rstrip().endswith("Oran (%): Lisans = 77")


def test_a_block_with_no_reading_renders_exactly_what_it_always_did():
    """Every Markdown and Standard block, and every table Deep could not read
    with certainty."""
    from amsc.rag_context import AssembledContext
    from amsc.table_view import CONTEXT_HEADER

    text = AssembledContext(blocks=[_block()], total_tokens=4, budget=100).render()
    assert text == "[S1] (Personel; sayfa 3)" + chr(10) + "|Lisans|77|"
    assert CONTEXT_HEADER not in text


def test_the_context_budget_pays_for_the_reading():
    """A reading is rendered, so it is charged; a chunk without one costs
    exactly its own tokens, as it always did."""
    from amsc.rag_context import _context_tokens
    from amsc.rag_index import IndexedChunk

    row = {"chunk_id": "c1", "text": "|Lisans|77|", "token_count": 4, "unit_ids": []}
    plain = IndexedChunk.from_row(0, row)
    carrying = IndexedChunk.from_row(0, dict(row, table_view="Oran (%): Lisans = 77"))

    assert _context_tokens(plain) == plain.token_count == 4
    assert _context_tokens(carrying) > carrying.token_count
