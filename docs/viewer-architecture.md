# Viewer architecture — who owns what, and how a document reaches the page

Written for the engineer who has to change something in the Viewer and does not
want to trace two repositories first. Practical only; the product story is in
[viewer-v3.md](viewer-v3.md).

## The two repositories

| | `chunk` (this repo) | `chat_rag` (the console) |
|---|---|---|
| owns | chunking methods, the payload reader, this repository's own page over its frozen corpus, and the retrieval engine behind *Sorgu* | the documents, their ingest, the packaging lifecycle, the `/api/v1` contract and **the Viewer screen the product uses** |
| holds no | product state — no uploads, no per-document status | copy of a chunker, a method list or a payload shape |
| the seam | `amsc.chunking.registry` (method identity) and `amsc.viewer.corpus` (payload shape) | reads both; states neither |

The rule that keeps it clean: **product state never moves into the library, and
the library's knowledge is never restated in the console.** When the two must
agree, the console reads `amsc`.

## The layers in `chunk`

```
amsc.chunking.registry            the registry: which methods exist, what each one is
    |                   (Phase 5 -- the single source of method identity;
    |                    the console projects it at
    |                    GET /api/v1/meta/chunking-methods, read at run time,
    |                    so a new method needs no rebuild of anything)
amsc.viewer.corpus      the reader: artifact trees -> one payload shape
    |                   load_corpus() and catalog(). Renders no page.
    +-- amsc.viewer.build      this repository's page over its frozen trees
    |
amsc.viewer.chat        the retrieval engine behind *Sorgu*, run by the console
```

**There used to be a fourth: `amsc.viewer.server`**, an HTTP server on `:8765`
that served the page, ran that engine and relayed the console's `/api/demo/*`
routes for a live document. Step 12 made the Viewer a screen of the console
over `/api/v1` and moved the engine to console API; Step 13 removed the relay
and the server. Nothing in either repository starts a second process
(`chat_rag/docs/legacy-removal.md`).

`viewer.corpus` is the whole cross-repository contract. The page reads it, and
so does `chat_rag`'s packaging worker — which is why a live document and a
frozen benchmark document have exactly the same shape and the page needs no
second reader.

## The build: what creates Viewer v3

One command, one input set, one output directory:

```powershell
py -3.11 -m amsc.viewer.build --output artifacts/viewer-v3/index.html
```

| | |
|---|---|
| inputs (required) | tracked source only: `viewer/build.py`, `viewer/template.py`, `viewer/corpus.py`, `chunking/registry.py`, `chunking/method.py` |
| inputs (optional) | `--benchmark DOC=DIR`, `--deep DOC=DIR` — frozen research trees, embedded into the page |
| outputs | `artifacts/viewer-v3/index.html` and `catalog.json` beside it |
| owner of the optional inputs | the research runs (`amsc.research.benchmark.chunkers`, `amsc.deep.run`). They are git-ignored and a fresh clone has none |

With no trees this builds an **empty shell**, which is the only build a clean
checkout can make and is what the tests use to check that the build reads the
registry rather than a list of its own. It is **not** the product's Viewer:
that is a screen of the console (`chat_rag/frontend/app/viewer/`), reading
`/api/v1`, and nothing in `chat_rag` builds or serves this page. What is here
is for looking at *this* repository's frozen benchmark corpus, which the
console has no copy of.

**Nothing generated is in version control.** `artifacts/` is git-ignored here,
`artifacts/viewer-live/` in `chat_rag`. Two tests hold that line:
`chunk/tests/unit/viewer/test_viewer_boundary.py::test_no_generated_viewer_output_is_in_version_control`
and its `chat_rag` counterpart.

| kind | where | rebuilt by |
|---|---|---|
| tracked source | `src/amsc/*.py` | — |
| build artifact | `artifacts/viewer-v3/{index.html,catalog.json}` | `python -m amsc.viewer.build` |
| runtime state | `chat_rag/artifacts/viewer-live/<key>/` | an ingest, or `resume_incomplete()` |
| disposable cache | `chat_rag` parser cache, `.cache/rag-embeddings/` | itself |

## Where Viewer v3 gets its data

One source per page, and one shape for both.

```
this repository's page   frozen research trees -> viewer.corpus.load_corpus -> DATA.docs
the product's Viewer     a live document       -> the same reader, in the console
```

The page built here is opened as a file, over the trees embedded in it at build
time. The product's Viewer is a screen of the console and asks the console:

| the screen needs | it asks | authoritative source |
|---|---|---|
| available documents | `GET /api/v1/documents` | the console's ledger, each row carrying its `analysis` block |
| methods and their metadata | `GET /api/v1/meta/chunking-methods` | `amsc.chunking.registry`, read at run time, plus availability on this machine |
| chunk boundaries, units, pages | `GET /api/v1/documents/<id>/analysis/payload` | `viewer.corpus.load_corpus` |
| chunk rows to retrieve over | `GET /api/v1/documents/<id>/analysis/methods/<m>/chunks` | the packaged `chunks.jsonl` |
| one question through several methods | `POST /api/v1/analysis-queries` | `amsc.viewer.chat`, run in the console's process |
| comparison / debug / benchmark | the same payload | one payload, several views |

