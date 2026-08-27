"""Structure-first, told which headings actually bear hierarchy.

The rule the chunker has always applied -- open a chunk at every heading -- is
correct only when every heading opens a section. On a card grid it is not, and
this is where the canonical's ``opens_section`` takes over that decision.
"""

from __future__ import annotations

from amsc.models import RawDocumentUnit, SemanticRole, UnitType
from amsc.structural_chunker import chunk_units

from tests.conftest import WordTokenCounter


def unit(unit_id, order, text, unit_type=UnitType.PARAGRAPH, section=("A",),
         role=None, page=1):
    opens = None if role is None else role in (SemanticRole.SECTION, SemanticRole.GROUP)
    return RawDocumentUnit(
        document_id="doc",
        unit_id=unit_id,
        order=order,
        text=text,
        type=unit_type,
        heading_level=2 if unit_type == UnitType.HEADING else None,
        semantic_role=role,
        opens_section=opens,
        section_path=list(section),
        source={"page": page},
    )


def award_page(role):
    """A chapter, then three award cards, exactly as page 12 is laid out."""
    units = [
        unit("h-1", 1, "5. ODUL VE BASARILARIMIZ", UnitType.HEADING,
             role=SemanticRole.SECTION, section=("5. ODUL VE BASARILARIMIZ",))
    ]
    order = 2
    for index, name in enumerate(("Birinci odul", "Ikinci odul", "Ucuncu odul")):
        units.append(
            unit("h-%d" % (index + 2), order, name, UnitType.HEADING, role=role,
                 section=("5. ODUL VE BASARILARIMIZ",))
        )
        order += 1
        units.append(
            unit("p-%d" % (index + 2), order, "aciklama %d" % index,
                 section=("5. ODUL VE BASARILARIMIZ",))
        )
        order += 1
    return units


def chunk(units, **flags):
    return chunk_units(units, counter=WordTokenCounter(), **flags)


# ------------------------------------------------------------------ default


def test_the_flag_is_off_by_default_and_every_heading_still_opens_a_chunk():
    units = award_page(SemanticRole.ITEM)

    assert len(chunk(units)) == len(chunk(units, respect_semantic_roles=False))
    # Three, not four: the undersized-neighbour merge already rejoins the first
    # card with the chapter heading above it.
    assert len(chunk(units)) == 3


def test_a_corpus_that_carries_no_role_decision_is_chunked_identically():
    """Switching the flag on against an older canonical must change nothing."""
    units = award_page(None)

    assert chunk(units) == chunk(units, respect_semantic_roles=True)


# -------------------------------------------------------------- roles honoured


def test_item_titles_stop_exploding_one_section_into_many():
    units = award_page(SemanticRole.ITEM)

    before = chunk(units)
    after = chunk(units, respect_semantic_roles=True)

    assert len(before) == 3
    assert len(after) == 1


def test_an_item_title_is_still_rendered_where_it_was_printed():
    units = award_page(SemanticRole.ITEM)

    text = chunk(units, respect_semantic_roles=True)[0]["text"]

    for name in ("Birinci odul", "Ikinci odul", "Ucuncu odul"):
        assert name in text
    assert text.index("Birinci odul") < text.index("aciklama 0") < text.index("Ikinci odul")


def test_an_item_title_still_contributes_its_unit_id():
    units = award_page(SemanticRole.ITEM)

    ids = chunk(units, respect_semantic_roles=True)[0]["unit_ids"]

    assert "h-2" in ids and "p-2" in ids


def test_a_group_label_still_opens_a_section():
    units = [
        unit("h-1", 1, "5. ODULLER", UnitType.HEADING, role=SemanticRole.SECTION),
        unit("p-1", 2, "giris"),
        unit("h-2", 3, "2018", UnitType.HEADING, role=SemanticRole.GROUP,
             section=("5. ODULLER", "2018")),
        unit("p-2", 4, "govde", section=("5. ODULLER", "2018")),
    ]

    assert len(chunk(units, respect_semantic_roles=True)) == 2


