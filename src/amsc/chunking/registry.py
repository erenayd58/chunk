"""The chunking methods, in one registry -- the answer to "where do I add one?"

A chunking method has an identity that travels a long way: the wire id a
console sends and the Viewer names an arm by (``structure-only``), the engine
kind a packaged ``mapping.json`` declares and the boundary-reason reader keys
on (``structure_first``), the product name and one-line summary every screen
shows (``Standard``), and the capabilities that decide how each layer treats
it -- does it need a sentence-embedding model, may it consult a language
model, is it one of the frozen benchmark's arms, may a budget cut of its be
arbitrated rather than greedy.

One :class:`ChunkMethod` per method, one ordered registry, and every consumer
reads it: the Viewer builder takes its order, labels, summaries and kinds from
here; the benchmark dispatches an arm's ``kind`` through :func:`partition`;
the relation deriver asks which kinds arbitrate their cuts; the console builds
its catalogue over it. A method registered here is known to all of them at
once.

Two kinds of method
-------------------

A **partition method** is a function from a canonical corpus to chunk rows
in the structural row schema -- Markdown, Standard and Hybrid are these, and
so is the example in :mod:`amsc.chunking.example`. It is registered with a
``partition`` callable and run through :func:`partition`, which hands it the
shared token budget and, when it declares ``needs_embedder``, a boundary
embedder.

**Deep Analysis is not a partition.** It is an orchestration -- the Standard
partition as a baseline, a proposer, a deterministic selector, a double-order
verifier, a status and report, table enrichment, and a deterministic fallback
-- that lives in :mod:`amsc.deep.pipeline` and is packaged by
:mod:`amsc.deep.arm`. The registry *describes* it (its key, kind, label,
that it consults a model, which method is its ``baseline``) so every layer can
list it and tell it apart, but it does not pretend to run it: asking
:func:`partition` for it fails with the reason. Uniform identity, not uniform
internals.

Adding a method
---------------

1. Write the method module: a partition ``units, counter, budget -> rows``
   in the structural row schema, and beside it the :class:`ChunkMethod`
   that describes it. Import the two types from :mod:`amsc.chunking.method`,
   never from here -- that is what lets this module import yours.
   :mod:`amsc.chunking.example` is a complete, minimal one: copy it.
2. Register it: import the method's :class:`ChunkMethod` below and add it
   to ``_BUILTIN``. That import and that tuple element are the whole entry.
3. Test it.

Nothing else. The Viewer lists it (the served page reads this registry at
request time, so no rebuild), the packager accepts it, the console offers it,
the benchmark can dispatch it. Registration is explicit and at import time on
purpose: no directory is scanned and no name is guessed, so what is offered is
exactly what somebody wrote down.

The built-in partitions below wrap their engine and import it lazily, because
those engines are also research entry points that must not be loaded merely to
learn a method's name. A new method needs neither the wrapper nor the lazy
import.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from typing import Any, Callable, Iterator, Optional

# The types a method module needs live in a leaf module so that a method can
# import them and this module can import the method. Re-exported here: every
# caller that reads ``registry.ChunkMethod`` keeps working.
from .method import DEEP_KIND, ChunkMethod, Partition, PartitionResult

__all__ = [
    "DEEP_KIND", "ChunkMethod", "Partition", "PartitionResult",
    "UnknownMethod", "NotAPartition",
    "register", "unregister", "get", "is_known", "by_kind", "methods", "order",
    "kinds", "partition_methods", "benchmark_arms", "deep_method",
    "kind_arbitrates", "meta", "partition",
    "ORDER", "LABELS", "SUMMARIES", "KINDS",
    "MARKDOWN", "HYBRID", "STANDARD", "DEEP",
]


class UnknownMethod(KeyError):
    """No method with this key (or kind) is registered."""

    def __init__(self, wanted: str, known: Sequence[str], *, by: str = "key"):
        self.wanted = wanted
        self.known = tuple(known)
        super().__init__(
            f"unknown chunking method {by} {wanted!r}; registered {by}s are "
            + ", ".join(repr(k) for k in known)
        )

    def __str__(self) -> str:  # KeyError would quote the whole message again
        return self.args[0]


class NotAPartition(TypeError):
    """The method exists but is not a partition function (Deep Analysis)."""


# --------------------------------------------------------------------------
# the built-in partitions
# --------------------------------------------------------------------------
# Engines are imported inside the functions: this module is imported by the
# Viewer builders, the benchmark and the console, none of which should pay
# for every engine's imports to learn a method's name.


def _budget_kwargs(budget: Mapping[str, Any]) -> dict[str, int]:
    return {
        name: int(budget[name])
        for name in ("min_tokens", "target_tokens", "soft_max_tokens", "hard_max_tokens")
        if name in budget
    }


def _partition_markdown(units, *, counter, budget, chunk_size_tokens=None,
                        chunk_overlap_tokens=None, **_ignored) -> PartitionResult:
    from . import markdown

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


def _partition_standard(units, *, counter, budget, respect_semantic_roles=False,
                        **_ignored) -> PartitionResult:
    from . import structural

    rows = structural.chunk_units(
        units, counter=counter, respect_semantic_roles=respect_semantic_roles,
        **_budget_kwargs(budget),
    )
    return PartitionResult(rows, {"respect_semantic_roles": respect_semantic_roles})


def _partition_hybrid(units, *, counter, budget, boundary_embedder=None,
                      respect_semantic_roles=False, **_ignored) -> PartitionResult:
    from . import hybrid

    result = hybrid.chunk_units(
        units, counter=counter, boundary_embedder=boundary_embedder,
        respect_semantic_roles=respect_semantic_roles, **_budget_kwargs(budget),
    )
    return PartitionResult(result.chunks, dict(result.diagnostics))


MARKDOWN = ChunkMethod(
    key="markdown",
    kind="markdown_recursive",
    label="Markdown",
    summary="Metni sabit boyutta keser; bölüm yapısına bakmaz.",
    partition=_partition_markdown,
    sized=True,
    benchmark_arm=True,
    # The sizes a live run uses: the frozen benchmark's, so a live Markdown
    # variant is that arm and not a lookalike.
    options={"chunk_size_tokens": 700, "chunk_overlap_tokens": 140},
)
HYBRID = ChunkMethod(
    key="hybrid",
    kind="hybrid_h1",
    label="Hybrid",
    summary="Yapıyı takip eder; bütçeyi aşan bölümlerde kesim yerini anlam benzerliğiyle seçer.",
    partition=_partition_hybrid,
    needs_embedder=True,
    arbitrated_cuts=True,
    benchmark_arm=True,
)
STANDARD = ChunkMethod(
    key="structure-only",
    kind="structure_first",
    label="Standard",
    summary="Dokümanın başlık yapısını takip eder; yalnız çok büyüyen bölümler bölünür.",
    partition=_partition_standard,
    benchmark_arm=True,
)
DEEP = ChunkMethod(
    key="agentic",
    kind=DEEP_KIND,
    label="Deep Analysis",
    summary="Standard'ın bıraktığı kötü sınırları arar ve düzeltir; kararsız yerlerde modele danışır.",
    deep=True,
    baseline=STANDARD.key,
    uses_model=True,
    arbitrated_cuts=True,
)

#: The methods the library ships, in the order the Viewer lists them. This
#: tuple is the registration: import a method's ``ChunkMethod`` from its
#: module and add it here. Nothing else in the library has to learn its name.
_BUILTIN: tuple[ChunkMethod, ...] = (MARKDOWN, HYBRID, STANDARD, DEEP)


# --------------------------------------------------------------------------
# the registry
# --------------------------------------------------------------------------
_lock = threading.RLock()
_registry: dict[str, ChunkMethod] = {}


def register(method: ChunkMethod, *, replace: bool = False) -> ChunkMethod:
    """Add a method. Keys and kinds are unique; ``replace`` allows re-registering
    the same key (a test swapping an implementation), never a kind collision
    between two different keys."""
    with _lock:
        existing = _registry.get(method.key)
        if existing is not None and not replace:
            raise ValueError(f"chunking method {method.key!r} is already registered")
        for other in _registry.values():
            if other.key != method.key and other.kind == method.kind:
                raise ValueError(
                    f"chunking method {method.key!r} declares kind {method.kind!r}, "
                    f"which {other.key!r} already uses"
                )
        _registry[method.key] = method
        return method


def unregister(key: str) -> ChunkMethod:
    """Remove a method (for tests that register a temporary one)."""
    with _lock:
        try:
            return _registry.pop(key)
        except KeyError:
            raise UnknownMethod(key, list(_registry)) from None


def get(key: str) -> ChunkMethod:
    with _lock:
        try:
            return _registry[key]
        except KeyError:
            raise UnknownMethod(key, list(_registry)) from None


def is_known(key: str) -> bool:
    with _lock:
        return key in _registry


def by_kind(kind: str) -> ChunkMethod:
    with _lock:
        for method in _registry.values():
            if method.kind == kind:
                return method
        raise UnknownMethod(kind, [m.kind for m in _registry.values()], by="kind")


def methods() -> tuple[ChunkMethod, ...]:
    """Every registered method, in registration (display) order."""
    with _lock:
        return tuple(_registry.values())


def order() -> tuple[str, ...]:
    return tuple(m.key for m in methods())


def kinds() -> dict[str, str]:
    """key -> kind, for a manifest writer or reader."""
    return {m.key: m.kind for m in methods()}


def partition_methods() -> tuple[str, ...]:
    return tuple(m.key for m in methods() if m.partition is not None)


def benchmark_arms() -> tuple[str, ...]:
    """The frozen chunk benchmark's arms, in its order."""
    return tuple(m.key for m in methods() if m.benchmark_arm)


