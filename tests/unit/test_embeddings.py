from __future__ import annotations

import numpy as np

from amsc.cache import FileEmbeddingCache
from amsc.embeddings import (
    CachedSemanticBoundaryEmbedder,
    RetrievalEmbedder,
    SemanticBoundaryEmbedder,
    SentenceTransformerBoundaryEmbedder,
)
from conftest import FakeModelTokenizer, RecordingBackend


def make_embedder(limit: int = 8):
    backend = RecordingBackend()
    embedder = SentenceTransformerBoundaryEmbedder(
        backend=backend,
        tokenizer=FakeModelTokenizer(limit),
        model_id="test:e5",
    )
    return embedder, backend


def test_boundary_and_retrieval_interfaces_are_distinct() -> None:
    embedder, _ = make_embedder()
    assert isinstance(embedder, SemanticBoundaryEmbedder)
    assert not isinstance(embedder, RetrievalEmbedder)


def test_prefix_and_model_limit_are_explicit() -> None:
    embedder, backend = make_embedder(limit=8)
    batch = embedder.embed_units(["one two"])
    assert embedder.prefix_policy == "symmetric_query"
    assert embedder.model_input_limit == 8
    assert backend.calls == [(["query: one two"], False)]
    assert batch.provenance[0].prefix == "query: "


def test_existing_training_prefix_is_not_duplicated() -> None:
    embedder, backend = make_embedder(limit=8)
    embedder.embed_units(["query: one two"])
    assert backend.calls == [(["query: one two"], False)]


def test_long_input_is_fragmented_without_truncation() -> None:
    embedder, backend = make_embedder(limit=6)
    batch = embedder.embed_units(
        ["One two three. Four five six. Seven eight nine."]
    )
    flattened = [text for call, truncation in backend.calls for text in call]
    assert len(flattened) >= 3
    assert all(text.startswith("query: ") for text in flattened)
    assert all(truncation is False for _, truncation in backend.calls)
    assert batch.provenance[0].semantic_fragment_count >= 3
    assert np.isclose(np.linalg.norm(batch.vectors[0]), 1.0)


def test_single_oversized_sentence_uses_model_token_windows() -> None:
    embedder, backend = make_embedder(limit=6)
    batch = embedder.embed_units(["one two three four five six seven eight"])
    assert batch.provenance[0].semantic_fragment_count > 1
    assert all(not truncation for _, truncation in backend.calls)


def test_override_may_not_exceed_native_limit() -> None:
    backend = RecordingBackend()
    try:
        SentenceTransformerBoundaryEmbedder(
            backend=backend,
            tokenizer=FakeModelTokenizer(8),
            model_id="test",
            max_input_tokens_override=9,
        )
    except ValueError as exc:
        assert "cannot exceed" in str(exc)
    else:
        raise AssertionError("Expected model input override validation")


def test_file_cache_prevents_second_backend_call(tmp_path) -> None:
    embedder, backend = make_embedder(limit=8)
    cached = CachedSemanticBoundaryEmbedder(
        embedder, FileEmbeddingCache(tmp_path / "cache")
    )
    first = cached.embed_units(["one two"])
    second = cached.embed_units(["one two"])
    assert len(backend.calls) == 1
    assert first.provenance[0].cache_hit is False
    assert second.provenance[0].cache_hit is True
    assert np.allclose(first.vectors, second.vectors)


def test_cache_namespace_changes_with_prefix() -> None:
    backend = RecordingBackend()
    tokenizer = FakeModelTokenizer(8)
    first = SentenceTransformerBoundaryEmbedder(
        backend=backend, tokenizer=tokenizer, model_id="m", prefix="query: "
    )
    second = SentenceTransformerBoundaryEmbedder(
        backend=backend, tokenizer=tokenizer, model_id="m", prefix="custom: "
    )
    assert first.cache_namespace != second.cache_namespace


def test_cache_key_preserves_exact_semantic_whitespace(tmp_path) -> None:
    embedder, backend = make_embedder(limit=8)
    cached = CachedSemanticBoundaryEmbedder(
        embedder, FileEmbeddingCache(tmp_path / "cache")
    )

    cached.embed_units(["one two"])
    cached.embed_units(["one  two"])
    cached.embed_units(["one\ntwo"])

    assert len(backend.calls) == 3
