from __future__ import annotations

import pytest

from amsc.chunk_mapping import MAP_OFFSET, map_chunks
from amsc.markdown_chunker import (
    CHUNK_OVERLAP_TOKENS,
    CHUNK_SIZE_TOKENS,
    chunk_units,
    render_markdown,
)
from amsc.models import UnitType

from _chunk_fixtures import WhitespaceCounter, heading, unit, words

COUNTER = WhitespaceCounter()


def split(units, **kwargs):
    kwargs.setdefault("chunk_size_tokens", 20)
    kwargs.setdefault("chunk_overlap_tokens", 4)
    kwargs.setdefault("hard_max_tokens", 200)
    return chunk_units(units, counter=COUNTER, **kwargs)


# --------------------------------------------------------------- rendering


def test_every_unit_span_reproduces_that_unit_text_exactly():
    units = [
        heading("h-1", "One", 1),
        unit("p-1", "first body", order=2, section=("One",)),
        unit("t-1", "|a|b|\n|---|---|", order=3, type=UnitType.TABLE, section=("One",)),
    ]

    document = render_markdown(units)

    for item in units:
        start, end = document.spans[item.unit_id]
        assert document.text[start:end] == item.text


def test_the_atx_marker_is_rendering_and_belongs_to_no_unit():
    units = [heading("h-1", "One", 1), unit("p-1", "body", order=2, section=("One",))]

    document = render_markdown(units)

    assert document.text.startswith("## One")
    start, _ = document.spans["h-1"]
    assert document.text[start:] .startswith("One")
    # the "## " characters sit outside every span
    assert not any(start <= 0 < end for start, end in document.spans.values())


def test_a_heading_is_rendered_at_the_level_the_parser_reported():
    units = [
        unit("h-1", "Deep", order=1, type=UnitType.HEADING, level=4, section=("Deep",)),
        unit("p-1", "body", order=2, section=("Deep",)),
    ]

    assert render_markdown(units).text.startswith("#### Deep")


# ------------------------------------------------------------- separators


def test_a_heading_boundary_is_preferred_over_a_blank_line():
    units = [
        heading("h-1", "One", 1),
        unit("p-1", words(12), order=2, section=("One",)),
        heading("h-2", "Two", 3),
        unit("p-2", words(12, "x"), order=4, section=("Two",)),
    ]

    chunks = split(units, chunk_size_tokens=16, chunk_overlap_tokens=0)

    assert len(chunks) == 2
    assert chunks[0]["text"].startswith("## One")
    assert chunks[1]["text"].startswith("## Two")
    assert "markdown_heading" in chunks[1]["split_strategies"]


def test_without_a_heading_the_cut_falls_back_to_a_blank_line():
    units = [
        unit("p-1", words(12), order=1),
        unit("p-2", words(12, "x"), order=2),
    ]

    chunks = split(units, chunk_size_tokens=16, chunk_overlap_tokens=0)

    assert len(chunks) == 2
    assert chunks[0]["text"] == words(12)
    assert "blank_line" in chunks[1]["split_strategies"]


def test_a_single_oversized_paragraph_falls_all_the_way_to_words():
    units = [unit("p-1", words(60), order=1)]

    chunks = split(units, chunk_size_tokens=20, chunk_overlap_tokens=0)

    assert len(chunks) > 1
    assert any("word" in chunk["split_strategies"] for chunk in chunks)
    # No structural courtesy: this arm cuts a paragraph mid-sentence by design.
    assert all(chunk["token_count"] <= 20 for chunk in chunks)


def test_a_line_boundary_is_used_before_a_word_boundary():
    units = [unit("p-1", "\n".join(words(6, f"l{index}") for index in range(6)), order=1)]

    chunks = split(units, chunk_size_tokens=20, chunk_overlap_tokens=0)

    assert any("line" in chunk["split_strategies"] for chunk in chunks)
    assert not any("word" in chunk["split_strategies"] for chunk in chunks)


# ------------------------------------------------------------------ sizes


def test_overlap_repeats_content_between_neighbouring_chunks():
    units = [unit(f"p-{index}", words(8, f"s{index}"), order=index + 1) for index in range(6)]

    with_overlap = split(units, chunk_size_tokens=20, chunk_overlap_tokens=8)
    without = split(units, chunk_size_tokens=20, chunk_overlap_tokens=0)

    assert sum(chunk["token_count"] for chunk in with_overlap) > sum(
        chunk["token_count"] for chunk in without
    )
    first, second = with_overlap[0], with_overlap[1]
    assert second["char_start"] < first["char_end"]


