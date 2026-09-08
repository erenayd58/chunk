"""What in this package is product, what is research, and what may import what.

The package tree already separates the domains -- :mod:`amsc.document`,
:mod:`amsc.canonical`, :mod:`amsc.chunking`, :mod:`amsc.deep`,
:mod:`amsc.quality`, :mod:`amsc.retrieval`, :mod:`amsc.viewer`,
:mod:`amsc.research`. What a tree cannot say is which of those a *console*
may depend on, or that a lazily imported research module is still off the
product path. That is declared here, by full dotted module name, and enforced
against the real import graph by ``tests/unit/test_library_surface.py``.

**The one rule: nothing reachable from an entry point may be research, legacy
or unused.** A module that is *not* reachable from one must be declared below,
so a new research module cannot arrive unclassified.

``product`` is *derived*, never listed: whatever :data:`ENTRY_POINTS` reaches
by a module-level import. ``service`` is the Viewer's own server process --
product code, but it runs beside the console rather than inside it, and it is
separate because it legitimately spans both worlds (its BM25 index uses the
frozen benchmark's Turkish fold, so a Viewer question is tokenised exactly as
the benchmark tokenised it). ``research`` is maintained, runnable and off the
product path; every module under ``amsc.research`` is research by where it
lives, and this module says so rather than letting the package name imply it.
``legacy`` is kept only so an existing comparison keeps working. ``unused``
has no importer anywhere and no entry point: a deletion candidate.

``docs/library-surface.md`` says where new code goes.
"""

from __future__ import annotations

from typing import Literal

Status = Literal["product", "service", "research", "legacy", "unused"]


#: The modules ``chat_rag``'s **product code** may import. This is the console
#: contract: an import outside this set, from anything but a test, fails
#: ``chat_rag/tests/unit/test_amsc_surface.py``. Keep it small and deliberate
#: -- every name here is something the console genuinely calls.
CONSOLE_API = frozenset({
    # canonical documents: PDF -> units
    "canonical.adapter",
    "canonical.layout",
    "canonical.prepare",
    "document.io",
    "document.models",
    "document.tokenization",
    # chunking
    "chunking.registry",        # the method registry -- method identity
    # ``chunking.method`` (the ChunkMethod / PartitionResult types) is not
    # here: the registry re-exports both, so the console never imports it.
    "chunking.structural",
    "chunking.adaptive.v4",     # the frozen V4 chunker, offered by the factory
    "chunking.adaptive.config",  # V4Config and friends
    # Deep Analysis
    "deep.pipeline",            # the production entry point
    "deep.selector",            # DeepConfig, and the objective it names
    "deep.run",                 # writing a Deep run as a tree
    "deep.arm",                 # packaging a run as a Viewer arm
    # embeddings and retrieval
    "embedding.boundary",
    "embedding.cache",
    "retrieval.embeddings",     # retrieval embedders -- not the boundary ones
    "retrieval.pipeline",       # BM25 / hybrid / RRF, the frozen implementations
    # measurement and presentation
    "quality.lint",
    "tables.view",
    # the Viewer
    "viewer.corpus",            # the payload reader the Viewer and console share
})

#: Product modules loaded **on demand** by :mod:`amsc.chunking.registry` when a
#: method is actually run, rather than imported at module scope. They are
#: product, they are simply not in the eager closure, so they are named here.
DISPATCHED = frozenset({
    "chunking.markdown",
    "chunking.hybrid",
})

#: The auto-discovered chunking plugin directory. Every module under it is an
#: entry point by construction: :mod:`amsc.chunking.discovery` imports the
#: directory, so a file dropped there is loaded whether or not anything names
#: it. Declaring the *package* rather than each file is what lets a new
#: chunker be one new file -- and because each is an entry point, whatever a
#: plugin imports is still held to the one rule.
PLUGIN_PACKAGE = "chunking.plugins"

#: Every module the product path may start from. The product surface is
#: whatever these reach; nothing else has to be listed. Plugin modules are
#: entry points too -- see :data:`PLUGIN_PACKAGE` -- and are added to this set
#: by ``tests/unit/test_library_surface.py``, which is the one place that
#: knows which files exist.
ENTRY_POINTS = CONSOLE_API | DISPATCHED | frozenset({
    "viewer.build",      # the Viewer product page and its build
    "chunking.example",  # the documented template for a new chunking method
    "cli",               # the ``amsc`` console script
    "surface",           # this module
})