## What runs after ingest (the packaging lifecycle)

All of it in `chat_rag/components/viewer/analysis.py`, one background worker
thread, one build at a time per document.

```
upload / ingest finishes
   |
   v  app.stage_viewer_analysis()
analysis.stage(units, deep_result, methods)     <- request thread, serialisation only
   |    writes units.jsonl (the canonical) and, on a Deep upload, the run tree
   |    writes state.json  status=pending
   v
analysis.enqueue(key)                            <- at most one job per key in flight
   |
   v  the worker
analysis._build(key)
   |    status=running
   |    Deep first (its packaging also writes the Standard partition)
   |    then every other requested method over the SAME canonical
   |    viewer.corpus.load_corpus(...)  ->  viewer-payload.json   <- PUBLICATION
   |    status=ready | failed
   v
the Viewer screen reads it through GET /api/v1/documents/<id>/analysis/payload
```

Identity is the **content hash**, not the upload id: the same PDF uploaded twice
is one analysis directory that answers for both `doc_id`s. That is why staging
twice is idempotent and why a second upload adds variants rather than a document.

**No second provider call, ever.** A Deep Analysis run made during ingest is
taken off the chunker as-is. A Deep variant asked for later, with no run to
reuse, runs the deterministic contract (`use_llm=False`) and is recorded as
exactly that. Held by
`chat_rag/tests/unit/test_viewer_packaging_offline.py`, which packages with the
network stubbed out entirely.

### What survives what

