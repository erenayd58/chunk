from __future__ import annotations

import json

import pytest

from amsc.chunk_mapping import (
    MAP_NORMALIZED,
    MAP_OFFSET,
    MAP_PROVENANCE,
    MAP_SEQUENTIAL,
    base_unit_id,
    map_chunks,
)
from amsc.models import UnitType

from _chunk_fixtures import chunk, heading, unit


# ---------------------------------------------------------------- fragment ids


@pytest.mark.parametrize(
    "given,expected",
    [
        ("t-00186#f2", "t-00186"),
        ("t-00186", "t-00186"),
        ("p-1#f11", "p-1"),
        ("odd#fx", "odd#fx"),
    ],
)
def test_base_unit_id_strips_only_fragment_suffixes(given, expected):
    assert base_unit_id(given) == expected


def test_fragment_ids_resolve_to_their_base_unit():
    units = [unit("t-1", "a\nb\nc", order=1, type=UnitType.TABLE)]
    mapping = map_chunks(units, [chunk("c1", "a\nb", ["t-1#f1"])])

    assert mapping.chunks[0].unit_ids() == ("t-1",)
    assert mapping.chunks[0].unmapped_unit_ids == ()


# ------------------------------------------------------------------- rung 0


def test_offset_rung_is_arithmetic_and_wins_when_spans_are_supplied():
    units = [unit("p-1", "alpha", order=1), unit("p-2", "beta", order=2)]
    spans = {"p-1": (0, 5), "p-2": (7, 11)}
    rendered = "alpha\n\nbeta"

    mapping = map_chunks(
        units,
        [chunk("c1", rendered[3:], [], char_start=3, char_end=len(rendered))],
        unit_spans=spans,
    )

    segments = mapping.chunks[0].segments
    assert [s.method for s in segments] == [MAP_OFFSET, MAP_OFFSET]
    # p-1 is entered part-way: only its last two characters are in the chunk.
    assert (segments[0].unit_id, segments[0].unit_start, segments[0].unit_end) == ("p-1", 3, 5)
    assert (segments[1].unit_id, segments[1].unit_start, segments[1].unit_end) == ("p-2", 0, 4)
    assert mapping.chunks[0].coverage["p-2"] == pytest.approx(1.0)
    assert mapping.chunks[0].coverage["p-1"] == pytest.approx(0.4)


def test_offset_rung_is_skipped_when_the_chunk_declares_no_range():
    units = [unit("p-1", "alpha", order=1)]
    mapping = map_chunks(units, [chunk("c1", "alpha", ["p-1"])], unit_spans={"p-1": (0, 5)})

    assert [s.method for s in mapping.chunks[0].segments] == [MAP_PROVENANCE]


# ------------------------------------------------------------------- rung 1


def test_provenance_rung_locates_units_verbatim():
    units = [unit("p-1", "alpha", order=1), unit("p-2", "beta", order=2)]
    mapping = map_chunks(units, [chunk("c1", "alpha\n\nbeta", ["p-1", "p-2"])])

    segments = mapping.chunks[0].segments
    assert [(s.unit_id, s.chunk_start, s.chunk_end) for s in segments] == [
        ("p-1", 0, 5),
        ("p-2", 7, 11),
    ]
    assert all(s.method == MAP_PROVENANCE for s in segments)
    assert mapping.health["units_never_mapped"] == 0


def test_repeated_text_maps_forward_rather_than_to_the_first_occurrence():
    units = [unit("p-1", "same", order=1), unit("p-2", "same", order=2)]
    mapping = map_chunks(units, [chunk("c1", "same\n\nsame", ["p-1", "p-2"])])

    starts = [s.chunk_start for s in mapping.chunks[0].segments]
    assert starts == [0, 6]


# ------------------------------------------------------------------- rung 2


def test_normalized_rung_matches_across_reflowed_whitespace():
    units = [unit("p-1", "alpha\n   beta", order=1)]
    mapping = map_chunks(units, [chunk("c1", "intro\n\nalpha beta", ["p-1"])])

    segment = mapping.chunks[0].segments[0]
    assert segment.method == MAP_NORMALIZED
    assert "alpha beta" == "intro\n\nalpha beta"[segment.chunk_start : segment.chunk_end]


