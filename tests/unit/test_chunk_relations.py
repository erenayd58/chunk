"""The continuation relation and the local expander, held to their rules."""

from __future__ import annotations

import json

import pytest

from amsc.chunk_relations import (
    MARKDOWN_SPLIT_CONTINUATION,
    SECTION_LABEL_CONTINUATION,
    TOKEN_BUDGET_CONTINUATION,
    continuation_groups,
    derive_continuations,
    derive_tree,
    expand_context,
)


def chunk(cid, tokens, *, heading="**5. BOLUM**", path=("**5. BOLUM**",), pages=(1,), units=("p-1",)):
    return {
        "chunk_id": cid,
        "token_count": tokens,
        "heading": heading,
        "section_paths": [list(path)],
        "pages": list(pages),
        "unit_ids": list(units),
    }


def section_run():
    """One oversized section in three plain budget splits, then a new section."""
    return [
        chunk("c-1", 600, units=("p-1", "p-2")),
        chunk("c-2", 650, units=("p-3",)),
        chunk("c-3", 200, units=("p-4",)),
        chunk("c-4", 500, heading="**6. YENI**", path=("**6. YENI**",), units=("p-5",)),
    ]


def labelled_run():
    """The same shape, but the second boundary lands on a label seam."""
    return [
        chunk("c-1", 600, units=("p-1", "p-2")),
        chunk("c-2", 650, units=("p-3",)),
        chunk("c-3", 200, units=("h-9", "p-4")),
        chunk("c-4", 500, heading="**6. YENI**", path=("**6. YENI**",), units=("p-5",)),
    ]


# --- deriving the relation --------------------------------------------------


def test_same_section_adjacent_budget_split_is_a_continuation():
    links = derive_continuations(section_run(), kind="structure_first")

    assert [(l["from_chunk"], l["to_chunk"]) for l in links] == [
        ("c-1", "c-2"),
        ("c-2", "c-3"),
    ]
    first = links[0]
    assert first["relation_type"] == TOKEN_BUDGET_CONTINUATION
    assert first["same_section"] is True
    assert first["boundary_reason"] == "budget_split"
    assert first["section_path"] == ["**5. BOLUM**"]
    assert first["cut_position"] == "greedy"
    assert links[1]["relation_type"] == TOKEN_BUDGET_CONTINUATION


def test_a_label_seam_is_recorded_but_is_not_a_token_budget_continuation():
    links = derive_continuations(labelled_run(), kind="structure_first")

    assert links[0]["relation_type"] == TOKEN_BUDGET_CONTINUATION
    assert links[1]["relation_type"] == SECTION_LABEL_CONTINUATION
    assert links[1]["boundary_reason"] == "label_split"


def test_hybrid_budget_cuts_state_their_position_is_not_recorded():
    links = derive_continuations(section_run(), kind="hybrid_h1")
    assert all(
        l["cut_position"] == "not_recorded_greedy_or_arbitrated" for l in links
    )
    assert all(l["relation_type"] == TOKEN_BUDGET_CONTINUATION for l in links)


def test_a_section_change_is_not_a_continuation():
    links = derive_continuations(section_run(), kind="structure_first")
    assert all(l["to_chunk"] != "c-4" for l in links)


def test_a_typographically_different_banner_breaks_the_chain():
    """The real 0213/0214 case: same words, different emphasis, no link."""
    chunks = [
        chunk("c-1", 300),
        chunk("c-2", 300, heading="5. BOLUM", path=("5. BOLUM",)),
    ]
    assert derive_continuations(chunks, kind="structure_first") == []


def test_distant_chunks_are_never_linked():
    """c-1 and c-3 share a section but sit apart; no relation is invented."""
    chunks = [
        chunk("c-1", 300),
        chunk("c-2", 300, heading="**6. ARA**", path=("**6. ARA**",)),
        chunk("c-3", 300),
    ]
    links = derive_continuations(chunks, kind="structure_first")

    assert links == []
    # And by construction every link the deriver can ever emit is adjacent.
    for link in derive_continuations(section_run(), kind="structure_first"):
        assert link["to_index"] == link["from_index"] + 1


