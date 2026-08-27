from __future__ import annotations

import pytest

from amsc.hybrid_chunker import chunk_units
from amsc.structural_chunker import chunk_units as structural_chunk_units

from conftest import StaticBoundaryEmbedder
from _chunk_fixtures import WhitespaceCounter, heading, unit, words

COUNTER = WhitespaceCounter()

#: Small enough to build a readable oversized section out of four paragraphs.
LIMITS = dict(min_tokens=50, target_tokens=150, soft_max_tokens=160, hard_max_tokens=1000)


def section_of(*bodies: str):
    units = [heading("h-1", "H", 1)]
    for index, body in enumerate(bodies, start=1):
        units.append(unit(f"p-{index}", body, order=index + 1, section=("H",)))
    return units


def embedder_for(bodies, vectors):
    return StaticBoundaryEmbedder(dict(zip(bodies, vectors)))


def four_paragraphs():
    return [words(60, f"s{index}") for index in range(4)]


def hybrid(units, embedder=None, **kwargs):
    return chunk_units(
        units,
        counter=COUNTER,
        boundary_embedder=embedder,
        arbitrate=embedder is not None,
        **{**LIMITS, **kwargs},
    )


# ------------------------------------------------------- the baseline shape


def test_without_arbitration_it_is_the_structure_first_chunker():
    """The section assembly is shared code; this is what keeps it honest."""
    units = section_of(*four_paragraphs())

    hybrid_rows = hybrid(units).chunks
    structural_rows = structural_chunk_units(units, counter=COUNTER, **LIMITS)

    def without_id(rows):
        return [{key: value for key, value in row.items() if key != "chunk_id"} for row in rows]

    assert without_id(hybrid_rows) == without_id(structural_rows)
    assert [row["chunk_id"] for row in hybrid_rows] != [
        row["chunk_id"] for row in structural_rows
    ]


def test_a_section_that_already_fits_is_never_embedded():
    units = section_of(words(20))
    embedder = embedder_for([words(20)], [[1.0, 0.0]])

    result = hybrid(units, embedder)

    assert embedder.calls == []
    assert result.diagnostics["oversized_section_count"] == 0
    assert result.diagnostics["arbitrated_boundary_count"] == 0


def test_arbitration_without_an_embedder_is_refused():
    with pytest.raises(ValueError, match="boundary embedder"):
        chunk_units(section_of(words(20)), counter=COUNTER, arbitrate=True)


# --------------------------------------------------------------- the rule


def test_the_cut_moves_to_the_higher_shift_candidate_not_the_last_one():
    bodies = four_paragraphs()
    units = section_of(*bodies)
    # p1 is orthogonal to the rest, so the sharpest shift is the *earliest*
    # admissible cut -- the one the greedy rule would have passed over.
    embedder = embedder_for(bodies, [[1.0, 0.0], [0.0, 1.0], [0.0, 1.0], [0.0, 1.0]])

    arbitrated = hybrid(units, embedder)
    greedy = hybrid(units)

    assert arbitrated.diagnostics["arbitration_changed_boundary_count"] >= 1
    assert [row["token_count"] for row in arbitrated.chunks] != [
        row["token_count"] for row in greedy.chunks
    ]
    assert arbitrated.chunks[0]["unit_ids"] == ["p-1"]
    assert greedy.chunks[0]["unit_ids"] == ["p-1", "p-2"]


def test_when_the_signal_is_indifferent_the_baseline_cut_wins():
    bodies = four_paragraphs()
    units = section_of(*bodies)
    embedder = embedder_for(bodies, [[1.0, 0.0]] * 4)

    arbitrated = hybrid(units, embedder)
    greedy = hybrid(units)

    assert arbitrated.diagnostics["arbitrated_boundary_count"] > 0
    assert arbitrated.diagnostics["arbitration_changed_boundary_count"] == 0
    assert [row["text"] for row in arbitrated.chunks] == [row["text"] for row in greedy.chunks]


def test_a_candidate_below_the_minimum_is_not_admissible():
    # The sharpest boundary in this section is right after the tiny first piece,
    # but cutting there would leave a 13-token chunk, under min_tokens=50. The
    # arbitration must not reach for it however sharp it looks.
    bodies = [words(10), words(60, "x"), words(60, "y"), words(60, "z")]
    units = section_of(*bodies)
    embedder = embedder_for(bodies, [[1.0, 0.0], [0.0, 1.0], [0.0, 1.0], [0.0, 1.0]])

    result = hybrid(units, embedder)

    assert result.chunks[0]["unit_ids"] != ["p-1"]
    assert result.chunks[0]["token_count"] >= 50
    # Nothing admissible was sharper, so the baseline cut stands.
    assert result.diagnostics["arbitration_changed_boundary_count"] == 0
    assert [row["text"] for row in result.chunks] == [
        row["text"] for row in hybrid(units).chunks
    ]


def test_a_section_with_no_admissible_cut_falls_back_and_says_so():
    # One piece already exceeds the target, so no cut lands inside the window.
    bodies = [words(400), words(400, "x")]
    units = section_of(*bodies)
    embedder = embedder_for(bodies, [[1.0, 0.0], [0.0, 1.0]])

    result = hybrid(units, embedder, hard_max_tokens=1000)

    assert result.diagnostics["h1_fallback_section_count"] == 1
    assert result.diagnostics["arbitrated_boundary_count"] == 0
    greedy = hybrid(units, hard_max_tokens=1000)
    assert [row["text"] for row in result.chunks] == [row["text"] for row in greedy.chunks]


def test_only_the_pieces_of_oversized_sections_are_embedded():
    small = words(20)
    bodies = four_paragraphs()
    units = section_of(*bodies)
    units.append(heading("h-2", "Small", 100, section=("Small",)))
    units.append(unit("p-9", small, order=101, section=("Small",)))
    embedder = embedder_for(
        [*bodies, small], [[1.0, 0.0], [0.0, 1.0], [0.0, 1.0], [0.0, 1.0], [1.0, 0.0]]
    )

    result = hybrid(units, embedder)

    embedded = {text for call in embedder.calls for text in call}
    assert small not in embedded
    assert result.diagnostics["embedded_piece_count"] == len(bodies)


# ---------------------------------------------------------------- outputs


def test_the_hard_cap_is_an_invariant():
    units = section_of(*four_paragraphs())

    with pytest.raises(AssertionError, match="hard cap"):
        hybrid(units, hard_max_tokens=10)


def test_chunk_rows_carry_the_shared_schema():
    units = section_of(*four_paragraphs())

    row = hybrid(units).chunks[0]

    for key in (
        "chunk_id",
        "text",
        "unit_ids",
        "token_count",
        "pages",
        "section_paths",
        "heading",
        "split_strategies",
    ):
        assert key in row
    assert row["heading"] == "H"
    assert row["text"].startswith("H")


def test_diagnostics_separate_never_asked_from_asked_and_unchanged():
    bodies = four_paragraphs()
    units = section_of(*bodies)
    embedder = embedder_for(bodies, [[1.0, 0.0]] * 4)

    diagnostics = hybrid(units, embedder).diagnostics

    assert diagnostics["arbitration_enabled"] is True
    assert diagnostics["oversized_section_count"] == 1
    assert diagnostics["arbitrated_section_count"] == 1
    assert diagnostics["h1_fallback_section_count"] == 0
    assert diagnostics["admissible_candidate_total"] >= diagnostics["arbitrated_boundary_count"]
    assert diagnostics["window"] == [50, 150]
    assert diagnostics["tuning_status"] == "poc_initial_not_optimized"
