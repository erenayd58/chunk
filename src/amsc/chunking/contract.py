"""The chunk contract: what a chunker must say, and what the framework derives.

Before this module the contract existed, but nowhere in particular. A chunker
had to produce a dict with eight keys because :mod:`amsc.viewer.corpus` read
three of them positionally, :mod:`amsc.chunking.relations` read two more,
``chat_rag``'s structural chunker read four with ``row[...]`` and the rest with
``row.get(...)``, and the only written statement of the whole shape was a
docstring. Nothing checked it. A new chunker that forgot ``pages`` did not
fail -- it produced a Viewer with empty page badges and structural metrics
quietly computed over nothing.

So the requirements are collected here, once, and split into three honest
groups.

**Core -- what a chunker must give.** Four fields, and they are exactly the
four that every downstream consumer reads with ``row[...]``:

``chunk_id``, ``text``, ``unit_ids``, ``token_count``.

Of those, a chunker supplies **one and a half**: the text, and the provenance
that says where the text came from -- either the ``unit_ids`` it packed, or a
``span`` into a rendering the framework handed it. The other fields are
derived. Provenance is required and never guessed: a chunk that cannot say
where its text came from is a chunk nothing downstream can highlight, page,
score or cite, and inferring it by searching for the text would attach the
wrong paragraph the first time a document repeats a sentence.

**Derived -- what the framework works out.** ``chunk_id`` (from the document
and the method's infix), ``token_count`` (from the shared counter),
``unit_ids`` (arithmetic, from the span), and every capability field below.
The derivation from a span is the intersection of character ranges -- the same
arithmetic :func:`amsc.chunking.mapping.map_chunks` calls its ``offset`` rung,
over the same spans the renderer recorded. There is no text search anywhere in
this module.

**Capabilities -- what a method opts into.** :class:`Capability` is the
vocabulary; a method declares what its rows carry and the framework fills it
in. Declaring is not work: ``pages``, ``section_paths``, ``heading`` and
``split_strategies`` are all derived from the provenance the chunk already
gave. A method that declares nothing extra emits the four core fields and
works everywhere, because every consumer of an optional field already reads it
defensively.

Anything else a method computed rides along under
:attr:`Chunk.extra`, preserved verbatim, once the method declares
``CUSTOM_METADATA``. That is the difference between an extension and a leak:
the row still says what it is.

Errors are :class:`ContractError`, raised at
:func:`amsc.chunking.registry.partition` -- one boundary, naming the method,
the chunk and what was wrong, instead of a ``KeyError`` from whichever
consumer happened to read the row first.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional, Protocol, Sequence

from .method import (
    DEFAULT_CAPABILITIES,
    DEFAULT_ORDER,
    Capability,
    ChunkMethod,
    PartitionResult,
)
from ..document.models import RawDocumentUnit, UnitType

__all__ = [
    "Capability", "Chunk", "ChunkResult", "ContractError", "Rendering",
    "chunker", "normalize", "validate_rows",
    "CORE_FIELDS", "CAPABILITY_FIELDS", "fields_of",
]


#: The fields every row carries, whatever the method. These are the four the
#: consumers read with ``row[...]``; nothing else is ever required.
CORE_FIELDS: tuple[str, ...] = ("chunk_id", "text", "unit_ids", "token_count")

#: Which row fields each capability puts on the row. A field appears if and
#: only if its capability is declared, which is what makes the declaration
#: worth reading.
CAPABILITY_FIELDS: Mapping[Capability, tuple[str, ...]] = {
    Capability.PAGES: ("pages",),
    Capability.HEADINGS: ("heading",),
    Capability.HIERARCHY: ("section_paths",),
    Capability.PROVENANCE: ("split_strategies",),
    Capability.OFFSETS: ("char_start", "char_end"),
    Capability.SEMANTIC_SCORES: ("scores",),
    Capability.CUSTOM_METADATA: (),
}

#: Fragment ids (``t-00186#f2``) say the unit was cut; the strategy vocabulary
#: below is what a derived ``split_strategies`` uses when the method itself
#: has no opinion. ``whole`` is the structural family's own word for an uncut
#: unit, kept so the two agree.
STRATEGY_WHOLE = "whole"
STRATEGY_PARTIAL = "partial"

_FRAGMENT = "#f"


class ContractError(ValueError):
    """A chunker's output does not satisfy the contract.

    Raised at the boundary -- when a partition returns -- so the message names
    the method and the chunk, rather than surfacing as a ``KeyError`` inside
    whichever consumer read the row first.
    """


class Rendering(Protocol):
    """A rendered document plus every unit's character range inside it.

    Structural, not nominal: :class:`amsc.chunking.markdown.RenderedDocument`
    satisfies it, and so would another renderer, without this module importing
    an engine.
    """

    text: str
    spans: Mapping[str, tuple[int, int]]

    def units_in(self, start: int, end: int) -> list[str]:
        ...


def fields_of(method: ChunkMethod) -> frozenset[str]:
    """Every row field this method's declaration allows."""
    fields = set(CORE_FIELDS)
    for capability in method.capabilities:
        fields.update(CAPABILITY_FIELDS.get(capability, ()))
    return frozenset(fields)