def deep_method() -> Optional[ChunkMethod]:
    """The orchestration method, if one is registered (there is one)."""
    return next((m for m in methods() if m.deep), None)


def kind_arbitrates(kind: str) -> bool:
    """May a same-section budget cut of this kind have been arbitrated?"""
    with _lock:
        return any(m.kind == kind and m.arbitrated_cuts for m in _registry.values())


def meta() -> dict[str, dict[str, Any]]:
    """Capabilities per key, in the shape a page embeds: no callables."""
    return {
        m.key: {
            "kind": m.kind,
            "deep": m.deep,
            "baseline": m.baseline,
            "needsEmbedder": m.needs_embedder,
            "usesModel": m.uses_model,
            "benchmarkArm": m.benchmark_arm,
        }
        for m in methods()
    }


def partition(
    key: str,
    units: Sequence[Any],
    *,
    counter: Any,
    budget: Mapping[str, Any],
    boundary_embedder: Any = None,
    respect_semantic_roles: bool = False,
    **options: Any,
) -> PartitionResult:
    """Run one partition method over a canonical.

    ``budget`` is the shared token budget (``min_tokens``, ``target_tokens``,
    ``soft_max_tokens``, ``hard_max_tokens``). ``boundary_embedder`` may be
    the embedder or a zero-argument callable that builds it; it is resolved
    only for a method that declares ``needs_embedder``, so a caller can hand
    in a lazy loader and never pay for a model a method does not use.
    ``options`` override the method's own defaults (a Markdown size, say).
    """
    method = get(key)
    if method.partition is None:
        raise NotAPartition(
            f"{method.key!r} ({method.label}) is an orchestration, not a partition: "
            "run it through amsc.deep.pipeline.chunk_document and package it with "
            "amsc.deep.arm.package"
        )
    embedder = None
    if method.needs_embedder:
        embedder = boundary_embedder() if callable(boundary_embedder) else boundary_embedder
        if embedder is None:
            raise ValueError(f"{method.key!r} needs a boundary embedder and none was given")
    settings = {**method.options, **options}
    return method.partition(
        units, counter=counter, budget=budget, boundary_embedder=embedder,
        respect_semantic_roles=respect_semantic_roles, **settings,
    )