def test_markdown_links_are_their_own_relation_type():
    chunks = [
        chunk("m-1", 600, heading=None, units=("p-1", "p-2")),
        chunk("m-2", 600, heading=None, units=("p-2", "p-3")),
        chunk("m-3", 600, heading=None, units=("p-4",)),
    ]
    links = derive_continuations(chunks, kind="markdown_recursive")

    assert [l["boundary_reason"] for l in links] == ["md_overlap", "md_size"]
    assert {l["relation_type"] for l in links} == {MARKDOWN_SPLIT_CONTINUATION}


def test_an_empty_section_path_never_links():
    chunks = [
        chunk("c-1", 300, path=()),
        chunk("c-2", 300, path=()),
    ]
    chunks[0]["section_paths"] = []
    chunks[1]["section_paths"] = []
    assert derive_continuations(chunks, kind="structure_first") == []


def test_groups_are_maximal_runs():
    links = derive_continuations(section_run(), kind="structure_first")
    assert continuation_groups(4, links) == [0, 0, 0, None]


# --- the expander -----------------------------------------------------------


def run_expand(seed, **kwargs):
    chunks = section_run()
    links = derive_continuations(chunks, kind="structure_first")
    return expand_context(seed, chunks=chunks, links=links, **kwargs)


def test_expansion_keeps_document_order_and_contiguity():
    result = run_expand("c-2", max_total_tokens=2000)

    assert result.chunk_ids == ["c-1", "c-2", "c-3"]
    assert result.added_before == ["c-1"]
    assert result.added_after == ["c-3"]
    assert result.total_tokens == 600 + 650 + 200


def test_expansion_respects_the_hard_budget():
    # Seed 650; prev (600) fits at 1250 <= 1300; next (200) would reach 1450.
    result = run_expand("c-2", max_total_tokens=1300)

    assert result.chunk_ids == ["c-1", "c-2"]
    assert result.total_tokens == 1250
    assert result.stopped["after"] == "budget"


def test_expansion_stops_at_the_section_boundary():
    result = run_expand("c-3", max_total_tokens=10_000)

    assert result.chunk_ids == ["c-1", "c-2", "c-3"]
    assert "c-4" not in result.chunk_ids
    assert result.stopped["after"] == "section_boundary"


def test_expansion_does_not_cross_a_label_seam():
    """Only TOKEN_BUDGET_CONTINUATION is walked; a label boundary stops it."""
    chunks = labelled_run()
    links = derive_continuations(chunks, kind="structure_first")

    result = expand_context("c-2", chunks=chunks, links=links, max_total_tokens=10_000)

    assert result.chunk_ids == ["c-1", "c-2"]
    assert result.stopped["after"] == "non_budget_boundary"


def test_expansion_adds_no_duplicates():
    result = run_expand("c-1", max_total_tokens=10_000)
    assert len(result.chunk_ids) == len(set(result.chunk_ids))


def test_a_chunk_without_links_expands_to_itself():
    result = run_expand("c-4", max_total_tokens=10_000)
    assert result.chunk_ids == ["c-4"]
    assert result.stopped == {"before": "section_boundary", "after": "section_boundary"}


def test_disabled_expansion_changes_nothing():
    result = run_expand("c-2", max_total_tokens=10_000, enabled=False)

    assert result.chunk_ids == ["c-2"]
    assert result.total_tokens == 650
    assert result.stopped == {"expansion": "disabled"}


def test_the_neighbor_limit_is_respected():
    result = run_expand("c-3", max_total_tokens=10_000, max_neighbors_each_side=1)
    assert result.chunk_ids == ["c-2", "c-3"]
    assert result.stopped["before"] == "neighbor_limit"


def test_an_unknown_seed_is_an_error():
    with pytest.raises(ValueError, match="unknown chunk id"):
        run_expand("c-999", max_total_tokens=100)


def test_derivation_is_deterministic():
    once = derive_continuations(section_run(), kind="structure_first")
    twice = derive_continuations(section_run(), kind="structure_first")
    assert json.dumps(once, sort_keys=True) == json.dumps(twice, sort_keys=True)


# --- sidecar tree guards ----------------------------------------------------


def test_derive_tree_refuses_to_write_into_the_benchmark_tree(tmp_path):
    with pytest.raises(ValueError, match="frozen benchmark tree"):
        derive_tree(tmp_path / "bench", tmp_path / "bench" / "relations")


def test_derive_tree_refuses_evaluation(tmp_path):
    with pytest.raises(ValueError, match="evaluation"):
        derive_tree(tmp_path / "bench", tmp_path / "evaluation" / "relations")