# ---------------------------------------------------------------------------
# what a chunker returns
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Chunk:
    """One chunk, as its author sees it: the text, and where it came from.

    Exactly one provenance has to be given.

    ``unit_ids``
        The canonical units this chunk packed, in reading order. A fragment id
        (``t-00186#f2``) is kept as written -- the framework reads the unit it
        belongs to and records that the unit was cut.
    ``span``
        A ``(start, end)`` character range in the rendering the framework
        handed the method (see :class:`Capability.OFFSETS`). The units it
        covers are worked out arithmetically from the renderer's own spans.

    Everything below is optional, and supplying one requires the matching
    capability -- otherwise the field would appear on rows the method
    declared it does not produce. Leaving one out is not a gap: the framework
    derives it from the provenance.
    """

    text: str
    unit_ids: Optional[Sequence[str]] = None
    span: Optional[tuple[int, int]] = None
    #: The heading leading this chunk. Derived from the heading units the
    #: chunk covers when the method says nothing.
    heading: Optional[str] = None
    #: The source pages. Derived from the content units.
    pages: Optional[Sequence[int]] = None
    #: The section paths the chunk spans. Derived from the content units.
    section_paths: Optional[Sequence[Sequence[str]]] = None
    #: How the units in this chunk were cut. Derived from the provenance:
    #: a fragment id, or a span that covers only part of a unit, is partial.
    split_strategies: Optional[Sequence[str]] = None
    #: Whatever numbers the method wants to publish about this chunk.
    scores: Optional[Mapping[str, Any]] = None
    #: Method-specific fields, carried onto the row verbatim.
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def of(cls, value: Any) -> "Chunk":
        """A :class:`Chunk` from a chunk, a mapping, or ``(text, unit_ids)``.

        The mapping form is what lets a method that already builds dicts move
        onto the contract a step at a time: unknown keys become ``extra``,
        which is where they were going anyway.
        """
        if isinstance(value, cls):
            return value
        if isinstance(value, MappingABC):
            derived = sorted({"chunk_id", "token_count"} & set(value))
            if derived:
                raise ContractError(
                    f"a chunk carries {derived}, which the framework derives; "
                    "give the text and the provenance and let it"
                )
            known = {f for f in cls.__dataclass_fields__ if f != "extra"}
            body = {k: v for k, v in value.items() if k in known}
            extra = dict(value.get("extra") or {})
            extra.update({k: v for k, v in value.items() if k not in known and k != "extra"})
            span = body.get("span")
            if span is not None:
                body["span"] = (int(span[0]), int(span[1]))
            return cls(**body, extra=extra)
        if isinstance(value, (tuple, list)) and len(value) == 2:
            return cls(text=str(value[0]), unit_ids=list(value[1]))
        raise ContractError(
            f"a chunker returned {type(value).__name__}; expected a Chunk, a "
            "mapping, or a (text, unit_ids) pair"
        )


@dataclass(frozen=True)
class ChunkResult:
    """Chunks plus whatever the method wants recorded about the run.

    A method that has nothing to record returns the chunks alone; the
    framework accepts either.
    """

    chunks: Sequence[Chunk]
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# declaring a method
# ---------------------------------------------------------------------------


