"""Adaptive Multi-Signal Semantic Chunking -- the library, by domain.

Importing this package costs nothing: there is no re-export here, so a
consumer that wants one thing imports that one thing and pays for its
dependencies only. The map:

=========================== ==================================================
:mod:`amsc.document`        the canonical document -- schema, file format,
                            token counting. The bottom of the graph.
:mod:`amsc.canonical`       PDF in, canonical document out, repairs included.
:mod:`amsc.chunking`        the chunking methods and the one registry that
                            names them; :mod:`amsc.chunking.adaptive` is the
                            frozen V1-V4 lineage.
:mod:`amsc.deep`            Deep Analysis: an orchestration over a baseline
                            partition, not a partition.
:mod:`amsc.quality`         how good is this parse, this boundary, these
                            chunks.
:mod:`amsc.tables`          a table as a retriever indexes it and a reader
                            sees it.
:mod:`amsc.embedding`       boundary embedding, and its cache.
:mod:`amsc.retrieval`       the frozen BM25/hybrid/RRF implementations and the
                            retrieval-side embedder.
:mod:`amsc.viewer`          the read model, the page built from it, and the
                            standalone demo server beside it.
:mod:`amsc.research`        maintained research and evaluation, off the
                            product path.
:mod:`amsc.providers`       the HTTP transport every model-consulting path
                            shares.
:mod:`amsc.surface`         which of the above a console may import, and why.
=========================== ==================================================

``amsc.cli`` is the ``amsc`` console script: ``validate`` and ``chunk`` over
the V1-V4 lineage.
"""

__all__: list[str] = []