# --------------------------------------------------------------------------
# live views, for the modules that used to hold a tuple or a dict
# --------------------------------------------------------------------------
class _View(Mapping):
    """A read-only mapping over the registry, computed on every access, so a
    module-level name like ``ARM_KINDS`` stays true after a registration."""

    def __init__(self, project: Callable[[ChunkMethod], Any]):
        self._project = project

    def _items(self) -> dict[str, Any]:
        return {m.key: self._project(m) for m in methods()}

    def __getitem__(self, key: str) -> Any:
        return self._items()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._items())

    def __len__(self) -> int:
        return len(_registry)

    def __repr__(self) -> str:
        return repr(self._items())


class _Order(Sequence):
    """A read-only sequence of keys, computed on every access."""

    def __init__(self, select: Callable[[], tuple[str, ...]]):
        self._select = select

    def __getitem__(self, index):
        return self._select()[index]

    def __len__(self) -> int:
        return len(self._select())

    def __iter__(self) -> Iterator[str]:
        return iter(self._select())

    def __eq__(self, other: object) -> bool:
        return tuple(self._select()) == tuple(other) if isinstance(other, Sequence) else NotImplemented

    def __hash__(self) -> int:  # a Sequence with __eq__ must say so explicitly
        return hash(self._select())

    def __repr__(self) -> str:
        return repr(self._select())


#: Every key in display order; ``LABELS``, ``SUMMARIES`` and ``KINDS`` map a
#: key to that field. Each reflects the registry as it is now.
ORDER = _Order(order)
LABELS = _View(lambda m: m.label)
SUMMARIES = _View(lambda m: m.summary)
KINDS = _View(lambda m: m.kind)

for _method in _BUILTIN:
    register(_method)
del _method
