from __future__ import annotations

import pytest

from amsc import chunk_quality as quality
from amsc.chunk_mapping import map_chunks
from amsc.models import UnitType

from _chunk_fixtures import WhitespaceCounter, chunk, heading, unit, words

COUNTER = WhitespaceCounter()


def measure(units, chunks, **kwargs):
    mapping = map_chunks(units, chunks)
    return quality.measure(units, chunks, mapping, counter=COUNTER, **kwargs)


# ------------------------------------------------------------------- sizes


def test_token_distribution_uses_the_frozen_nearest_rank_helper():
    units = [unit(f"p-{i}", words(i + 1), order=i + 1) for i in range(10)]
    chunks = [chunk(f"c-{i}", units[i].text, [units[i].unit_id]) for i in range(10)]

    report = measure(units, chunks)

    assert report["token_count"]["min"] == 1
    assert report["token_count"]["max"] == 10
    assert report["token_count"]["median"] == 5.5
    # nearest rank at 0.90 over ten values is the ninth, not the eighth.
    assert report["token_count"]["p90_nearest_rank"] == 9


def test_size_bands_count_each_threshold_independently():
    units = [unit("p-1", words(5), order=1), unit("p-2", words(50), order=2)]
    chunks = [chunk("c-1", units[0].text, ["p-1"]), chunk("c-2", units[1].text, ["p-2"])]

    bands = measure(units, chunks, min_tokens=10, soft_max_tokens=20, hard_max_tokens=50)[
        "size_bands"
    ]

    assert bands["below_min_count"] == 1
    assert bands["above_soft_max_count"] == 1
    assert bands["at_hard_cap_count"] == 1
    assert bands["over_hard_cap_count"] == 0


# --------------------------------------------------------------- structure


def test_accumulated_headings_do_not_count_as_spanning_two_sections():
    """A heading's own path names the section it opens, not the one it is in."""
    units = [
        heading("h-1", "Outer", 1, section=("Outer",)),
        heading("h-2", "Inner", 2, section=("Inner",)),
        unit("p-1", "body", order=3, section=("Inner",)),
    ]
    chunks = [
        chunk("c-1", "Outer\n\nInner\n\nbody", ["p-1"], heading="Outer\n\nInner")
    ]

    report = measure(units, chunks)

    assert report["structure"]["multi_section_count"] == 0
    assert report["structure"]["multi_heading_path_count"] == 1


def test_content_from_two_sections_in_one_chunk_is_reported():
    units = [
        heading("h-1", "One", 1, section=("One",)),
        unit("p-1", "first", order=2, section=("One",)),
        heading("h-2", "Two", 3, section=("Two",)),
        unit("p-2", "second", order=4, section=("Two",)),
    ]
    chunks = [chunk("c-1", "first\n\nsecond", ["p-1", "p-2"])]

    assert measure(units, chunks)["structure"]["multi_section_count"] == 1


def test_heading_led_and_headingless_chunks_are_counted():
    units = [
        heading("h-1", "One", 1, section=("One",)),
        unit("p-1", "first", order=2, section=("One",)),
        unit("p-2", "second", order=3, section=("One",)),
    ]
    chunks = [
        chunk("c-1", "One\n\nfirst", ["p-1"], heading="One"),
        chunk("c-2", "second", ["p-2"]),
    ]

    structure = measure(units, chunks)["structure"]
    assert structure["heading_led_count"] == 1
    assert structure["without_heading_count"] == 1


def test_a_short_chunk_that_is_only_a_heading_is_page_furniture():
    units = [
        heading("h-1", "Finansal Bilgiler", 1, section=("Finansal Bilgiler",)),
        unit("p-1", words(40), order=2, section=("Finansal Bilgiler",)),
    ]
    chunks = [
        chunk("c-1", "Finansal Bilgiler", [], heading="Finansal Bilgiler"),
        chunk("c-2", units[1].text, ["p-1"]),
    ]

    assert measure(units, chunks, min_tokens=10)["structure"]["furniture_chunk_count"] == 1


def test_a_section_spread_over_two_chunks_counts_as_one_split_run():
    units = [
        heading("h-1", "One", 1, section=("One",)),
        unit("p-1", "first", order=2, section=("One",)),
        unit("p-2", "second", order=3, section=("One",)),
    ]
    chunks = [chunk("c-1", "first", ["p-1"]), chunk("c-2", "second", ["p-2"])]

    structure = measure(units, chunks)["structure"]
    assert structure["section_run_split_count"] == 1


# ----------------------------------------------------------- fragmentation


def test_a_repeated_heading_is_not_counted_as_a_fragmented_unit():
    units = [
        heading("h-1", "One", 1, section=("One",)),
        unit("p-1", "first", order=2, section=("One",)),
        unit("p-2", "second", order=3, section=("One",)),
    ]
    chunks = [
        chunk("c-1", "One\n\nfirst", ["p-1"], heading="One"),
        chunk("c-2", "One\n\nsecond", ["p-2"], heading="One"),
    ]

    fragmentation = measure(units, chunks)["fragmentation"]
    assert fragmentation["headings_repeated_across_chunks"] == 1
    assert fragmentation["content_units_in_multiple_chunks"] == 0


