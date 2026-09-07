# Library surface — product, research, legacy

`amsc` started as a research package and became a product dependency along the
way, so both live in one flat namespace. This note says which is which, and
where new code goes. The declaration itself is
[src/amsc/surface.py](../src/amsc/surface.py); the tests that make it true are
[tests/unit/test_library_surface.py](../tests/unit/test_library_surface.py)
and, on the console side, `chat_rag/tests/unit/test_amsc_surface.py`.

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

## The one rule

> Nothing reachable from an entry point may be research, legacy or unused.

Checked against the real import graph, not a list, and the failure names the
import chain that broke it:

```
product code reached modules it must not:
  chunk_benchmark <- table_view
  legacy_chat_rag <- retrieval_benchmark <- chunk_benchmark <- table_view
```

A second rule keeps the console honest: `chat_rag`'s **product code** may
import only `surface.CONSOLE_API` (21 modules). Its **tests** may import any
product module — fixtures legitimately need things the console does not — but
never a research or legacy one.

## What `chat_rag` may import

`amsc.surface.CONSOLE_API`, grouped by what it is for:

| area | modules |
|---|---|
| canonical documents (PDF → units) | `checkpoint_adapter`, `checkpoint_layout`, `prepare_full_checkpoint`, `io`, `models` |
| chunking | `methods` (the registry — method identity), `structural_chunker`, `deep_pipeline`, `deep_analysis`, `deep_run`, `v4_chunker`, `config`, `tokenization` |
| embeddings and retrieval | `embeddings`, `cache`, `rag_embeddings`, `retrieval_pipeline` |
| measurement and presentation | `structural_qa`, `table_view` |
| the Viewer | `deep_arm`, `viewer_corpus` |

The bare package (`import amsc`, for the version in the provenance snapshot)
is always allowed.

Adding one is a deliberate act: add the name in `surface.py` **here**, commit,
push, and bump the pin in `chat_rag/requirements.txt` — the same three-step
release any cross-repo change needs (see
[viewer-architecture.md](viewer-architecture.md)).

## Careful with these

Two product modules have a research heritage. The module as a whole is not a
product API; only the named symbols are. `surface.MIXED` carries the same list
in code. It was four until Phase 8 moved the provider transport and the
parallel-call machinery out of `agentic_chunker` and `llm_boundary_judge` into
`provider_calls`, which took both of those off the product path entirely.

| module | what product uses, and only that |
|---|---|
| `evaluation` | `_median`, `_nearest_rank` — **deliberately** shared, so a structural-quality number computed for a live document matches one computed for the frozen corpus. Pinned by `tests/unit/test_chunk_quality.py` |
| `chunker` | nothing directly. It is on the product path only because `amsc/__init__` exports `V1Chunker`/`V2Chunker`/`V3Chunker` as part of the package's public API. New product code should use `structural_chunker`, `deep_pipeline` or `v4_chunker` |

## Where new code goes

* **a new product module** — write it, import it from something already on the
  product path. Nothing to declare. Add it to `CONSOLE_API` only if `chat_rag`
  itself needs to import it.
* **a new research module** — write it and add its name to `RESEARCH` in
  `surface.py`. The completeness test will ask you to if you forget.
* **a new chunking method** — neither. Write the module (copy
  `example_chunker.py`; its types come from `chunk_method.py`, a leaf module
  that imports nothing else, which is what lets `methods.py` import your
  module without a cycle), then import its `ChunkMethod` into `amsc.methods`
  and add it to `_BUILTIN` ([adding-a-chunker.md](adding-a-chunker.md)). That
  import makes it product by reachability, so nothing is declared here. Only a
  method the registry loads *on demand* rather than at import — the three
  built-ins, whose engines are also research entry points — goes in
  `DISPATCHED`.
* **something the product and a benchmark both need** — put it in the product
  module that owns the concept and re-export it from the research module, not
  the other way round. That is how `normalize_unit_ids_for_retrieval` came to
  live in `chunk_mapping` (the single chunk↔unit resolver) with
  `chunk_benchmark` keeping the name on its surface.

## Why the files did not move

Directories would say all of this more loudly, and the cost was too high for
what it buys:

* about thirty modules are documented `python -m amsc.<module>` entry points
  (CLAUDE.md, `docs/`), and several write their own dotted name into artifacts
  (`"generator": "amsc.viewer_v3"`), which tests pin;
* `pyproject.toml` ships `amsc = "amsc.cli:main"`;
* moving them would need a re-export shim per module — which is the
  duplicate-surface problem, not a fix for it.

The declaration plus the graph test gives the same answer to every question a
directory layout would have answered, and it is checked rather than implied.
If the tree is ever reorganised, `surface.py` is the map to do it from.

## Known mixed areas, and what is left

* `evaluation`'s two percentile helpers are shared on purpose and pinned by a
  test; extracting them would need that contract restated, not removed.
* `rag_index` (Viewer service) reads the frozen benchmark's Turkish fold table
  from `chunk_benchmark` by design, so the Viewer's chat tokenises exactly as
  the benchmark did. This is why `service` is its own status rather than part
  of `product`.
* `unused` is empty. `parent_expansion` held it — no importer anywhere in
  either repository, no entry point — and Phase 8 deleted it. The status stays
  declared so the next such module has somewhere to sit while the deletion is
  decided.