| situation | behaviour |
|---|---|
| restart during packaging | `resume_incomplete()` re-queues every `pending`/`running` record, and every `ready` one whose payload is missing. Disk is the authority; a finished document is not rebuilt |
| packaging failure | the state goes `failed` with the error; **the last published payload is untouched** and still served. One variant failing does not fail the others |
| missing/corrupt Viewer state | an unreadable `state.json` reports `failed`, and is never merged over (that would silently drop `doc_ids`). A `ready` record with no payload is demoted to `pending` |
| document deleted while packaging | the delete wins: the key is marked revoked, and the build removes its own output on the way out — otherwise the build's next write recreates the directory the delete removed |
| same document staged twice | one key, one directory; a build already in flight is not queued again |
| concurrent reads during publication | one `RLock` per key covers reads *and* writes of `state.json` and `viewer-payload.json` (on Windows an open reader is enough to break the writer's rename) |
| temp files | records are written `<name>.<pid>.<tid>.tmp` and renamed. `sweep_scratch()` runs at the start of `resume_incomplete()` and removes orphans |

The per-document build lock is deliberately *not* the state lock: a build holds
its lock for minutes and a status poll must not queue behind it.

## What else is in the Viewer's neighbourhood

| piece | status | why |
|---|---|---|
| `amsc.viewer.corpus` | **load-bearing, shared** | the reader the page, the server and the console all use. Method identity is `amsc.chunking.registry`'; this module restates none of it |
| `amsc.research.benchmark.inspector` | **load-bearing, research** | the per-run inspector `amsc.research.benchmark.chunkers` writes into every benchmark tree. Older than the product page and unrelated to it |

There is one page. A second builder over this same reader existed until it
was removed; nothing in the product served it, and the `--agentic` provenance
arm only it could show had no caller.

## Releasing a change that crosses both repos

`chat_rag` consumes this library as a **pinned dependency**, not as a sibling
checkout (`chat_rag/requirements.txt`: `amsc-poc @ git+...@<commit>`), and
`chat_rag/tests/unit/test_amsc_pin.py` checks every `from amsc... import` in
product code against that commit *and* against this checkout's HEAD. A
developer's editable install hides the difference; that test is what stops it.

So a change that adds or moves an `amsc` symbol the console imports lands in
three steps, in this order:

1. commit it here;
2. push;
3. bump the pin: `python tools/promote_chunk_pin.py` in `chat_rag`, which
   resolves the sha, refuses one that is unpushed or that HEAD does not
   contain, rewrites the one requirement line and runs the pin tests.

Until steps 1-3 are done, `test_amsc_pin` fails naming the missing symbol.
That is the check working, not a broken test: the console would not install
against the pinned library. Do not add a fallback import to quiet it -- the
fallback is what made the old dependency invisible in the first place.

## How a new chunker reaches the Viewer

Nothing Viewer-specific. Following `docs/adding-a-chunker.md`:

1. write `src/amsc/chunking/plugins/<yöntem>.py`: a partition returning
   `Chunk` objects, with `@chunker(...)` above it (types imported from
   `amsc.chunking.contract`);
2. there is no step 2 — the file is the registration;
3. write a test.

From there: the page keys behaviour off `methodMeta` flags (`deep`, `baseline`)
rather than off names; `viewer.corpus` accepts an arm packaged under its kind;
the console offers it (`components/viewer/methods.py` adds only availability
and product order); and the packager runs it over the canonical like any
other. Held end to end by
`chunk/tests/unit/chunking/test_methods_registry.py::test_a_registered_method_reaches_every_consumer_with_no_other_edit`.

**And no rebuild.** A new method used to be invisible in the Viewer until
somebody remembered `python -m amsc.viewer.build` — a step with no error
message, only a missing column. The product's Viewer is a screen of the console
now and reads `GET /api/v1/meta/chunking-methods` at run time, so registering
the method is the whole of exposing it. Held by
`chat_rag/tests/unit/test_chunker_extension.py::test_the_viewer_is_told_about_it_without_a_rebuild_of_anything`
and, from this side,
`test_methods_registry.py::test_a_built_page_carries_the_registry_as_it_was_when_it_was_built`.

This repository's own page is still a snapshot: it embeds the registry at build
time, because that is all a file opened from disk can carry. Rebuild it when a
method or the *template* changes.

**Deep Analysis is the one exception**, and only where it has to be: it is an
orchestration over a baseline partition, so it carries extra status (which model
ran, how many calls, the decision story) that a partition method has none of.
The page finds it by the registry's `deep` flag, never by its name.

## Debugging a failed package

1. **What does the console think?**
   `GET /api/v1/documents/<doc_id>/analysis` — `status`, `error`,
   `selected_methods`, `ready_methods`, `failed_methods`, and `content` for the
   shared analysis. A `failed` here with a working `/analysis/payload` means a
   *rebuild* failed and the last good analysis is still up.
2. **What is on disk?**
   `chat_rag/artifacts/viewer-live/<key>/` — `state.json` (with a `traceback`
   when the worker caught it), `units.jsonl` (the canonical), `run/` (the Deep
   tree), `variants/<method>/chunks.jsonl`, `viewer-payload.json`. No payload
   file means nothing was ever published.
3. **Which method?** `state.json` → `methods.<key>.error`. One variant failing
   leaves the others `ready`; the document stays open on what worked.
4. **Retry** with `POST /api/v1/documents/<doc_id>/analysis` (re-queues) or
   `POST .../analysis/methods {"methods": [...]}` (adds variants). Neither
   re-parses the PDF: the canonical is on disk.
5. **Common causes.** No canonical and no way to recover one — a document
   ingested before this packaging existed, whose parser-cache entry is gone.
   Hybrid unavailable — the sentence-embedding model is not downloaded on this
   machine; `GET /api/v1/meta/chunking-methods` says so with the reason.
6. **The logs.** `chat_rag/logs/` (`ViewerAnalysis`) for the worker.
7. **The screen shows nothing.** It reads `GET /api/v1/documents`, so start
   there: a document with no `analysis.ready_methods` has nothing to open yet,
   and `GET /api/v1/documents/<id>/analysis/payload` answers **409**
   `not_ready` with the state rather than an empty page.

## The files to know

| path | what |
|---|---|
| `chunk/src/amsc/chunking/registry.py` | the method registry — method identity |
| `chunk/src/amsc/chunking/method.py` | the `ChunkMethod` / `PartitionResult` types — a leaf module, so a method module can import them and the registry can import the method |
| `chat_rag/tools/promote_chunk_pin.py` | moves the `amsc-poc` pin to a chunk commit and checks it holds |
| `chunk/src/amsc/viewer/corpus.py` | the payload reader — the cross-repo contract |
| `chunk/src/amsc/viewer/build.py` + `viewer/template.py` | this repository's own page over its frozen trees, and its build |
| `chunk/src/amsc/viewer/chat/` | the retrieval engine behind *Sorgu*, run by the console |
| `chat_rag/components/viewer/analysis.py` | packaging lifecycle and state |
| `chat_rag/components/viewer/methods.py` | this deployment's view of the registry |
| `chat_rag/frontend/app/viewer/` + `components/viewer/` | **the product's Viewer**: five screens over `/api/v1` |
| `chat_rag/interfaces/http/v1/routers/documents.py` | the analysis routes the screen reads |
| `chat_rag/start-demo.ps1` | starts the backend and the console — two processes, no third |

## Tests that hold this

```powershell
# chunk
py -3.11 -m pytest tests/unit/viewer/test_viewer_boundary.py tests/unit/viewer/test_viewer_v3.py `
                   tests/unit/viewer/test_viewer_corpus.py tests/unit/chunking/test_methods_registry.py `
                   tests/integration/test_frozen_corpus_viewer.py

# chat_rag
py -3.11 -m pytest tests/unit/test_viewer_boundary.py tests/unit/test_viewer_analysis.py `
                   tests/unit/test_viewer_api_shapes.py tests/unit/test_viewer_packaging_offline.py `
                   tests/unit/test_viewer_state_concurrency.py tests/unit/test_demo_workspace.py
```