# ------------------------------------------------------------------- rung 3


def test_split_table_maps_by_lines_with_the_header_repeated_in_both_parts():
    table = "|h1|h2|\n|---|---|\n|a|1|\n|b|2|"
    units = [unit("t-1", table, order=1, type=UnitType.TABLE)]
    first = "|h1|h2|\n|---|---|\n|a|1|"
    second = "|h1|h2|\n|---|---|\n|b|2|"

    mapping = map_chunks(
        units, [chunk("c1", first, ["t-1#f1"]), chunk("c2", second, ["t-1#f2"])]
    )

    assert all(
        segment.method == MAP_SEQUENTIAL
        for part in mapping.chunks
        for segment in part.segments
    )
    # Neither part carries the whole unit, and between them every row is covered.
    assert mapping.chunks[0].coverage["t-1"] < 1.0
    assert mapping.chunks[1].coverage["t-1"] < 1.0
    covered = set()
    for part in mapping.chunks:
        for segment in part.segments:
            covered.update(range(segment.unit_start, segment.unit_end))
    assert len(covered) >= len(table) - 4  # the two row separators are not text


def test_a_fragment_rejoined_with_different_whitespace_is_still_located():
    """The structure-first splitter rejoins sentences with a single space.

    A paragraph that contained a double space therefore stops matching a few
    characters in, and a byte-exact affix search finds only the first sentence.
    Retrying against whitespace-normalised text is what keeps the unit mapped --
    on the holdout corpus exactly one unit reached this rung.
    """
    text = "Birinci cumle.  Ikinci cumle.  Ucuncu cumle."
    units = [heading("h-1", "Baslik", 1), unit("p-1", text, order=2, section=("Baslik",))]
    # Fragments as the splitter emits them: single-spaced, so neither half is a
    # byte-exact slice of the unit. Both parts repeat the section's heading.
    first = "Baslik\n\nBirinci cumle. Ikinci cumle."
    second = "Baslik\n\nUcuncu cumle."

    mapping = map_chunks(
        units,
        [
            chunk("c1", first, ["p-1#f1"], heading="Baslik"),
            chunk("c2", second, ["p-1#f2"], heading="Baslik"),
        ],
    )

    assert mapping.health["units_never_mapped"] == 0
    body = [
        segment
        for chunk in mapping.chunks
        for segment in chunk.segments
        if segment.unit_id == "p-1"
    ]
    assert [segment.method for segment in body] == [MAP_SEQUENTIAL, MAP_SEQUENTIAL]
    covered = sum(chunk.coverage["p-1"] for chunk in mapping.chunks)
    assert covered == pytest.approx(1.0, abs=0.1)
    # Offsets still address the raw unit text, not the normalised copy.
    assert text[body[0].unit_start : body[0].unit_end].startswith("Birinci cumle.")
    assert text[body[1].unit_start : body[1].unit_end].endswith("Ucuncu cumle.")


def test_mid_word_split_is_located_as_a_prefix_and_a_suffix():
    units = [unit("p-1", "Istisnadan yararlanmak icin", order=1)]
    mapping = map_chunks(
        units,
        [
            chunk("c1", "lead\n\nIstisnadan ya", ["p-1"]),
            chunk("c2", "rarlanmak icin\n\ntail", ["p-1"]),
        ],
    )

    first, second = mapping.chunks
    assert first.segments[0].method == MAP_SEQUENTIAL
    assert first.segments[0].unit_start == 0
    assert second.segments[0].unit_end == len("Istisnadan yararlanmak icin")
    assert first.coverage["p-1"] + second.coverage["p-1"] == pytest.approx(1.0)


# ------------------------------------------------------------------ unmapped


def test_a_unit_that_is_nowhere_in_the_chunk_is_reported_not_silently_dropped():
    units = [unit("p-1", "alpha", order=1), unit("p-2", "beta", order=2)]
    mapping = map_chunks(units, [chunk("c1", "alpha", ["p-1", "p-2"])])

    assert mapping.chunks[0].unmapped_unit_ids == ("p-2",)
    assert mapping.health["unmapped:not_found"] == 1
    assert mapping.health["units_never_mapped"] == 1