def test_a_table_split_across_chunks_is_reported_as_table_fragmentation():
    table = "|h1|h2|\n|---|---|\n|a|1|\n|b|2|"
    units = [unit("t-1", table, order=1, type=UnitType.TABLE)]
    chunks = [
        chunk("c-1", "|h1|h2|\n|---|---|\n|a|1|", ["t-1#f1"]),
        chunk("c-2", "|h1|h2|\n|---|---|\n|b|2|", ["t-1#f2"]),
    ]

    fragmentation = measure(units, chunks)["fragmentation"]
    assert fragmentation["table_units_fragmented"] == 1
    # A table is cut between rows, so the sentence test must stay silent.
    assert fragmentation["mid_sentence_split_count"] == 0


def test_a_cut_inside_a_word_is_reported_with_both_sides():
    units = [unit("p-1", "Istisnadan yararlanmak icin", order=1)]
    chunks = [
        chunk("c-1", "Istisnadan ya", ["p-1"]),
        chunk("c-2", "rarlanmak icin", ["p-1"]),
    ]

    fragmentation = measure(units, chunks)["fragmentation"]
    assert fragmentation["mid_word_split_count"] == 1
    example = fragmentation["mid_word_examples"][0]
    assert example["left"].endswith("ya")
    assert example["right"].startswith("rarlanmak")


def test_a_paragraph_cut_between_sentences_is_not_a_mid_sentence_split():
    units = [unit("p-1", "First one. Second one.", order=1)]
    chunks = [chunk("c-1", "First one.", ["p-1"]), chunk("c-2", "Second one.", ["p-1"])]

    assert measure(units, chunks)["fragmentation"]["mid_sentence_split_count"] == 0


# ------------------------------------------------------------- duplication


def test_overlap_pushes_duplicate_token_mass_above_one():
    units = [unit("p-1", words(10), order=1), unit("p-2", words(10, "x"), order=2)]
    both = f"{units[0].text}\n\n{units[1].text}"
    chunks = [chunk("c-1", both, ["p-1", "p-2"]), chunk("c-2", both, ["p-1", "p-2"])]

    duplication = measure(units, chunks)["duplication"]
    assert duplication["duplicate_token_mass_ratio"] == pytest.approx(2.0)
    assert duplication["duplicate_chunk_text_count"] == 2
    assert duplication["distinct_chunk_text_count"] == 1


# ---------------------------------------------------------------- coverage


def test_a_content_unit_no_chunk_carries_is_named_not_just_counted():
    units = [unit("p-1", "kept", order=1), unit("p-2", "dropped", order=2)]
    chunks = [chunk("c-1", "kept", ["p-1"])]

    coverage = measure(units, chunks)["coverage"]
    assert coverage["content_units_never_mapped"] == 1
    assert coverage["never_mapped_examples"] == ["p-2"]
    assert coverage["content_unit_coverage"] == pytest.approx(0.5)


def test_headings_are_excluded_from_content_coverage():
    units = [
        heading("h-1", "One", 1, section=("One",)),
        unit("p-1", "body", order=2, section=("One",)),
    ]
    chunks = [chunk("c-1", "body", ["p-1"])]

    coverage = measure(units, chunks)["coverage"]
    assert coverage["content_unit_count"] == 1
    assert coverage["content_unit_coverage"] == pytest.approx(1.0)


# ------------------------------------------------------------------ schema


def test_schema_health_shows_which_keys_a_corpus_actually_carries():
    units = [unit("p-1", "body", order=1)]
    chunks = [{"chunk_id": "c-1", "text": "body", "unit_ids": ["p-1"]}]

    health = measure(units, chunks)["schema_health"]
    assert health["unit_ids"] == 1
    assert health["heading"] == 0
    assert health["section_paths"] == 0


# ------------------------------------------------------ parser vs chunker


def test_unit_level_findings_are_subtracted_as_the_parser_baseline():
    """A sentence-like heading is the parser's doing and must not score an arm."""
    units = [
        heading("h-1", "Bu bir cumledir.", 1, section=("Bu bir cumledir.",)),
        unit("p-1", "body", order=2, section=("Bu bir cumledir.",)),
    ]
    chunks = [chunk("c-1", "Bu bir cumledir.\n\nbody", ["p-1"], heading="Bu bir cumledir.")]

    report = measure(units, chunks)

    assert report["structural_qa"]["parser_baseline_finding_count"] >= 1
    assert report["structural_qa"]["chunk_derived_finding_count"] == 0


def test_a_chunk_spanning_two_section_paths_is_a_chunk_derived_finding():
    units = [
        heading("h-1", "One", 1, section=("One",)),
        unit("p-1", "first", order=2, section=("One",)),
        heading("h-2", "Two", 3, section=("Two",)),
        unit("p-2", "second", order=4, section=("Two",)),
    ]
    chunks = [
        chunk(
            "c-1",
            "first\n\nsecond",
            ["p-1", "p-2"],
            section_paths=[["One"], ["Two"]],
        )
    ]

    report = measure(units, chunks)
    by_rule = report["structural_qa"]["chunk_derived_by_rule"]
    assert by_rule["section_inconsistency"]["MEDIUM"] == 1


def test_the_baseline_can_be_computed_once_and_shared_between_arms():
    units = [
        heading("h-1", "One", 1, section=("One",)),
        unit("p-1", "body", order=2, section=("One",)),
    ]
    baseline = quality.parser_baseline(units)
    chunks = [chunk("c-1", "One\n\nbody", ["p-1"], heading="One")]

    shared = measure(units, chunks, baseline=baseline)
    standalone = measure(units, chunks)

    assert shared["structural_qa"] == standalone["structural_qa"]
