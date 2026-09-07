"""What a chunking method *is* -- the types a method module needs, and nothing else.

This module is a leaf on purpose: it imports no other ``amsc`` module, so a
chunker that imports it can itself be imported by the registry
(:mod:`amsc.methods`) at module level without a cycle. That is the whole
reason it is separate from the registry. A method module says

    from .chunk_method import ChunkMethod, PartitionResult

writes its partition, declares its :class:`ChunkMethod`, and is then listed
in ``amsc.methods._BUILTIN``, which imports it. The registry imports the
method; the method never imports the registry. :mod:`amsc.example_chunker`
is the copyable instance of that shape.

:mod:`amsc.methods` re-exports every name here, so existing callers that
read ``methods.ChunkMethod`` or ``methods.PartitionResult`` are unaffected.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

#: The engine kind of Deep Analysis, named here so the orchestration modules
#: and the registry entry cannot disagree about it.
DEEP_KIND = "deep_analysis"


@dataclass(frozen=True)
class PartitionResult:
    """What a partition returns: rows, and whatever it wants recorded.

    ``rows`` are chunk rows in the structural schema (``chunk_id``, ``text``,
    ``unit_ids``, ``token_count``, ``pages``, ``section_paths``, ``heading``,
    ``split_strategies``). ``diagnostics`` are counts and settings the
    benchmark writes into its summary; never content. ``spans`` are the
    rendered-document spans of a method that chunks a rendering rather than
    the units (Markdown), which the chunk mapper needs to find each unit.
    """

    rows: list[dict[str, Any]]
    diagnostics: dict[str, Any] = field(default_factory=dict)
    spans: Optional[dict[str, Any]] = None


Partition = Callable[..., PartitionResult]


@dataclass(frozen=True)
class ChunkMethod:
    """One chunking method, as every layer needs to know it."""

    #: The wire id: what a console sends, what the Viewer names the arm.
    key: str
    #: The engine kind: what a packaged manifest declares and the
    #: boundary-reason reader keys on. Two methods may not share one.
    kind: str
    #: The product name, one per method, everywhere.
    label: str
    #: One sentence for someone choosing it.
    summary: str
    #: ``units, counter, budget -> PartitionResult``; ``None`` for an
    #: orchestration such as Deep Analysis.
    partition: Optional[Partition] = None
    #: Needs a sentence-embedding model to run (Hybrid).
    needs_embedder: bool = False
    #: May consult a language model (Deep Analysis).
    uses_model: bool = False
    #: An orchestration over a baseline partition, not a partition itself.
    deep: bool = False
    #: The key of the partition a Deep run starts from and is compared to.
    baseline: Optional[str] = None
    #: Takes ``chunk_size_tokens`` / ``chunk_overlap_tokens`` instead of the
    #: shared min/target/soft/hard budget (Markdown).
    sized: bool = False
    #: A same-section budget cut may have been chosen by an arbitration
    #: rather than greedily; the relation deriver must not claim "greedy".
    arbitrated_cuts: bool = False
    #: One of the frozen chunk benchmark's compared arms.
    benchmark_arm: bool = False
    #: Default option values for a live (non-benchmark) run of the partition.
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key or not self.kind:
            raise ValueError("a chunking method needs both a key and a kind")
        if self.deep and self.partition is not None:
            raise ValueError(f"{self.key!r}: an orchestration is not a partition")
        if not self.deep and self.partition is None:
            raise ValueError(f"{self.key!r}: a method that is not deep needs a partition")
        if self.baseline is not None and not self.deep:
            raise ValueError(f"{self.key!r}: only a deep method has a baseline")
