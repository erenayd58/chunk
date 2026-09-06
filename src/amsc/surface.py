"""What in this package is product, what is research, and what may import what.

`amsc` grew as a research package and became a product dependency along the
way, so the two live in one flat namespace. Rather than move seventy-odd
modules -- which would break thirty documented ``python -m amsc.<module>``
entry points and the module names written into artifacts -- the boundary is
declared here and enforced by tests.

The five statuses
-----------------

``product``
    Supported. On the path the RAG console and the Viewer actually run.
    *Derived*, not listed: every module reachable by a module-level import
    from :data:`ENTRY_POINTS`. A new internal helper is product by simply
    being imported by one, and needs no edit here.
``service``
    The Viewer's own server process (``python -m amsc.viewer_server``).
    Product code, but it runs beside the console rather than inside it, and
    ``chat_rag`` never imports it. It is listed separately because it
    legitimately spans both worlds: its BM25 index deliberately uses the
    frozen benchmark's Turkish fold, so that a question asked in the Viewer is
    tokenised exactly as the benchmark tokenised it.
``research``
    Experiments, benchmarks, the frozen evaluator's runners, and the
    preparation tools around them. Still maintained, still runnable, still
    has real callers -- but nothing on the product path may import it.
``legacy``
    Kept only so an existing import path or an existing comparison keeps
    working. Not to be built on.
``unused``
    No importer anywhere in either repository, and no entry point. A deletion
    candidate. Empty as of Phase 8, which deleted the one module that had the
    status; it stays declared so the next such module has somewhere to sit
    while the deletion is decided.

The one rule
------------

**Nothing reachable from an entry point may be research, legacy or unused.**

That is the whole invariant, and it is checked by
``tests/unit/test_library_surface.py`` against the real import graph, not
against a list. A module that is *not* reachable from an entry point must be
declared below, so a new research module cannot quietly arrive unclassified.

Where new code goes
-------------------

* a new **product** module: write it, import it from something already on the
  product path, and add it to :data:`CONSOLE_API` only if ``chat_rag`` itself
  needs to import it;
* a new **research** module: write it and add its name to :data:`RESEARCH`;
* a new **chunking method**: it is neither -- register it in
  :mod:`amsc.methods` (``docs/adding-a-chunker.md``) and, if it is loaded on
  demand by the registry, add it to :data:`DISPATCHED`.
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
    "checkpoint_adapter",
    "checkpoint_layout",
    "prepare_full_checkpoint",
    "io",
    "models",
    # chunking
    "methods",              # the method registry -- method identity
    "structural_chunker",
    "deep_pipeline",        # Deep Analysis, the production entry point
    "deep_analysis",        # its configuration
    "deep_run",             # writing a Deep run as a tree
    "v4_chunker",           # the frozen V4 chunker, offered by the factory
    "config",               # V4Config and friends
    "tokenization",
    # embeddings and retrieval
    "embeddings",           # boundary embedders
    "cache",
    "rag_embeddings",       # retrieval embedders
    "retrieval_pipeline",   # BM25 / hybrid / RRF, the frozen implementations
    # measurement and presentation
    "structural_qa",
    "table_view",
    # the Viewer
    "deep_arm",             # packaging a run as a Viewer arm
    "viewer_corpus",        # the payload reader both Viewer pages share
})

#: Product modules loaded **on demand** by :mod:`amsc.methods` when a method is
#: actually run, rather than imported at module scope. They are product, they
#: are simply not in the eager closure, so they are named here.
DISPATCHED = frozenset({
    "markdown_chunker",
    "hybrid_chunker",
})

#: Every module the product path may start from. The product surface is
#: whatever these reach; nothing else has to be listed.
ENTRY_POINTS = CONSOLE_API | DISPATCHED | frozenset({
    "viewer_v3",        # the Viewer product page and its build
    "example_chunker",  # the documented template for a new chunking method
    "cli",              # the ``amsc`` console script
    "surface",          # this module
})

#: The Viewer's server process. See the ``service`` status above.
SERVICE = frozenset({
    "viewer_server",
    "rag_chat",
    "rag_index",
    "rag_context",
    "rag_answer",
})

#: Research: experiments, benchmarks, the frozen evaluator's runners and the
#: preparation tools around them. Real callers, real value, off the product
#: path -- and they must stay off it.
RESEARCH = frozenset({
    # the frozen three-arm and retrieval benchmarks
    "chunk_benchmark",
    "retrieval_benchmark",
    "run_retrieval_benchmark",
    "holdout_benchmark",
    "run_holdout_benchmark",
    "agentic_benchmark",
    "chunk_viewer",          # the per-run inspector chunk_benchmark writes
    # research phases
    "phase3c_research",
    "v5_research",
    "scale_calibration",
    "semantic_comparators",
    "semantic_assist",
    "failure_analysis",
    # gold sets and human labelling
    "boundary_preference",
    "gold_repin",
    # the v1 per-boundary judge and the Agentic arm built on it. Both were on
    # the product path until Phase 8 moved the provider transport and the
    # parallel-call machinery they held into `provider_calls`; what is left
    # here is the research, and Deep Analysis no longer imports either.
    "llm_boundary_judge",
    "agentic_chunker",
    # checkpoint preparation for research corpora
    "prepare_checkpoint",
    "checkpoint_qa",
})

#: Legacy: kept for an import path or a comparison, not to be built on.
LEGACY = frozenset({
    #: A pinned reproduction of the *public* ``MurselTasgin/chat_rag``
    #: chunker, used as a benchmark candidate. Not this product's code, and
    #: not a claim about KKB's production chunker.
    "legacy_chat_rag",
    #: Viewer v2: the earlier page, kept for the research build with its
    #: ``--agentic`` provenance arm and as a manual fallback. Viewer v3 is the
    #: product page. See ``docs/viewer-architecture.md``.
    "viewer_v2",
    "viewer_v2_template",
})

#: No importer anywhere in either repository, no entry point, not documented.
#: Empty since Phase 8 deleted ``parent_expansion``, the only entry it ever
#: had. The status stays: it is where a module goes when the evidence says
#: nothing reaches it and the deletion is a separate decision.
#: Evidence is in ``tests/unit/test_library_surface.py``.
UNUSED: frozenset[str] = frozenset()

#: Product modules with a research heritage, and exactly what the product uses
#: from each. These are the ones to be careful with: the module as a whole is
#: not a product API, only the named symbols are.
#:
#: Phase 8 emptied two of the four entries the right way round -- by moving the
#: product infrastructure out (``provider_calls``) rather than by declaring the
#: research modules product -- which took ``agentic_chunker`` and
#: ``llm_boundary_judge`` off the path entirely. The two that remain are here
#: because what product uses of them is deliberately shared, not accidentally
#: reached.
MIXED: dict[str, str] = {
    "evaluation":
        "the frozen boundary/chunk evaluator. Product uses only the percentile "
        "helpers `_median` / `_nearest_rank`, deliberately, "
        "so a structural-quality number computed for a live document matches "
        "one computed for the frozen corpus. Pinned by "
        "`tests/unit/test_chunk_quality.py`.",
    "chunker":
        "the V1-V3 orchestration, superseded by `structural_chunker`, "
        "`deep_pipeline` and `v4_chunker`. It is on the product path only "
        "because `amsc/__init__` exports `V1Chunker`/`V2Chunker`/`V3Chunker` as "
        "part of the package's public API. New product code should not use it.",
}

#: Everything declared, for the completeness check.
DECLARED = SERVICE | RESEARCH | LEGACY | UNUSED


def classify(module: str) -> Status:
    """The status of one ``amsc`` submodule, by its bare name.

    Anything not explicitly declared is ``product``: the product surface is
    derived from the import graph rather than listed, so a new internal helper
    needs no entry here. The graph itself is checked by
    ``tests/unit/test_library_surface.py``, which is what stops an
    *undeclared* research module from passing as product.
    """
    name = module.split(".")[-1] if module.startswith("amsc") else module
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
    name = module.split(".")[-1] if module.startswith("amsc") else module
    return name in CONSOLE_API