def chunker(
    *,
    key: str,
    label: str,
    summary: str = "",
    kind: Optional[str] = None,
    capabilities: Iterable[Any] = DEFAULT_CAPABILITIES,
    order: int = DEFAULT_ORDER,
    chunk_infix: Optional[str] = None,
    **method_fields: Any,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Declare a chunking method on the function that implements it.

    ::

        @chunker(key="semantic-v2", label="Semantic V2",
                 capabilities=[Capability.PAGES, Capability.HEADINGS])
        def semantic_v2(units, *, counter, budget, **options):
            ...
            return [Chunk(text=..., unit_ids=[...]), ...]

    ``kind`` -- the engine kind a packaged manifest declares -- defaults to the
    key with its dashes turned into underscores, because a method that has no
    opinion about it should not have to invent one. Any other
    :class:`~amsc.chunking.method.ChunkMethod` field may be passed through
    (``needs_embedder``, ``sized``, ``options``, ...).

    The decorator returns the function, so it stays directly callable and
    testable; the method it built hangs off it as ``chunk_method``, which is
    what :mod:`amsc.chunking.discovery` looks for.
    """

    def declare(partition: Callable[..., Any]) -> Callable[..., Any]:
        method = ChunkMethod(
            key=key,
            kind=kind or key.replace("-", "_"),
            label=label,
            summary=summary,
            partition=partition,
            capabilities=frozenset(capabilities),
            order=order,
            chunk_infix=chunk_infix,
            **method_fields,
        )
        partition.chunk_method = method  # type: ignore[attr-defined]
        return partition

    return declare


# ---------------------------------------------------------------------------
# framework-side derivation
# ---------------------------------------------------------------------------


def _base(unit_id: str) -> str:
    """``t-00186#f2`` -> ``t-00186``. Local so the contract stays a leaf."""
    head, sep, tail = str(unit_id).partition(_FRAGMENT)
    return head if sep and tail.isdigit() else str(unit_id)


def _ordered_unique_paths(units: Sequence[RawDocumentUnit]) -> list[list[str]]:
    paths: list[list[str]] = []
    for unit in units:
        path = list(unit.section_path or ())
        if path and path not in paths:
            paths.append(path)
    return paths


def _covered_by_span(
    span: tuple[int, int],
    document: Rendering,
    units_by_id: Mapping[str, RawDocumentUnit],
    where: str,
) -> tuple[list[RawDocumentUnit], set[str]]:
    """The units a character range covers, and which of them it only partly covers.

    Arithmetic over the renderer's own spans -- the ``offset`` rung of
    :func:`amsc.chunking.mapping.map_chunks`, and the reason a document that
    repeats a paragraph still attributes each chunk to the right occurrence.
    """
    start, end = span
    if start < 0 or end <= start:
        raise ContractError(f"{where}: span {span!r} is not a forward character range")
    if end > len(document.text):
        raise ContractError(
            f"{where}: span {span!r} runs past the {len(document.text)}-character rendering"
        )
    covered: list[RawDocumentUnit] = []
    partial: set[str] = set()
    for unit_id in document.units_in(start, end):
        unit = units_by_id.get(unit_id)
        if unit is None:                        # a span for a unit not in this corpus
            raise ContractError(f"{where}: the rendering spans unknown unit {unit_id!r}")
        covered.append(unit)
        unit_start, unit_end = document.spans[unit_id]
        if unit_start < start or unit_end > end:
            partial.add(unit_id)
    return covered, partial


def _covered_by_ids(
    unit_ids: Sequence[str],
    units_by_id: Mapping[str, RawDocumentUnit],
    where: str,
) -> tuple[list[RawDocumentUnit], set[str]]:
    covered: list[RawDocumentUnit] = []
    partial: set[str] = set()
    for unit_id in unit_ids:
        unit = units_by_id.get(_base(unit_id))
        if unit is None:
            raise ContractError(
                f"{where}: claims unit {unit_id!r}, which is not in the canonical corpus"
            )
        if unit not in covered:
            covered.append(unit)
        if _base(unit_id) != str(unit_id):
            partial.add(unit.unit_id)
    return covered, partial


def _row(
    chunk: Chunk,
    index: int,
    *,
    method: ChunkMethod,
    document_id: str,
    units_by_id: Mapping[str, RawDocumentUnit],
    counter: Any,
    document: Optional[Rendering],
) -> dict[str, Any]:
    where = f"{method.key!r} chunk {index}"
    if not isinstance(chunk.text, str) or not chunk.text:
        raise ContractError(f"{where}: a chunk needs text")
    if (chunk.unit_ids is None) == (chunk.span is None):
        raise ContractError(
            f"{where}: give exactly one provenance -- the unit_ids the chunk "
            "packed, or a span into the rendering. Text alone cannot be "
            "attributed to a source."
        )

    if chunk.span is not None:
        if not method.can(Capability.OFFSETS):
            raise ContractError(
                f"{where}: located by span, so the method must declare "
                f"Capability.OFFSETS (it declares "
                f"{sorted(c.value for c in method.capabilities)})"
            )
        if document is None:
            raise ContractError(
                f"{where}: located by span, but the partition was handed no "
                "rendering to measure it against -- name ``document`` in its "
                "signature and chunk ``document.text``"
            )
        covered, partial = _covered_by_span(chunk.span, document, units_by_id, where)
        declared_ids = [
            unit.unit_id for unit in covered if unit.type != UnitType.HEADING
        ]
    else:
        covered, partial = _covered_by_ids(list(chunk.unit_ids or ()), units_by_id, where)
        declared_ids = [str(unit_id) for unit_id in (chunk.unit_ids or ())]

    content = [unit for unit in covered if unit.type != UnitType.HEADING]
    headings = [unit for unit in covered if unit.type == UnitType.HEADING]

    row: dict[str, Any] = {
        "chunk_id": f"{document_id}:{method.infix}-{index:04d}",
        "text": chunk.text,
        "unit_ids": declared_ids,
        "token_count": int(counter.count(chunk.text)),
    }

    if method.can(Capability.PAGES):
        row["pages"] = (
            sorted({int(page) for page in chunk.pages})
            if chunk.pages is not None
            else sorted({u.source.page for u in content if u.source.page is not None})
        )
    elif chunk.pages is not None:
        raise ContractError(f"{where}: gave pages without declaring Capability.PAGES")

    if method.can(Capability.HIERARCHY):
        row["section_paths"] = (
            [list(path) for path in chunk.section_paths]
            if chunk.section_paths is not None
            else _ordered_unique_paths(content)
        )
    elif chunk.section_paths is not None:
        raise ContractError(f"{where}: gave section_paths without declaring Capability.HIERARCHY")

    if method.can(Capability.HEADINGS):
        row["heading"] = (
            chunk.heading
            if chunk.heading is not None
            else ("\n".join(unit.text for unit in headings) or None)
        )
    elif chunk.heading is not None:
        raise ContractError(f"{where}: gave a heading without declaring Capability.HEADINGS")

    if method.can(Capability.PROVENANCE):
        if chunk.split_strategies is not None:
            row["split_strategies"] = sorted({str(s) for s in chunk.split_strategies})
        else:
            row["split_strategies"] = sorted(
                {STRATEGY_PARTIAL if unit.unit_id in partial else STRATEGY_WHOLE
                 for unit in covered}
            ) or [STRATEGY_WHOLE]
    elif chunk.split_strategies is not None:
        raise ContractError(f"{where}: gave split_strategies without declaring Capability.PROVENANCE")

    if method.can(Capability.OFFSETS) and chunk.span is not None:
        row["char_start"], row["char_end"] = int(chunk.span[0]), int(chunk.span[1])

    if method.can(Capability.SEMANTIC_SCORES):
        row["scores"] = dict(chunk.scores or {})
    elif chunk.scores is not None:
        raise ContractError(f"{where}: gave scores without declaring Capability.SEMANTIC_SCORES")

    if chunk.extra:
        if not method.can(Capability.CUSTOM_METADATA):
            raise ContractError(
                f"{where}: carries method-specific fields "
                f"{sorted(chunk.extra)}, so the method must declare "
                "Capability.CUSTOM_METADATA"
            )
        clash = sorted(set(chunk.extra) & (set(CORE_FIELDS) | set(row)))
        if clash:
            raise ContractError(
                f"{where}: method-specific fields {clash} would overwrite "
                "contract fields; name them something else"
            )
        row.update(chunk.extra)

    return row


def normalize(
    produced: Any,
    *,
    method: ChunkMethod,
    units: Sequence[RawDocumentUnit],
    counter: Any,
    document: Optional[Rendering] = None,
) -> PartitionResult:
    """Turn whatever a partition returned into validated rows.

    A partition written before the contract returns a
    :class:`~amsc.chunking.method.PartitionResult` and is passed through --
    validated, never rewritten, because those are the frozen engines and their
    rows are a finished experiment's output. A partition written against the
    contract returns :class:`Chunk` objects (optionally wrapped in a
    :class:`ChunkResult`) and its rows are derived here.

    Either way the caller gets one shape, so no consumer has to know which
    kind of method produced it.
    """
    if isinstance(produced, PartitionResult):
        validate_rows(produced.rows, method=method)
        return produced

    if isinstance(produced, ChunkResult):
        chunks, diagnostics = produced.chunks, dict(produced.diagnostics)
    elif isinstance(produced, (SequenceABC, list, tuple)) and not isinstance(produced, (str, bytes)):
        chunks, diagnostics = list(produced), {}
    elif produced is None:
        chunks, diagnostics = [], {}
    else:
        try:
            chunks, diagnostics = list(produced), {}
        except TypeError:
            raise ContractError(
                f"{method.key!r} returned {type(produced).__name__}; a partition "
                "returns Chunk objects, a ChunkResult, or a PartitionResult"
            ) from None

    document_id = units[0].document_id if units else ""
    units_by_id = {unit.unit_id: unit for unit in units}
    rows = [
        _row(
            Chunk.of(item),
            index,
            method=method,
            document_id=document_id,
            units_by_id=units_by_id,
            counter=counter,
            document=document,
        )
        for index, item in enumerate(chunks, start=1)
    ]
    validate_rows(rows, method=method)
    spans = dict(document.spans) if document is not None else None
    return PartitionResult(rows, diagnostics, spans)


# ---------------------------------------------------------------------------
# the boundary check
# ---------------------------------------------------------------------------


def validate_rows(rows: Any, *, method: ChunkMethod) -> None:
    """Hold a method's rows to what it declared. Raises :class:`ContractError`.

    This runs for every method, however it was written, which is the point:
    the derived rows cannot drift from the declaration, and a frozen engine
    that quietly changed shape is caught here rather than in a Viewer that
    renders an empty badge.
    """
    if not isinstance(rows, (list, tuple)):
        raise ContractError(
            f"{method.key!r} produced {type(rows).__name__}; a partition produces a list of rows"
        )

    allowed = fields_of(method)
    required = allowed if not method.can(Capability.OFFSETS) else allowed - {"char_start", "char_end"}
    free = method.can(Capability.CUSTOM_METADATA)
    seen: set[str] = set()

    for index, row in enumerate(rows, start=1):
        where = f"{method.key!r} chunk {index}"
        if not isinstance(row, MappingABC):
            raise ContractError(f"{where}: a chunk row is a mapping, not {type(row).__name__}")

        missing = sorted(required - set(row))
        if missing:
            raise ContractError(
                f"{where}: missing {missing}. The core fields are "
                f"{list(CORE_FIELDS)}; the rest follow from the capabilities "
                f"the method declared ({sorted(c.value for c in method.capabilities)})."
            )
        if not free:
            undeclared = sorted(set(row) - allowed)
            if undeclared:
                raise ContractError(
                    f"{where}: carries {undeclared}, which {method.key!r} does not "
                    "declare. Declare the capability that owns the field, or "
                    "Capability.CUSTOM_METADATA to carry your own."
                )

        chunk_id = row["chunk_id"]
        if not isinstance(chunk_id, str) or not chunk_id:
            raise ContractError(f"{where}: chunk_id must be a non-empty string")
        if chunk_id in seen:
            raise ContractError(f"{where}: chunk_id {chunk_id!r} is used twice")
        seen.add(chunk_id)

        if not isinstance(row["text"], str) or not row["text"]:
            raise ContractError(f"{where}: text must be a non-empty string")
        if not isinstance(row["token_count"], int) or isinstance(row["token_count"], bool):
            raise ContractError(f"{where}: token_count must be an int")
        if row["token_count"] < 0:
            raise ContractError(f"{where}: token_count is negative")
        unit_ids = row["unit_ids"]
        if not isinstance(unit_ids, (list, tuple)) or any(
            not isinstance(unit_id, str) for unit_id in unit_ids
        ):
            raise ContractError(f"{where}: unit_ids must be a list of strings")
