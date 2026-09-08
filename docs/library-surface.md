# Library surface — product, research, legacy

`amsc` started as a research package and became a product dependency along the
way. The package tree now separates the domains
([package-layout.md](package-layout.md)); this note says which of them a
*console* may depend on, and where new code goes. The declaration itself is
[src/amsc/surface.py](../src/amsc/surface.py); the tests that make it true are
[tests/unit/test_library_surface.py](../tests/unit/test_library_surface.py)
and, on the console side, `chat_rag/tests/unit/test_amsc_surface.py`.

Modules are named here by their dotted path below `amsc` — `chunking.registry`,
`research.benchmark.chunkers` — which is what the declaration uses.

## The five statuses

| status | what it means | how it is decided |
|---|---|---|
| **product** | supported; on the path the console and the Viewer actually run | **derived** — every module reachable by a module-level import from `ENTRY_POINTS` |
| **service** | the Viewer's own server process; product code, but a separate process the console never imports | declared |
| **research** | experiments, benchmarks, the frozen evaluator's runners, preparation tools | declared |
| **legacy** | kept only so an import path or a comparison keeps working | declared |
| **unused** | no importer anywhere, no entry point; a deletion candidate | declared, with evidence (empty since Phase 8) |

Product is derived on purpose. A new internal helper becomes product simply by
being imported by something already on the path — no list to update. What
*must* be declared is anything **off** the path, which is exactly the moment
someone should be asked what a new module is.

The tree and the declaration say the same thing twice on purpose: everything
under `amsc/research/` is declared `research` or `legacy`, and
`test_everything_under_the_research_package_is_declared_research` fails if the
two ever disagree — in either direction. The package name is the signpost; the
declaration is the check.

## The one rule

> Nothing reachable from an entry point may be research, legacy or unused.

Checked against the real import graph, not a list, and the failure names the
import chain that broke it:

```
product code reached modules it must not:
  research.benchmark.chunkers <- tables.view
  research.legacy_chat_rag <- research.benchmark.retrieval <- research.benchmark.chunkers <- tables.view
```

A second rule keeps the console honest: `chat_rag`'s **product code** may
import only `surface.CONSOLE_API` (21 modules). Its **tests** may import any
product module — fixtures legitimately need things the console does not — but
never a research or legacy one.

## What `chat_rag` may import

`amsc.surface.CONSOLE_API`, grouped by what it is for:

| area | modules |
|---|---|
| canonical documents (PDF → units) | `canonical.adapter`, `canonical.layout`, `canonical.prepare`, `document.io`, `document.models`, `document.tokenization` |
| chunking | `chunking.registry` (the registry — method identity), `chunking.structural`, `chunking.adaptive.v4`, `chunking.adaptive.config` |
| Deep Analysis | `deep.pipeline`, `deep.selector`, `deep.run`, `deep.arm` |
| embeddings and retrieval | `embedding.boundary`, `embedding.cache`, `retrieval.embeddings`, `retrieval.pipeline` |
| measurement and presentation | `quality.lint`, `tables.view` |
| the Viewer | `viewer.corpus` |

The bare package (`import amsc`, for the version in the provenance snapshot)
is always allowed, and costs nothing: `amsc/__init__.py` re-exports nothing.

Adding one is a deliberate act: add the name in `surface.py` **here**, commit,
push, and bump the pin in `chat_rag/requirements.txt` — the same three-step
release any cross-repo change needs (see
[viewer-architecture.md](viewer-architecture.md)).

## Careful with these

Two product modules have a research heritage. The module as a whole is not a
product API; only the named symbols are. `surface.MIXED` carries the same list
in code. It was four until Phase 8 moved the provider transport and the
parallel-call machinery out of the v1 Agentic arm into `amsc.providers`, which
took both of those off the product path entirely.

| module | what product uses, and only that |
|---|---|
| `quality.evaluation` | `_median`, `_nearest_rank` — **deliberately** shared, so a structural-quality number computed for a live document matches one computed for the frozen corpus. Pinned by `tests/unit/quality/test_chunk_quality.py` |
| `chunking.adaptive.v1_v3` | nothing directly. It is on the product path only because the `amsc` console script can still run a V1–V3 config. New product code should use `chunking.structural`, `deep.pipeline` or `chunking.adaptive.v4` |

## Where new code goes

* **a new product module** — write it in the package that owns the concept
  ([package-layout.md](package-layout.md)) and import it from something already
  on the product path. Nothing to declare. Add it to `CONSOLE_API` only if
  `chat_rag` itself needs to import it.
* **a new research module** — write it under `amsc/research/` and add its
  dotted name to `RESEARCH` in `surface.py`. Two tests will ask you to if you
  forget: the completeness check, and the one that says the package and the
  declaration must agree.
* **a new chunking method** — neither. Drop the module into
  `amsc/chunking/plugins/` (copy `chunking/example.py`; its types come from
  `chunking/contract.py`) and that is the whole registration
  ([adding-a-chunker.md](adding-a-chunker.md)). A plugin needs no declaration
  here: `surface.PLUGIN_PACKAGE` says the directory is auto-discovered, so
  every module under it is an **entry point** — product by construction, and
  still walked, so a plugin that reached a research module fails the one rule
  like anything else. Only a module the registry loads *on demand* rather than
  at import — the engines behind the shipped methods, which are also research
  entry points — goes in `DISPATCHED`.
* **something the product and a benchmark both need** — put it in the product
  module that owns the concept and re-export it from the research module, not
  the other way round. That is how `normalize_unit_ids_for_retrieval` came to
  live in `chunking.mapping` (the single chunk↔unit resolver) with
  `research.benchmark.chunkers` keeping the name on its surface.

## Why the declaration survives the tree

The tree answers *where does this live*; only the declaration can answer *may
the console depend on it*, and only the graph test can answer *did a lazy
import put research back on the product path*. So both stay:

* `DISPATCHED` names product modules the registry imports **inside a function**
  — invisible to the tree and to a reader, deliberate in the declaration;
* `SERVICE` separates the Viewer's server process from the console's surface
  even though both live under `amsc/viewer/`;
* `MIXED` names a product module whose *symbols* are the API rather than the
  module, which no directory can express;
* `CONSOLE_API` is a cross-repository contract, not a layout.

## Known mixed areas, and what is left

* `quality.evaluation`'s two percentile helpers are shared on purpose and
  pinned by a test; extracting them would need that contract restated, not
  removed.
* `viewer.chat.index` (Viewer service) reads the frozen benchmark's Turkish
  fold table from `research.benchmark.chunkers` by design, so the Viewer's chat
  tokenises exactly as the benchmark did. This is why `service` is its own
  status rather than part of `product`.
* `deep.arm` imports `research.benchmark.agentic` **inside a function**, to
  write a comparison summary when one is asked for. It is the one product →
  research edge left, it is deferred, and the graph test allows it because it
  is not on the import path of a Deep run. Reversing it (moving the summary
  writer into `deep`) is open.
* `unused` is empty. `parent_expansion` held it — no importer anywhere in
  either repository, no entry point — and Phase 8 deleted it. The status stays
  declared so the next such module has somewhere to sit while the deletion is
  decided.