def test_display_type_is_carried_as_body_not_as_a_boundary():
    units = [
        unit("h-1", 1, "2. ORTAKLIK YAPISI", UnitType.HEADING, role=SemanticRole.SECTION),
        unit("h-2", 2, "Turkiye'nin onde gelen bankalarindan gelen guc",
             UnitType.HEADING, role=SemanticRole.DISPLAY),
        unit("p-1", 3, "KKB 11 bankanin ortakligindadir."),
    ]

    chunks = chunk(units, respect_semantic_roles=True)

    assert len(chunks) == 1
    assert "onde gelen" in chunks[0]["text"]


# ------------------------------------------------------------ preferred seam


def test_an_oversized_section_is_cut_at_an_item_title_not_mid_run():
    units = [unit("h-1", 1, "1. BOLUM", UnitType.HEADING, role=SemanticRole.SECTION)]
    order = 2
    for index in range(6):
        units.append(
            unit("h-i%d" % index, order, "Kalem %d" % index, UnitType.HEADING,
                 role=SemanticRole.ITEM)
        )
        order += 1
        units.append(unit("p-i%d" % index, order, " ".join(["kelime"] * 60)))
        order += 1

    chunks = chunk(
        units, respect_semantic_roles=True,
        min_tokens=40, target_tokens=140, soft_max_tokens=180, hard_max_tokens=400,
    )

    assert len(chunks) > 1
    # Every chunk after the first opens on the item title it belongs to, so no
    # award is separated from its own description.
    for row in chunks[1:]:
        assert row["text"].lstrip().startswith("1. BOLUM") or "Kalem" in row["text"]
    # Every description stays with the title above it: each chunk holds as many
    # bodies as titles.
    for row in chunks:
        assert row["text"].count("Kalem") == len(
            [p for p in row["unit_ids"] if p.startswith("p-i")]
        )


def test_the_hard_cap_still_holds_with_roles_on():
    units = [unit("h-1", 1, "1. BOLUM", UnitType.HEADING, role=SemanticRole.SECTION)]
    order = 2
    for index in range(12):
        units.append(
            unit("h-i%d" % index, order, "Kalem %d" % index, UnitType.HEADING,
                 role=SemanticRole.ITEM)
        )
        order += 1
        units.append(unit("p-i%d" % index, order, " ".join(["kelime"] * 80)))
        order += 1

    chunks = chunk(
        units, respect_semantic_roles=True,
        min_tokens=40, target_tokens=200, soft_max_tokens=260, hard_max_tokens=300,
    )

    assert all(row["token_count"] <= 300 for row in chunks)


def test_a_run_of_items_under_the_soft_max_is_still_cut_at_its_seams():
    """One long letter with bold run-in subheads must not survive as one chunk."""
    units = [unit("h-1", 1, "9. BASKANIN MESAJI", UnitType.HEADING,
                  role=SemanticRole.SECTION)]
    order = 2
    for index in range(4):
        units.append(
            unit("h-s%d" % index, order, "Ara baslik %d" % index, UnitType.HEADING,
                 role=SemanticRole.ITEM)
        )
        order += 1
        units.append(unit("p-s%d" % index, order, " ".join(["kelime"] * 40)))
        order += 1

    whole = chunk(units, min_tokens=30, target_tokens=100, soft_max_tokens=400,
                  hard_max_tokens=900)
    seamed = chunk(units, respect_semantic_roles=True, min_tokens=30,
                   target_tokens=100, soft_max_tokens=400, hard_max_tokens=900)

    # Without roles the whole letter is one section under the soft maximum.
    assert len(whole) == 4
    # With them it is cut at the subheads instead of left whole.
    assert len(seamed) > 1
    assert max(row["token_count"] for row in seamed) < 400
