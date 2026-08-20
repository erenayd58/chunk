from __future__ import annotations

import numpy as np

from amsc.retrieval_benchmark import (
    _irrelevant_token_ratio,
    _minimum_evidence_cover,
)
from amsc.retrieval_pipeline import (
    DeterministicBM25,
    DeterministicHybridIndex,
    E5RetrievalEmbedder,
    RetrievalDocument,
)


class _Tokenizer:
    model_max_length = 20

    def __call__(self, text, *, add_special_tokens, truncation=False):
        assert truncation is False
        ids = list(range(len(text.split())))
        if add_special_tokens:
            ids = [100, *ids, 101]
        return {"input_ids": ids}

    def decode(self, ids):
        return " ".join(f"w{value}" for value in ids)


class _Model:
    def __init__(self):
        self.calls: list[list[str]] = []
        self.max_seq_length = 0

    def encode(self, texts, **kwargs):
        self.calls.append(list(texts))
        vectors = []
        for text in texts:
            if text.startswith("query: "):
                vectors.append([1.0, float(len(text))])
            else:
                vectors.append([2.0, float(len(text))])
        return np.asarray(vectors, dtype=np.float32)


def _doc(chunk_id: str, text: str, units: tuple[str, ...], tokens: int = 10):
    return RetrievalDocument(chunk_id, text, units, (1,), tokens)


def test_retrieval_cache_is_exact_text_and_role_separated(tmp_path) -> None:
    model = _Model()
    embedder = E5RetrievalEmbedder(
        model=model,
        tokenizer=_Tokenizer(),
        model_id="fake",
        query_prefix="query: ",
        document_prefix="passage: ",
        model_input_limit=20,
        batch_size=8,
        cache_dir=tmp_path,
        cache_queries=False,
    )

    _, query_stats = embedder.embed_queries(["same text", "same  text"])
    _, document_stats = embedder.embed_documents(["same text"])
    _, cached_stats = embedder.embed_documents(["same text"])

    assert query_stats.cache_misses == 2
    assert document_stats.cache_misses == 1
    assert cached_stats.cache_hits == 1
    assert len(model.calls) == 2
    assert model.calls[0] == ["query: same text", "query: same  text"]
    assert model.calls[1] == ["passage: same text"]


def test_bm25_unicode_tokenization_and_scores() -> None:
    bm25 = DeterministicBM25(
        ["Kredi notu ve ödeme", "sürdürülebilirlik raporu"], k1=1.5, b=0.75
    )
    scores = bm25.scores("KREDİ ödeme")

    assert DeterministicBM25.tokenize("İşletme'nin ÇSY'si") == ["işletme'nin", "çsy'si"]
    assert scores[0] > scores[1]


def test_rrf_is_deterministic_and_uses_both_rankings() -> None:
    documents = [_doc("a", "alpha", ("u1",)), _doc("b", "beta alpha", ("u2",))]
    index = DeterministicHybridIndex(
        documents=documents,
        document_embeddings=np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        bm25_k1=1.5,
        bm25_b=0.75,
        rrf_rank_constant=60,
        dense_weight=1.0,
        bm25_weight=1.0,
        candidate_pool_size=2,
    )

    first = index.search("beta", np.asarray([1.0, 0.0], dtype=np.float32), top_k=2)
    second = index.search("beta", np.asarray([1.0, 0.0], dtype=np.float32), top_k=2)

    assert first == second
    assert {hit.chunk_id for hit in first} == {"a", "b"}
    assert all(hit.dense_rank is not None and hit.bm25_rank is not None for hit in first)


def test_evidence_fragmentation_and_irrelevant_token_ratio() -> None:
    documents = [
        _doc("a", "", ("u1", "noise"), 10),
        _doc("b", "", ("u2",), 5),
        _doc("c", "", ("noise",), 20),
    ]
    evidence = {"u1", "u2"}

    assert _minimum_evidence_cover(evidence, documents) == 2
    ratio = _irrelevant_token_ratio(
        documents, evidence, {"u1": 4, "u2": 5, "noise": 20}
    )
    assert ratio == (35 - 9) / 35
