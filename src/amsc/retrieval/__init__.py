"""Retrieval: the frozen lexical and hybrid implementations, and their embedder.

:mod:`~amsc.retrieval.pipeline` is the deterministic BM25, the hybrid index and
RRF fusion that the frozen benchmarks measured and the console serves --
changing a formula here changes a published number.
:mod:`~amsc.retrieval.embeddings` is the retrieval-side embedder, deliberately
not the boundary one (:mod:`amsc.embedding`).
"""
