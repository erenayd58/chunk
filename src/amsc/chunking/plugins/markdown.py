"""The Markdown arm: the size-first recursive splitter, declared.

The engine is :mod:`amsc.chunking.markdown` and is frozen benchmark code; this
is the declaration the registry reads. The engine is imported inside the
partition on purpose -- the Viewer builders, the console and the benchmark all
import the registry to learn a method's *name*, and none of them should pay
for a splitter to do it.

This is the one shipped method that declares :attr:`Capability.OFFSETS`: it
chunks a rendering rather than the units, so every row carries its character
range in that rendering and the chunk mapper can locate it arithmetically.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..contract import Capability
from ..method import ChunkMethod, PartitionResult


def partition_markdown(
    units,
    *,
    counter: Any,
    budget: Mapping[str, Any],
    chunk_size_tokens: int | None = None,
    chunk_overlap_tokens: int | None = None,
    **_ignored: Any,
) -> PartitionResult:
    from .. import markdown

    size = int(chunk_size_tokens if chunk_size_tokens is not None else markdown.CHUNK_SIZE_TOKENS)
    overlap = int(chunk_overlap_tokens if chunk_overlap_tokens is not None else markdown.CHUNK_OVERLAP_TOKENS)
    document = markdown.render_markdown(units)
    rows = markdown.chunk_units(
        units,
        counter=counter,
        chunk_size_tokens=size,
        chunk_overlap_tokens=overlap,
        hard_max_tokens=int(budget["hard_max_tokens"]),
    )
    return PartitionResult(
        rows,
        {
            "chunk_size_tokens": size,
            "chunk_overlap_tokens": overlap,
            "tuning_status": markdown.TUNING_STATUS,
        },
        dict(document.spans),
    )


MARKDOWN = ChunkMethod(
    key="markdown",
    kind="markdown_recursive",
    label="Markdown",
    summary="Metni sabit boyutta keser; bölüm yapısına bakmaz.",
    partition=partition_markdown,
    capabilities=[
        Capability.PAGES,
        Capability.HEADINGS,
        Capability.HIERARCHY,
        Capability.PROVENANCE,
        Capability.OFFSETS,
    ],
    order=10,
    chunk_infix="md-chunk",
    sized=True,
    benchmark_arm=True,
    # The sizes a live run uses: the frozen benchmark's, so a live Markdown
    # variant is that arm and not a lookalike.
    options={"chunk_size_tokens": 700, "chunk_overlap_tokens": 140},
)
