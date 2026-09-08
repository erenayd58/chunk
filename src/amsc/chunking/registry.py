"""The chunking methods, in one registry -- the answer to "where do I add one?"

A chunking method has an identity that travels a long way: the wire id a
console sends and the Viewer names an arm by (``structure-only``), the engine
kind a packaged ``mapping.json`` declares and the boundary-reason reader keys
on (``structure_first``), the product name and one-line summary every screen
shows (``Standard``), what its rows carry (:class:`Capability`), and the
capabilities that decide how each layer treats it -- does it need a
sentence-embedding model, may it consult a language model, is it one of the
frozen benchmark's arms, may a budget cut of its be arbitrated rather than
greedy.

One :class:`ChunkMethod` per method, one ordered registry, and every consumer
reads it: the Viewer builder takes its order, labels, summaries and kinds from
here; the benchmark dispatches an arm's ``kind`` through :func:`partition`;
the relation deriver asks which kinds arbitrate their cuts; the console builds
its catalogue over it. A method registered here is known to all of them at
once.

Where the methods come from
---------------------------

Not from a tuple in this file. :mod:`amsc.chunking.discovery` imports every
module in ``amsc/chunking/plugins/`` and registers every method it declares,
so **adding a method is adding a file**. The four shipped ones are four
modules in that directory; the constants below are re-exports, kept because
consoles and tests read ``registry.STANDARD``.

Two kinds of method
-------------------

A **partition method** is a function from a canonical corpus to chunks --
Markdown, Standard and Hybrid are these, and so is the example in
:mod:`amsc.chunking.example`. :func:`partition` runs it, handing it the
options it actually asks for, and normalises whatever it returns into a
:class:`PartitionResult` whose rows have been checked against the method's own
declaration (:mod:`amsc.chunking.contract`).

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

1. Write ``amsc/chunking/plugins/<your_method>.py``: a function from units to
   :class:`~amsc.chunking.contract.Chunk` objects, with
   :func:`~amsc.chunking.contract.chunker` above it saying what it is.
   :mod:`amsc.chunking.example` is a complete, minimal one: copy it.
2. There is no step 2. The file is the registration.
3. Test it.

The Viewer lists it (the served page reads this registry at request time, so
no rebuild), the packager accepts it, the console offers it, the benchmark can
dispatch it.
"""

from __future__ import annotations

import inspect
import threading
from collections.abc import Mapping, Sequence
from typing import Any, Callable, Iterator, Optional

# The types a method module needs live in a leaf module so that a method can
# import them and this module can import the method. Re-exported here: every
# caller that reads ``registry.ChunkMethod`` keeps working.
from .method import DEEP_KIND, Capability, ChunkMethod, Partition, PartitionResult
from .contract import Chunk, ChunkResult, ContractError, chunker, normalize, validate_rows
from . import discovery
from .plugins.deep import DEEP
from .plugins.hybrid import HYBRID
from .plugins.markdown import MARKDOWN
from .plugins.standard import STANDARD

