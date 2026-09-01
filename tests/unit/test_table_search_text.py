"""The searchable rendering of a chunk's tables.

A table arrives as the markdown a layout model produced: merged cells repeated
across every column they span, a header broken over several rows, empty cells
kept, ``<br>`` inside the text. The contract here is that a second
representation is derived from that -- for retrieval only -- and that the raw
markdown reaches the answer model untouched.
"""

from __future__ import annotations

import pytest

from amsc.deep_pipeline import MODE_DEEP, MODE_STANDARD, DeepAnalysisSettings, chunk_document
from amsc.models import RawDocumentUnit
from amsc.rag_index import IndexedChunk
from amsc.table_search_text import enrich_rows, search_text_for


# A table in the shape a layout model actually emits: a caption row, a header
# split over two lines, a cell merged across two columns, and empty cells.
DEGENERATE_TABLE = "\n".join([
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


def _units_with_table():
    path = ["INSAN KAYNAKLARI"]
    units = [_unit(1, "h-0001", "heading", "INSAN KAYNAKLARI", level=1, path=path)]
    for order in range(2, 8):
        units.append(_unit(order, f"p-{order:04d}", "paragraph",
                           ("Kurumun insan kaynaklari politikasi hakkinda bilgi. " * 12).strip(),
                           path=path))
    units.append(_unit(8, "t-0008", "table", DEGENERATE_TABLE, path=path))
    return units


# --- what the rendering keeps ----------------------------------------------


def test_a_table_is_rendered_as_labels_columns_and_values():
    row = {"heading": "INSAN KAYNAKLARI", "section_paths": [["INSAN KAYNAKLARI"]],
           "unit_ids": ["t-0008"]}
    text = search_text_for(row, [_unit(1, "t-0008", "table", DEGENERATE_TABLE)])

    assert "Bolum: INSAN KAYNAKLARI" in text
    assert "Tablo: Personelin ogrenim durumu" in text
    # The header is split over two rows and is read down both of them.
    assert "Sutunlar: Ogrenim durumu, Kisi, Toplam icinde Oran (%)" in text
    # A value stays attached to the category it was printed under -- which is
    # the whole point: "77" on its own is not an answer to anything.
    assert "Lisans: Kisi = 212; Toplam icinde Oran (%) = 77" in text
    # A cell broken by <br> is one label again.
    assert "Yuksek lisans ve doktora: Kisi = 41; Toplam icinde Oran (%) = 15" in text
    # A band label between data rows names what follows rather than becoming a
    # label with no value.
    assert "Kadin:" in text
    assert "Kadin personel: Kisi = 118; Toplam icinde Oran (%) = 43" in text
    # None of the serialisation survives into the index.
    assert "|" not in text and "**" not in text and "<br>" not in text


def test_a_section_named_only_by_a_value_is_not_searched_on():
    """A caption printed above a table can be reported as a section header, and
    the section then bears a number for a name. A name that is only a number
    names nothing."""
    row = {"heading": "%100", "section_paths": [["%100"]], "unit_ids": ["t-0008"]}
    text = search_text_for(row, [_unit(1, "t-0008", "table", DEGENERATE_TABLE)])
    assert "Bolum:" not in text and "Baslik:" not in text
    assert "Lisans: Kisi = 212" in text, "the table is still rendered"


def test_only_chunks_that_carry_a_table_are_enriched():
    units = _units_with_table()
    rows = [
        {"chunk_id": "c1", "text": "prose", "unit_ids": ["p-0002", "p-0003"]},
        {"chunk_id": "c2", "text": DEGENERATE_TABLE, "unit_ids": ["p-0004", "t-0008"]},
    ]
    assert enrich_rows(rows, units) == 1
    assert "search_text" not in rows[0]
    assert rows[1]["search_text"].startswith("Tablo: Personelin ogrenim durumu")
    assert rows[1]["text"] == DEGENERATE_TABLE, "the raw table is never rewritten"


def test_a_table_split_into_fragments_is_rendered_once():
    """A large table reaches a chunk as several fragment ids of one unit."""
    units = _units_with_table()
    rows = [{"chunk_id": "c1", "text": "x", "unit_ids": ["t-0008#f1", "t-0008#f2"]}]
    assert enrich_rows(rows, units) == 1
    assert rows[0]["search_text"].count("Tablo: Personelin ogrenim durumu") == 1


# --- which pipeline produces it ---------------------------------------------


def test_deep_produces_a_search_text_and_standard_does_not():
    """The enrichment is Deep Analysis's, and Standard must be what it was."""
    units = _units_with_table()
    settings = DeepAnalysisSettings(use_llm=False, verify=False)

    standard = chunk_document(units, mode=MODE_STANDARD, settings=settings)
    assert all("search_text" not in row for row in standard.rows)

    deep = chunk_document(units, mode=MODE_DEEP, settings=settings)
    enriched = [row for row in deep.rows if row.get("search_text")]
    assert enriched, "the chunk carrying the table has a searchable rendering"
    assert deep.report["table_search_text_chunks"] == len(enriched)
    for row in enriched:
        assert "Oran (%)" in row["search_text"]
        assert "search_text" not in row["text"], "the two representations stay apart"


# --- the retrieval seam ------------------------------------------------------


def test_the_index_reads_the_rendering_and_the_context_never_does():
    """Both legs get the rendering beside the markdown -- never instead of it
    -- and the answer context keeps the raw text on its own."""
    row = {"chunk_id": "c1", "text": "|Lisans|212|", "token_count": 4,
           "unit_ids": ["t-0008"], "search_text": "Lisans: Oran (%) = 77"}
    chunk = IndexedChunk.from_row(0, row)
    assert chunk.text == "|Lisans|212|", "context text is the document's own"
    assert chunk.search_text == "Lisans: Oran (%) = 77"
    # What is searched is the chunk's own text plus the rendering. A chunk is
    # never searched for under less than the words the document gave it.
    assert "|Lisans|212|" in chunk.retrieval_text
    assert "Lisans: Oran (%) = 77" in chunk.retrieval_text

    plain = IndexedChunk.from_row(0, {"chunk_id": "c2", "text": "abc", "unit_ids": []})
    assert plain.search_text is None
    assert plain.retrieval_text == "abc"


# The shape a financial note takes, and the one the rendering used to lose: the
# label column's header cell carries the row labels the layout model merged into
# it, one column's two values arrive in a single cell, and a deduction is
# written as a parenthesised negative.
MERGED_LABEL_TABLE = "\n".join([
    "|**Satislar ve satislarin maliyeti**<br>Satis gelirleri<br>Satis iadeleri(-)"
    "|**1 Ocak-**<br>**31 Aralik 2024**|",
    "|---|---|",
    "||3.560.086.540<br>(16.923.281)|",
    "|**Toplam**|**3.543.163.259**|",
])


def test_a_header_too_long_to_name_a_column_is_kept_rather_than_dropped():
    """The label column's header is the only place the row labels are written.
    It is too long to be a column name -- repeated onto every row it would
    swamp the index -- so it is kept once, on a line of its own."""
    row = {"heading": None, "section_paths": [], "unit_ids": ["t-0008"]}
    text = search_text_for(row, [_unit(1, "t-0008", "table", MERGED_LABEL_TABLE)])

    assert "Satis gelirleri" in text and "Satis iadeleri(-)" in text
    assert text.count("Satis gelirleri") == 1, "kept once, never repeated per row"


def test_a_cell_of_values_is_a_data_row_not_a_column_name():
    """A parenthesised negative is a number, and a column's two values joined
    into one cell are still values: the row is data, so it never runs on into
    the header and is never repeated as a column's name."""
    row = {"heading": None, "section_paths": [], "unit_ids": ["t-0008"]}
    text = search_text_for(row, [_unit(1, "t-0008", "table", MERGED_LABEL_TABLE)])

    assert "Sutunlar: 1 Ocak- 31 Aralik 2024" in text, "the values are not a name"
    assert text.count("3.560.086.540") == 1
    assert "1 Ocak- 31 Aralik 2024: 3.560.086.540 (16.923.281)" in text
    assert "Toplam: 1 Ocak- 31 Aralik 2024 = 3.543.163.259" in text


@pytest.mark.parametrize("table_text", ["", "not a table at all", "|||\n|---|"])
def test_a_table_that_cannot_be_read_yields_nothing_rather_than_junk(table_text):
    row = {"heading": None, "section_paths": [], "unit_ids": ["t-0008"]}
    assert search_text_for(row, [_unit(1, "t-0008", "table", table_text or "-")]) is None