def test_an_unknown_unit_id_is_reported_separately():
    units = [unit("p-1", "alpha", order=1)]
    mapping = map_chunks(units, [chunk("c1", "alpha", ["p-1", "ghost"])])

    assert mapping.chunks[0].unmapped_unit_ids == ("ghost",)
    assert mapping.health["unmapped:unknown_unit_id"] == 1


# ------------------------------------------------------------------- headings


def test_a_rendered_heading_is_attributed_to_its_heading_unit():
    units = [
        heading("h-1", "Section One", 1),
        unit("p-1", "body", order=2, section=("Section One",)),
    ]
    mapping = map_chunks(
        units, [chunk("c1", "Section One\n\nbody", ["p-1"], heading="Section One")]
    )

    assert [s.unit_id for s in mapping.chunks[0].segments] == ["h-1", "p-1"]
    assert mapping.chunks[0].unmapped_unit_ids == ()
    assert mapping.health["units_never_mapped"] == 0


def test_a_heading_repeated_by_a_split_section_maps_in_every_part():
    units = [
        heading("h-1", "Section One", 1),
        unit("p-1", "first", order=2, section=("Section One",)),
        unit("p-2", "second", order=3, section=("Section One",)),
    ]
    mapping = map_chunks(
        units,
        [
            chunk("c1", "Section One\n\nfirst", ["p-1"], heading="Section One"),
            chunk("c2", "Section One\n\nsecond", ["p-2"], heading="Section One"),
        ],
    )

    assert [s.unit_id for s in mapping.chunks[0].segments] == ["h-1", "p-1"]
    assert [s.unit_id for s in mapping.chunks[1].segments] == ["h-1", "p-2"]


def test_several_accumulated_headings_map_to_each_of_their_units():
    units = [
        heading("h-1", "Outer", 1),
        heading("h-2", "Inner", 2),
        unit("p-1", "body", order=3, section=("Inner",)),
    ]
    mapping = map_chunks(
        units, [chunk("c1", "Outer\n\nInner\n\nbody", ["p-1"], heading="Outer\n\nInner")]
    )

    assert [s.unit_id for s in mapping.chunks[0].segments] == ["h-1", "h-2", "p-1"]


def test_a_heading_that_matches_no_heading_unit_is_reported():
    units = [unit("p-1", "body", order=1)]
    mapping = map_chunks(units, [chunk("c1", "Invented\n\nbody", ["p-1"], heading="Invented")])

    assert mapping.chunks[0].unmapped_unit_ids == ("c1:heading",)
    assert mapping.health["unmapped:heading"] == 1


def test_a_heading_the_chunk_text_does_not_start_with_is_reported():
    units = [
        heading("h-1", "Section One", 1),
        unit("p-1", "body", order=2, section=("Section One",)),
    ]
    mapping = map_chunks(
        units, [chunk("c1", "body only", ["p-1"], heading="Section One")]
    )

    assert "c1:heading" in mapping.chunks[0].unmapped_unit_ids


# -------------------------------------------------------------------- views


def test_segments_by_unit_groups_a_split_unit_across_its_chunks():
    units = [unit("p-1", "alpha beta", order=1)]
    mapping = map_chunks(
        units, [chunk("c1", "alpha", ["p-1"]), chunk("c2", "beta", ["p-1"])]
    )

    grouped = mapping.segments_by_unit()
    assert [chunk_id for chunk_id, _ in grouped["p-1"]] == ["c1", "c2"]


def test_as_dict_round_trips_through_json_with_sorted_keys():
    units = [unit("p-1", "alpha", order=1)]
    mapping = map_chunks(units, [chunk("c1", "alpha", ["p-1"])])

    payload = json.loads(json.dumps(mapping.as_dict(), sort_keys=True))
    assert payload["chunks"][0]["chunk_id"] == "c1"
    assert payload["health"]["units_never_mapped"] == 0
