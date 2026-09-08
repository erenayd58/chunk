"""The Hybrid arm: structure first, semantics where the budget forces a cut.

The engine is :mod:`amsc.chunking.hybrid`. It is the one shipped method that
declares ``needs_embedder``, so the registry resolves a boundary embedder for
it and for nothing else.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..method import ChunkMethod, PartitionResult
from ._budget import budget_kwargs


def partition_hybrid(
    units,
    *,
    counter: Any,
    budget: Mapping[str, Any],
    boundary_embedder: Any = None,
    respect_semantic_roles: bool = False,
    **_ignored: Any,
) -> PartitionResult:
    from .. import hybrid

    result = hybrid.chunk_units(
        units, counter=counter, boundary_embedder=boundary_embedder,
        respect_semantic_roles=respect_semantic_roles, **budget_kwargs(budget),
    )
    return PartitionResult(result.chunks, dict(result.diagnostics))


HYBRID = ChunkMethod(
    key="hybrid",
    kind="hybrid_h1",
    label="Hybrid",
    summary="Yapıyı takip eder; bütçeyi aşan bölümlerde kesim yerini anlam benzerliğiyle seçer.",
    partition=partition_hybrid,
    order=20,
    chunk_infix="h-chunk",
    needs_embedder=True,
    arbitrated_cuts=True,
    benchmark_arm=True,
)
