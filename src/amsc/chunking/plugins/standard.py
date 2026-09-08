"""The Standard arm: structure-first chunking, declared.

The engine is :mod:`amsc.chunking.structural` -- frozen benchmark code, imported
inside the partition so that learning this method's name costs nothing.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..method import ChunkMethod, PartitionResult
from ._budget import budget_kwargs


def partition_standard(
    units,
    *,
    counter: Any,
    budget: Mapping[str, Any],
    respect_semantic_roles: bool = False,
    **_ignored: Any,
) -> PartitionResult:
    from .. import structural

    rows = structural.chunk_units(
        units, counter=counter, respect_semantic_roles=respect_semantic_roles,
        **budget_kwargs(budget),
    )
    return PartitionResult(rows, {"respect_semantic_roles": respect_semantic_roles})


STANDARD = ChunkMethod(
    key="structure-only",
    kind="structure_first",
    label="Standard",
    summary="Dokümanın başlık yapısını takip eder; yalnız çok büyüyen bölümler bölünür.",
    partition=partition_standard,
    order=30,
    chunk_infix="s-chunk",
    benchmark_arm=True,
)
