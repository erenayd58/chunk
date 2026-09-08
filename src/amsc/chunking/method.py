"""What a chunking method *is* -- the types a method module needs, and nothing else.

This module is a leaf on purpose: it imports no other ``amsc`` module, so a
chunker that imports it can itself be imported by the registry
(:mod:`amsc.chunking.registry`) at module level without a cycle. That is the whole
reason it is separate from the registry. A method module says

    from .contract import Capability, Chunk, chunker

writes its partition, declares its :class:`ChunkMethod` (usually through the
:func:`amsc.chunking.contract.chunker` decorator, which builds one), and is
discovered by dropping the file into ``amsc/chunking/plugins/``. The registry
imports the plugin; the plugin never imports the registry.
:mod:`amsc.chunking.example` is the copyable instance of that shape.

:mod:`amsc.chunking.registry` re-exports every name here, so existing callers that
read ``registry.ChunkMethod`` or ``registry.PartitionResult`` are unaffected.

Three things live here rather than in :mod:`amsc.chunking.contract`, because a
:class:`ChunkMethod` has to be able to name them and the contract module has to
be able to build a :class:`ChunkMethod`: the engine kind of Deep Analysis, the
:class:`Capability` vocabulary, and the method record itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Iterable, Optional

#: The engine kind of Deep Analysis, named here so the orchestration modules
#: and the registry entry cannot disagree about it.
DEEP_KIND = "deep_analysis"

#: Where a method sorts in the one list every screen reads, when it says
#: nothing. The four shipped methods claim 10..40 so a new one lands after
#: them; ties break on the key, so the order is a fact rather than an
#: accident of which file the plugin loader happened to import first.
DEFAULT_ORDER = 100


class Capability(StrEnum):
    """An optional thing a method's rows carry, declared rather than implied.

    The four core fields (``chunk_id``, ``text``, ``unit_ids``,
    ``token_count``) are the whole *required* contract -- they are exactly
    what the downstream consumers cannot do without. Everything else is one
    of these, and a method's rows carry it only when the method says so.
    Two consequences, both deliberate:

    * a method that declares nothing extra still works everywhere. Every
      consumer of the optional fields already reads them defensively, and
      ``tests/unit/chunking/test_chunk_contract.py`` holds them to it, so a
      chunker is never obliged to invent a field it has no opinion about;
    * a method that *does* declare one gets it derived for free. The
      framework fills ``pages``, ``section_paths`` and the rest from the
      chunk's provenance -- see :func:`amsc.chunking.contract.normalize` --
      so declaring a capability is a statement about the output, not work.

    ``CUSTOM_METADATA`` is the escape hatch: with it declared, a method may
    put whatever else it computed on the row and it is carried through
    untouched. Without it, an unexpected field is an error at the contract
    boundary rather than a surprise three consumers downstream.
    """

    #: Rows carry ``pages``: the source pages the chunk's content came from.
    PAGES = "pages"
    #: Rows carry ``heading``: the heading text leading the chunk, or ``None``.
    HEADINGS = "headings"
    #: Rows carry ``section_paths``: the section paths the chunk spans.
    HIERARCHY = "hierarchy"
    #: Rows carry ``split_strategies``: how the units in it were cut.
    PROVENANCE = "provenance"
    #: Rows carry ``char_start``/``char_end`` in a rendered document, and the
    #: method is handed that rendering to chunk. This is what buys arithmetic
    #: provenance instead of a text search.
    OFFSETS = "offsets"
    #: Rows carry ``scores``: whatever numbers the method wants to publish
    #: about a chunk (a boundary strength, a cohesion). Never comparable
    #: across methods, and nothing rescales them.
    SEMANTIC_SCORES = "semantic_scores"
    #: Rows may carry method-specific fields, preserved verbatim.
    CUSTOM_METADATA = "custom_metadata"


#: What a method gets when it says nothing: the four optional fields the
#: shipped structural family has always emitted. A new chunker written with no
#: thought about capabilities therefore produces exactly the rows the Viewer
#: and the console have always read.
DEFAULT_CAPABILITIES: frozenset[Capability] = frozenset({
    Capability.PAGES,
    Capability.HEADINGS,
    Capability.HIERARCHY,
    Capability.PROVENANCE,
})


def _capabilities(declared: Iterable[Any]) -> frozenset[Capability]:
    """Coerce whatever was written down to :class:`Capability` members.

    A plugin may write ``capabilities=["pages", Capability.HEADINGS]``; both
    spellings mean the same thing and a typo fails here, at the declaration,
    naming the vocabulary.
    """
    out: set[Capability] = set()
    for item in declared:
        try:
            out.add(Capability(item))
        except ValueError:
            raise ValueError(
                f"unknown chunker capability {item!r}; the vocabulary is "
                + ", ".join(repr(c.value) for c in Capability)
            ) from None
    return frozenset(out)


@dataclass(frozen=True)
class PartitionResult:
    """What a partition returns: rows, and whatever it wants recorded.

    ``rows`` are chunk rows in the schema :mod:`amsc.chunking.contract`
    defines and validates -- the four core fields plus whatever the method's
    capabilities declare. ``diagnostics`` are counts and settings the
    benchmark writes into its summary; never content. ``spans`` are the
    rendered-document spans of a method that chunks a rendering rather than
    the units (Markdown), which the chunk mapper needs to find each unit.

    A plugin written against the contract returns
    :class:`amsc.chunking.contract.Chunk` objects and never builds one of
    these; :func:`amsc.chunking.registry.partition` normalises them into it,
    so every consumer sees one shape whichever way the method was written.
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
    #: ``units, **options -> chunks``; ``None`` for an orchestration such as
    #: Deep Analysis. The framework passes only the options the callable
    #: actually names, so a partition declares what it wants and no more.
    partition: Optional[Partition] = None
    #: What this method's rows carry beyond the four core fields.
    capabilities: frozenset[Capability] = DEFAULT_CAPABILITIES
    #: Where this method sorts in the one order every screen reads.
    order: int = DEFAULT_ORDER
    #: The chunk id infix, so a row says which method wrote it. Defaults to
    #: ``<key>-chunk``; only a framework-derived id uses it.
    chunk_infix: Optional[str] = None
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
        object.__setattr__(self, "capabilities", _capabilities(self.capabilities))

    def can(self, capability: Capability) -> bool:
        """Whether this method's rows carry that optional field."""
        return capability in self.capabilities

    @property
    def infix(self) -> str:
        """The chunk id infix a framework-derived ``chunk_id`` is built from."""
        return self.chunk_infix or f"{self.key}-chunk"
