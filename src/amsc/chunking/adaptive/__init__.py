"""The V1-V4 adaptive multi-signal semantic chunker -- the original PoC.

Versions are cumulative and each adds exactly one algorithmic difference:
V1 fixed threshold, V2 hierarchical adaptive threshold, V3 multi-scale shift,
V4 threshold-relative selection with soft structural support and semantic-safe
merge. V1-V3 share :mod:`~amsc.chunking.adaptive.v1_v3`; **V4 has its own
orchestration** (:mod:`~amsc.chunking.adaptive.v4`) precisely so that V4
conditionals never leak into the V1-V3 facade. Keep it that way.

These chunkers are frozen and byte-pinned by ``tests/integration``. They are
not in :mod:`amsc.chunking.registry`: the registry is the product method
catalogue, and this lineage is reached through ``V4Chunker`` and the ``amsc``
console script instead.
"""
