# Package layout — where things live and why

`src/amsc` is organised by responsibility. The package a module sits in is the
first answer to "what is this for?", and the dependency direction between
packages is meant to be obvious from the names alone.

```
src/amsc/
├── document/          the canonical document: schema, file format, tokens
├── canonical/         PDF → canonical document
│   └── refine/          the per-signal repairs the preparer composes
├── chunking/          the chunking methods and the one registry
│   └── adaptive/        the frozen V1–V4 semantic lineage
├── deep/              Deep Analysis — an orchestration, not a partition
├── quality/           how good is this parse, this boundary, these chunks
├── tables/            a table as a retriever indexes it, as a reader sees it
├── embedding/         boundary embedding, and its cache
├── retrieval/         frozen BM25 / hybrid / RRF, and the retrieval embedder
├── viewer/            the read model, the page, and the demo server beside it
│   └── chat/            the demo's question-answering stack
├── research/          maintained research and evaluation, off the product path
│   ├── benchmark/       the frozen chunker / retrieval / holdout benchmarks
│   ├── agentic/         the superseded v1 Agentic arm
│   ├── gold/            gold sets and human labelling
│   └── corpus/          preparing and inspecting the research corpora
├── providers.py       the HTTP transport every model-consulting path shares
├── cli.py             the `amsc` console script
├── surface.py         which of the above a console may import, and why
└── __init__.py        a map; it re-exports nothing
```

## Fast answers

| question | answer |
|---|---|
| where do I add a chunking method? | `amsc/chunking/` — see [adding-a-chunker.md](adding-a-chunker.md) |
| where is the method registry? | `amsc/chunking/registry.py`, the only one |
| where does Deep Analysis live? | `amsc/deep/` — selector, proposer, verifier, pipeline, arm, run |
| where are the document/canonical primitives? | `amsc/document/` (schema, IO, tokens); `amsc/canonical/` builds them from a PDF |
| where is Viewer code? | `amsc/viewer/` — `corpus.py` is the read model, `build.py` + `template.py` the page, `server.py` + `chat/` the standalone demo |
| what is product code? | everything outside `amsc/research/`, minus what `surface.py` declares `service`. The exact rule and the check: [library-surface.md](library-surface.md) |
| what is research code? | everything under `amsc/research/`, declared module by module in `surface.py` |
| what is the intended public API? | `surface.CONSOLE_API` — 21 dotted module paths. `import amsc` gives you nothing else |

## Dependency direction

Imports point down this list, never up:

```
document                      imports nothing in the package
  ├─ canonical                document
  ├─ embedding                document
  ├─ retrieval                nothing
  ├─ chunking                 document, embedding
  ├─ quality                  document, chunking
  ├─ tables                   document, chunking
  ├─ deep                     document, chunking, quality, tables, providers
  ├─ viewer                   chunking, quality, tables, retrieval
  └─ research                 all of the above
```

Three modules are deliberate leaves and must stay that way — a test asserts it:

* `document/models.py`, `document/io.py`, `document/tokenization.py` — the
  bottom of the graph;
* `chunking/method.py` — the types a method module needs, so a method can
  import them and the registry can import the method without a cycle;
* `providers.py` — the model transport, owned by nobody, so Deep Analysis
  reaching a provider does not drag a research arm along with it.

There are no import cycles, and no package `__init__.py` imports anything:
each one is documentation. That is what keeps `import amsc.chunking.method`
costing one leaf module instead of a package's worth of engines, and it is why
the tree can be reorganised again without a re-export layer holding it
together.

## Product, research, and frozen evidence

Three different things, told apart three different ways:

* **product code** — everything outside `amsc/research/`. Supported, on the
  path a console request actually runs.
* **maintained research** — `amsc/research/`. Runnable, tested and often
  frozen, but nothing a console touches may import it; `surface.py` declares
  each module and the import graph is checked against that declaration.
* **frozen evidence** — not code. `artifacts/`, `evaluation/`,
  `data/*.units.jsonl` and `tests/fixtures/*-golden/` are checked-in results
  pinned by `tests/integration/`. They record the module names that produced
  them *at the time*; those names are history, not a live reference, and the
  files are not edited to match a later layout.

## What did not move, and why

* `data/`, `evaluation/`, `artifacts/`, `configs/` and `tests/fixtures/` are
  untouched: they are pinned by hash or by value.
* `document/models.py` stays one module although it holds both the canonical
  schema and the V1–V4 provenance types. The Pydantic graph is transitively
  connected — `ChunkingResult` → `ChunkBoundary` → `BoundaryEvidence` → the
  provenance classes — so splitting it would put a type and its own field
  types in different packages for no gain.
* Research module names (`phase3c`, `v5`, `scale_calibration`,
  `boundary_preference`) are unchanged. A phase label *is* the identity of a
  frozen result; renaming it would make the record harder to follow, not
  easier.

## Tests

`tests/unit/` mirrors this tree one level deep — `tests/unit/chunking/`,
`tests/unit/deep/`, `tests/unit/viewer/` and so on — so a package and its
tests are found the same way. `tests/integration/` stays flat: each file there
is one frozen contract, not one module's tests. Shared test helpers live beside
`tests/conftest.py`.