def test_overlap_never_exceeds_the_configured_budget():
    units = [unit(f"p-{index}", words(8, f"s{index}"), order=index + 1) for index in range(6)]

    chunks = split(units, chunk_size_tokens=20, chunk_overlap_tokens=8)

    for previous, following in zip(chunks, chunks[1:]):
        shared = previous["char_end"] - following["char_start"]
        assert shared <= 0 or COUNTER.count(previous["text"][-shared:]) <= 8


def test_an_overlap_at_least_as_large_as_the_chunk_is_refused():
    units = [unit("p-1", words(30), order=1)]

    with pytest.raises(ValueError, match="chunk_overlap_tokens"):
        chunk_units(units, counter=COUNTER, chunk_size_tokens=10, chunk_overlap_tokens=10)


def test_the_hard_cap_is_an_invariant():
    units = [unit(f"p-{index}", words(8, f"s{index}"), order=index + 1) for index in range(6)]

    with pytest.raises(AssertionError, match="hard cap"):
        chunk_units(
            units,
            counter=COUNTER,
            chunk_size_tokens=20,
            chunk_overlap_tokens=8,
            hard_max_tokens=5,
        )


def test_the_frozen_benchmark_configuration_is_what_the_defaults_say():
    assert (CHUNK_SIZE_TOKENS, CHUNK_OVERLAP_TOKENS) == (700, 140)


# ----------------------------------------------------------------- schema


def test_no_chunk_is_only_a_heading():
    units = [
        heading("h-1", "One", 1),
        heading("h-2", "Two", 2),
        unit("p-1", words(5), order=3, section=("Two",)),
    ]

    chunks = split(units)

    assert len(chunks) == 1
    assert chunks[0]["unit_ids"] == ["p-1"]


def test_heading_is_a_byte_exact_prefix_of_the_chunk_text_or_absent():
    units = [
        heading("h-1", "One", 1),
        unit("p-1", words(12), order=2, section=("One",)),
        unit("p-2", words(12, "x"), order=3, section=("One",)),
    ]

    for chunk in split(units, chunk_size_tokens=16, chunk_overlap_tokens=0):
        if chunk["heading"] is not None:
            assert chunk["text"].startswith(chunk["heading"])


def test_a_chunk_that_opens_mid_paragraph_claims_no_heading():
    units = [
        heading("h-1", "One", 1),
        unit("p-1", words(40), order=2, section=("One",)),
    ]

    chunks = split(units, chunk_size_tokens=20, chunk_overlap_tokens=0)

    assert chunks[0]["heading"] == "## One"
    assert chunks[-1]["heading"] is None


def test_section_paths_and_pages_come_from_the_content_units_covered():
    units = [
        heading("h-1", "One", 1),
        unit("p-1", words(5), order=2, section=("One",)),
        heading("h-2", "Two", 3),
        unit("p-2", words(5, "x"), order=4, section=("Two",)),
    ]

    chunk = split(units)[0]

    assert chunk["section_paths"] == [["One"], ["Two"]]
    assert chunk["unit_ids"] == ["p-1", "p-2"]


def test_character_offsets_address_the_rendered_document_exactly():
    units = [
        heading("h-1", "One", 1),
        unit("p-1", words(12), order=2, section=("One",)),
        unit("p-2", words(12, "x"), order=3, section=("One",)),
    ]
    document = render_markdown(units)

    for chunk in split(units, chunk_size_tokens=16, chunk_overlap_tokens=0):
        assert document.text[chunk["char_start"] : chunk["char_end"]] == chunk["text"]


def test_offsets_let_the_mapping_resolve_every_chunk_arithmetically():
    units = [
        heading("h-1", "One", 1),
        unit("p-1", words(12), order=2, section=("One",)),
        unit("p-2", words(12, "x"), order=3, section=("One",)),
    ]
    chunks = split(units, chunk_size_tokens=16, chunk_overlap_tokens=0)

    mapping = map_chunks(units, chunks, unit_spans=dict(render_markdown(units).spans))

    assert mapping.health["units_never_mapped"] == 0
    assert all(
        segment.method == MAP_OFFSET
        for chunk in mapping.chunks
        for segment in chunk.segments
    )


def test_an_empty_corpus_produces_no_chunks():
    assert chunk_units([], counter=COUNTER) == []
