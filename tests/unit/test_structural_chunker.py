from __future__ import annotations

import pytest

from amsc.models import RawDocumentUnit, UnitType
from amsc.structural_chunker import chunk_units, split_unit_text

from tests.conftest import WordTokenCounter


def unit(unit_id, order, text, unit_type=UnitType.PARAGRAPH, section=("A",), page=1):
    return RawDocumentUnit(
        document_id="doc",
        unit_id=unit_id,
        order=order,
        text=text,
        type=unit_type,
        heading_level=2 if unit_type == UnitType.HEADING else None,
        section_path=list(section),
        source={"page": page},
    )


TABLE = "|H1|H2|\n|---|---|\n|a1|a2|\n|b1|b2|\n|c1|c2|\n|d1|d2|"


def test_table_split_repeats_header_and_never_breaks_a_row():
    counter = WordTokenCounter()
    fragments = split_unit_text(
        TABLE, unit_type=UnitType.TABLE, max_tokens=4, counter=counter
    )
    assert len(fragments) > 1
    assert all(f.strategy == "table_row_group" for f in fragments)
    for fragment in fragments:
        assert fragment.text.startswith("|H1|H2|\n|---|---|")
        for line in fragment.text.splitlines():
            assert line.startswith("|") and line.endswith("|")


def test_list_split_breaks_on_item_boundaries():
    counter = WordTokenCounter()
    text = "- alpha one\n- beta two\n- gamma three\n- delta four"
    fragments = split_unit_text(
        text, unit_type=UnitType.LIST, max_tokens=4, counter=counter
    )
    assert len(fragments) > 1
    assert all(f.strategy == "list_items" for f in fragments)
    for fragment in fragments:
        assert all(line.startswith("- ") for line in fragment.text.splitlines())


def test_paragraph_split_uses_sentence_boundaries_not_characters():
    counter = WordTokenCounter()
    text = "Bir cumle burada. Ikinci cumle burada. Ucuncu cumle burada."
    fragments = split_unit_text(
        text, unit_type=UnitType.PARAGRAPH, max_tokens=4, counter=counter
    )
    assert all(f.strategy in {"sentences", "words"} for f in fragments)
    joined = " ".join(f.text for f in fragments)
    assert set(joined.split()) == set(text.split())


def test_every_chunk_opens_on_its_own_section():
    counter = WordTokenCounter()
    units = [
        unit("h-1", 1, "Birinci Bolum", UnitType.HEADING, ("Birinci Bolum",)),
        unit("p-1", 2, "alpha " * 20, section=("Birinci Bolum",)),
        unit("h-2", 3, "Ikinci Bolum", UnitType.HEADING, ("Ikinci Bolum",)),
        unit("p-2", 4, "beta " * 20, section=("Ikinci Bolum",)),
    ]
    chunks = chunk_units(units, counter=counter, min_tokens=5, target_tokens=40,
                         soft_max_tokens=60, hard_max_tokens=80)
    assert len(chunks) == 2
    assert [c["heading"] for c in chunks] == ["Birinci Bolum", "Ikinci Bolum"]
    for chunk in chunks:
        assert len(chunk["section_paths"]) == 1


def test_hard_cap_is_an_invariant():
    counter = WordTokenCounter()
    units = [
        unit("h-1", 1, "Bolum", UnitType.HEADING),
        unit("t-1", 2, TABLE, UnitType.TABLE),
        unit("p-1", 3, "kelime " * 300),
    ]
    chunks = chunk_units(units, counter=counter, min_tokens=5, target_tokens=40,
                         soft_max_tokens=60, hard_max_tokens=80)
    assert chunks
    for chunk in chunks:
        assert chunk["token_count"] <= 80


def test_undersized_neighbours_merge_within_a_section():
    counter = WordTokenCounter()
    units = [
        unit("h-1", 1, "Bolum", UnitType.HEADING),
        unit("p-1", 2, "a b c"),
        unit("p-2", 3, "d e f"),
    ]
    chunks = chunk_units(units, counter=counter, min_tokens=50, target_tokens=200,
                         soft_max_tokens=300, hard_max_tokens=400)
    assert len(chunks) == 1
    assert chunks[0]["unit_ids"] == ["p-1", "p-2"]


def test_output_is_deterministic():
    counter = WordTokenCounter()
    units = [
        unit("h-1", 1, "Bolum", UnitType.HEADING),
        unit("p-1", 2, "alpha " * 50),
        unit("t-1", 3, TABLE, UnitType.TABLE),
    ]
    first = chunk_units(units, counter=counter)
    second = chunk_units(units, counter=counter)
    assert first == second


@pytest.mark.parametrize("unit_type", [UnitType.PARAGRAPH, UnitType.LIST, UnitType.TABLE])
def test_short_text_is_never_split(unit_type):
    counter = WordTokenCounter()
    fragments = split_unit_text("kisa metin", unit_type=unit_type, max_tokens=50,
                                counter=counter)
    assert [f.strategy for f in fragments] == ["whole"]
