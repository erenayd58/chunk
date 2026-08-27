"""Structure + Semantic Assist: a switch over the frozen chunkers, not a fork.

Everything here pins the reuse claims: Standard is byte-identical to the
structure-only arm, Enhanced is byte-identical to the hybrid arm, the assist is
consulted only where structure is genuinely ambiguous, and the API key can
never end up inside a generated artifact.
"""

from __future__ import annotations

import json

import pytest

from amsc.chunk_relations import derive_tree
from amsc.hybrid_chunker import chunk_units as hybrid_chunk_units
from amsc.semantic_assist import (
    OPENROUTER_API_KEY_ENV,
    ChunkingMode,
    OpenRouterEmbeddingProvider,
    QWEN_ADAPTER_STATUS,
    SemanticAssistConfig,
    chunk_with_mode,
    eligible_sections,
)
from amsc.structural_chunker import chunk_units as structural_chunk_units
from amsc.viewer_v2 import build_viewer

from conftest import StaticBoundaryEmbedder
from _chunk_fixtures import WhitespaceCounter, heading, unit, words

COUNTER = WhitespaceCounter()

CONFIG = SemanticAssistConfig(
    min_tokens=50,
    target_tokens=150,
    soft_max_tokens=160,
    hard_max_tokens=1000,
    respect_semantic_roles=False,
)

SMALL = words(30, "s")
#: Four 60-word paragraphs: two admissible cuts fit inside the greedy
#: window at each step, so the arbitration has a genuine choice to make.
BODIES = [words(60, "a"), words(60, "b"), words(60, "c"), words(60, "d")]


def corpus():
    """A small section that fits, then an oversized one that must split."""
    units = [heading("h-1", "KUCUK", 1)]
    units.append(unit("p-0", SMALL, order=2, section=("KUCUK",)))
    units.append(heading("h-2", "BUYUK", 3))
    for index, body in enumerate(BODIES, start=1):
        units.append(unit(f"p-{index}", body, order=index + 3, section=("BUYUK",)))
    return units


def provider(vectors=None):
    vectors = vectors or {
        BODIES[0]: [1.0, 0.0],  # the topic turns after the first paragraph
        BODIES[1]: [0.0, 1.0],
        BODIES[2]: [0.0, 1.0],
        BODIES[3]: [0.0, 1.0],
    }
    return StaticBoundaryEmbedder(vectors)


# --- mode equivalence (reuse regression) ------------------------------------


def test_standard_mode_is_byte_identical_to_structure_only():
    result = chunk_with_mode(corpus(), counter=COUNTER, config=CONFIG)

    expected = structural_chunk_units(
        corpus(),
        counter=COUNTER,
        min_tokens=50,
        target_tokens=150,
        soft_max_tokens=160,
        hard_max_tokens=1000,
        respect_semantic_roles=False,
    )
    assert result.chunks == expected
    assert result.diagnostics["semantic_assist"] is False


def test_enhanced_mode_is_byte_identical_to_the_hybrid_arm():
    config = SemanticAssistConfig(**{**CONFIG.__dict__, "mode": ChunkingMode.SEMANTIC_ASSIST})
    assist = chunk_with_mode(
        corpus(), counter=COUNTER, config=config, provider=provider()
    )

    expected = hybrid_chunk_units(
        corpus(),
        counter=COUNTER,
        boundary_embedder=provider(),
        arbitrate=True,
        min_tokens=50,
        target_tokens=150,
        soft_max_tokens=160,
        hard_max_tokens=1000,
        respect_semantic_roles=False,
    )
    assert assist.chunks == expected.chunks
    assert assist.diagnostics["semantic_assist"] is True
    assert assist.diagnostics["arbitrated_boundary_count"] == expected.diagnostics[
        "arbitrated_boundary_count"
    ]


def test_the_semantic_choice_actually_differs_from_greedy_when_shifts_say_so():
    """Reused arbitration regression: argmax picks the b|c boundary."""
    config = SemanticAssistConfig(**{**CONFIG.__dict__, "mode": ChunkingMode.SEMANTIC_ASSIST})
    result = chunk_with_mode(
        corpus(), counter=COUNTER, config=config, provider=provider()
    )

    assert result.diagnostics["arbitration_changed_boundary_count"] >= 1
    big = [c for c in result.chunks if c["heading"] == "BUYUK"]
    # Greedy would take [p-1, p-2]; the argmax cuts where the topic turns.
    assert big[0]["unit_ids"] == ["p-1"]
    assert big[1]["unit_ids"] == ["p-2", "p-3"]

    standard = chunk_with_mode(corpus(), counter=COUNTER, config=CONFIG)
    greedy_big = [c for c in standard.chunks if c["heading"] == "BUYUK"]
    assert greedy_big[0]["unit_ids"] == ["p-1", "p-2"]


# --- eligibility ------------------------------------------------------------


def test_assist_is_consulted_only_for_ambiguous_oversized_sections():
    spy = provider()
    config = SemanticAssistConfig(**{**CONFIG.__dict__, "mode": ChunkingMode.SEMANTIC_ASSIST})
    chunk_with_mode(corpus(), counter=COUNTER, config=config, provider=spy)

    embedded = {text for call in spy.calls for text in call}
    assert embedded == set(BODIES)
    assert SMALL not in embedded  # the section that fits is never embedded


def test_standard_mode_never_touches_the_provider():
    spy = provider()
    chunk_with_mode(corpus(), counter=COUNTER, config=CONFIG, provider=spy)
    assert spy.calls == []


def test_eligible_sections_names_the_ambiguity_without_an_embedder():
    records = eligible_sections(corpus(), counter=COUNTER, config=CONFIG)

    assert [record["heading"] for record in records] == ["BUYUK"]
    assert records[0]["ambiguous_boundaries"] >= 1
    assert records[0]["admissible_candidates"] >= 2
    assert records[0]["greedy_fallback"] is False


def test_enhanced_mode_without_a_provider_is_an_error():
    config = SemanticAssistConfig(**{**CONFIG.__dict__, "mode": ChunkingMode.SEMANTIC_ASSIST})
    with pytest.raises(ValueError, match="needs an embedding provider"):
        chunk_with_mode(corpus(), counter=COUNTER, config=config)


# --- the adapter and the key ------------------------------------------------


def test_the_adapter_is_marked_not_verified():
    assert OpenRouterEmbeddingProvider.status == QWEN_ADAPTER_STATUS
    assert "not_verified" in QWEN_ADAPTER_STATUS


def test_a_missing_key_is_a_loud_error(monkeypatch):
    monkeypatch.delenv(OPENROUTER_API_KEY_ENV, raising=False)
    adapter = OpenRouterEmbeddingProvider()
    with pytest.raises(RuntimeError, match=OPENROUTER_API_KEY_ENV):
        adapter.embed_units(["metin"])


def test_the_key_never_reaches_generated_artifacts(monkeypatch, tmp_path):
    """Build every artifact this phase produces with the key set; grep it."""
    sentinel = "sk-or-SENTINEL-NEVER-PERSIST"
    monkeypatch.setenv(OPENROUTER_API_KEY_ENV, sentinel)

    from test_viewer_v2 import make_tree

    tree = make_tree(tmp_path)
    viewer = tmp_path / "out" / "index.html"
    build_viewer({"doc": tree}, viewer, root=tmp_path)
    derive_tree(tree, tmp_path / "relations")

    produced = [viewer, *sorted((tmp_path / "relations").glob("*"))]
    assert produced
    for path in produced:
        assert sentinel not in path.read_text(encoding="utf-8"), path