#: The Viewer's server process. See the ``service`` status above.
SERVICE = frozenset({
    "viewer.server",
    "viewer.chat.session",
    "viewer.chat.index",
    "viewer.chat.context",
    "viewer.chat.answer",
})

#: Research: experiments, benchmarks, the frozen evaluator's runners and the
#: preparation tools around them. Real callers, real value, off the product
#: path -- and they must stay off it. Everything under ``amsc.research`` is
#: here; the list is the assertion, the package is only where it lives.
RESEARCH = frozenset({
    # the frozen three-arm, retrieval and holdout benchmarks
    "research.benchmark.chunkers",
    "research.benchmark.retrieval",
    "research.benchmark.run_retrieval",
    "research.benchmark.holdout",
    "research.benchmark.run_holdout",
    "research.benchmark.agentic",
    "research.benchmark.inspector",   # the per-run inspector the benchmark writes
    # research phases
    "research.phase3c",
    "research.v5",
    "research.scale_calibration",
    "research.semantic_comparators",
    "research.semantic_assist",
    "research.failure_analysis",
    # gold sets and human labelling
    "research.gold.boundary_preference",
    "research.gold.repin",
    # the v1 per-boundary judge and the Agentic arm built on it. Both were on
    # the product path until Phase 8 moved the provider transport and the
    # parallel-call machinery they held into `amsc.providers`; what is left
    # here is the research, and Deep Analysis no longer imports either.
    "research.agentic.judge",
    "research.agentic.chunker",
    # checkpoint preparation for research corpora
    "research.corpus.prepare_pages",
    "research.corpus.qa",
})

#: Legacy: kept for an import path or a comparison, not to be built on.
LEGACY = frozenset({
    #: A pinned reproduction of the *public* ``MurselTasgin/chat_rag``
    #: chunker, used as a benchmark candidate. Not this product's code, and
    #: not a claim about KKB's production chunker.
    "research.legacy_chat_rag",
})

#: No importer anywhere in either repository, no entry point, not documented.
#: Where a module goes when the evidence says nothing reaches it and the
#: deletion is a separate decision. Evidence lives in
#: ``tests/unit/test_library_surface.py``, which checks the claim.
UNUSED: frozenset[str] = frozenset()

#: Product modules with a research heritage, and exactly what the product uses
#: from each. The ones to be careful with: the module as a whole is not a
#: product API, only the named symbols are, and each is shared deliberately
#: rather than reached by accident.
MIXED: dict[str, str] = {
    "quality.evaluation":
        "the frozen boundary/chunk evaluator. Product uses only the percentile "
        "helpers `_median` / `_nearest_rank`, deliberately, "
        "so a structural-quality number computed for a live document matches "
        "one computed for the frozen corpus. Pinned by "
        "`tests/unit/test_chunk_quality.py`.",
    "chunking.adaptive.v1_v3":
        "the V1-V3 orchestration, superseded by `chunking.structural`, "
        "`deep.pipeline` and `chunking.adaptive.v4`. It is on the product path "
        "only because the `amsc` console script can still run a V1-V3 config. "
        "New product code should not use it.",
}

#: Everything declared, for the completeness check.
DECLARED = SERVICE | RESEARCH | LEGACY | UNUSED


def _name(module: str) -> str:
    """The dotted path of a submodule, relative to the package."""
    if module == "amsc":
        return ""
    return module[len("amsc."):] if module.startswith("amsc.") else module


def is_plugin(module: str) -> bool:
    """Whether this module is an auto-discovered chunking plugin."""
    return _name(module).startswith(PLUGIN_PACKAGE + ".")


def classify(module: str) -> Status:
    """The status of one ``amsc`` submodule, by its dotted path.

    Anything not explicitly declared is ``product``: the product surface is
    derived from the import graph rather than listed, so a new internal helper
    needs no entry here. The graph itself is checked by
    ``tests/unit/test_library_surface.py``, which is what stops an
    *undeclared* research module from passing as product.
    """
    name = _name(module)
    if is_plugin(module):
        return "product"
    if name in SERVICE:
        return "service"
    if name in RESEARCH:
        return "research"
    if name in LEGACY:
        return "legacy"
    if name in UNUSED:
        return "unused"
    return "product"


def console_may_import(module: str) -> bool:
    """Whether ``chat_rag``'s product code may import this ``amsc`` module."""
    return _name(module) in CONSOLE_API