__all__ = [
    "DEEP_KIND", "Capability", "ChunkMethod", "Partition", "PartitionResult",
    "Chunk", "ChunkResult", "ContractError", "chunker", "normalize", "validate_rows",
    "UnknownMethod", "NotAPartition",
    "register", "unregister", "get", "is_known", "by_kind", "methods", "order",
    "kinds", "partition_methods", "benchmark_arms", "deep_method",
    "kind_arbitrates", "meta", "capabilities", "partition", "discover",
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


def discover(package: str = discovery.PLUGIN_PACKAGE) -> tuple[ChunkMethod, ...]:
    """Register every method the plugin directory declares, and say which are new.

    Idempotent: a method already registered as itself is left alone, so this
    can be called again after a file is dropped into the directory --
    which is exactly what a long-running Viewer server does.
    """
    added: list[ChunkMethod] = []
    for method in discovery.discover(package):
        with _lock:
            if _registry.get(method.key) is method:
                continue
        register(method)
        added.append(method)
    return tuple(added)


def get(key: str) -> ChunkMethod:
    with _lock:
        try:
            return _registry[key]
        except KeyError:
            raise UnknownMethod(key, list(order())) from None


def is_known(key: str) -> bool:
    with _lock:
        return key in _registry


def by_kind(kind: str) -> ChunkMethod:
    for method in methods():
        if method.kind == kind:
            return method
    raise UnknownMethod(kind, [m.kind for m in methods()], by="kind")


def methods() -> tuple[ChunkMethod, ...]:
    """Every registered method, in display order.

    The order is :attr:`ChunkMethod.order` and then the key -- a fact each
    method states, rather than the order a plugin directory happened to be
    listed in. The shipped four claim 10..40 so a new method lands after them.
    """
    with _lock:
        return tuple(discovery.in_display_order(list(_registry.values())))


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
    return any(m.kind == kind and m.arbitrated_cuts for m in methods())


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


def capabilities() -> dict[str, list[str]]:
    """key -> the optional row fields that method's chunks carry.

    Read this rather than a row: what a method produces is a declaration, not
    something to be inferred by looking at one of its chunks and hoping the
    next is the same.
    """
    return {
        m.key: sorted(c.value for c in m.capabilities) for m in methods()
    }


# --------------------------------------------------------------------------
# running one
# --------------------------------------------------------------------------
#: Options handed only to a partition that names them outright, never through
#: ``**kwargs``. ``document`` is the rendering a method chunks when it works in
#: offsets; building one costs a pass over the corpus, so it is built for the
#: methods that asked and for nobody else.
_BY_NAME_ONLY = frozenset({"document"})


def _wanted(partition: Callable[..., Any], pool: Mapping[str, Any]) -> dict[str, Any]:
    """The subset of ``pool`` this partition actually asks for.

    A method declares what it needs by naming it. ``def chunk(units, *,
    counter)`` is a complete partition and is not handed a budget it never
    reads; ``def chunk(units, **options)`` is handed everything. This is what
    lets the minimal plugin in the docs be genuinely minimal.
    """
    try:
        signature = inspect.signature(partition)
    except (TypeError, ValueError):                 # a builtin or a C callable
        return {name: value for name, value in pool.items() if name not in _BY_NAME_ONLY}
    named = {
        name
        for name, parameter in signature.parameters.items()
        if parameter.kind in (parameter.KEYWORD_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    }
    takes_rest = any(
        parameter.kind is parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    return {
        name: value
        for name, value in pool.items()
        if name in named or (takes_rest and name not in _BY_NAME_ONLY)
    }


def _asks_for_document(partition: Callable[..., Any]) -> bool:
    try:
        return "document" in inspect.signature(partition).parameters
    except (TypeError, ValueError):
        return False


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
    """Run one partition method over a canonical, and check what it produced.

    ``budget`` is the shared token budget (``min_tokens``, ``target_tokens``,
    ``soft_max_tokens``, ``hard_max_tokens``). ``boundary_embedder`` may be
    the embedder or a zero-argument callable that builds it; it is resolved
    only for a method that declares ``needs_embedder``, so a caller can hand
    in a lazy loader and never pay for a model a method does not use.
    ``options`` override the method's own defaults (a Markdown size, say).

    A method that declares :attr:`Capability.OFFSETS` and names ``document``
    is handed the rendered document it chunks, and the units its spans cover
    are worked out from that rendering arithmetically.

    Whatever the method returns -- rows in a :class:`PartitionResult`, or
    :class:`~amsc.chunking.contract.Chunk` objects -- comes back as a
    :class:`PartitionResult` whose rows have been validated against the
    method's declaration. A row that does not satisfy it raises
    :class:`~amsc.chunking.contract.ContractError` here, naming the method and
    the chunk, rather than a ``KeyError`` in whichever consumer read it first.
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

    document = None
    if method.can(Capability.OFFSETS) and _asks_for_document(method.partition):
        from . import markdown as _markdown       # the renderer, loaded on demand

        document = _markdown.render_markdown(units)

    pool: dict[str, Any] = {
        "counter": counter,
        "budget": budget,
        "boundary_embedder": embedder,
        "respect_semantic_roles": respect_semantic_roles,
        "document": document,
        **method.options,
        **options,
    }
    produced = method.partition(units, **_wanted(method.partition, pool))
    return normalize(
        produced, method=method, units=units, counter=counter, document=document
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

discover()
