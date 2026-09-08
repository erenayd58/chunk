# Viewer architecture — who owns what, and how a document reaches the page

Written for the engineer who has to change something in the Viewer and does not
want to trace two repositories first. Practical only; the product story is in
[viewer-v3.md](viewer-v3.md).

## The two repositories

| | `chunk` (this repo) | `chat_rag` (the console) |
|---|---|---|
| owns | chunking methods, the payload reader, the Viewer pages, the Viewer's own server | the documents, their ingest, the packaging lifecycle, the console API |
| holds no | product state — no uploads, no per-document status | copy of a chunker, a method list or a payload shape |
| the seam | `amsc.chunking.registry` (method identity) and `amsc.viewer.corpus` (payload shape) | reads both; states neither |

The rule that keeps it clean: **product state never moves into the library, and
the library's knowledge is never restated in the console.** When the two must
agree, the console reads `amsc`.

## The layers in `chunk`

```
amsc.chunking.registry            the registry: which methods exist, what each one is
    |                   (Phase 5 -- the single source of method identity;
    |                    served live at /api/methods, so a page built earlier
    |                    still lists a method registered later)
amsc.viewer.corpus      the reader: artifact trees -> one payload shape
    |                   load_corpus() and catalog(). Renders no page.
    +-- amsc.viewer.build      the product page   (built and served by start-demo)
    |
amsc.viewer.server      the service: serves a page, relays the console
```

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

With no trees this is the **product shell**: a page with no embedded corpus that
reads every document live from the console. That is the only build a clean
checkout can make, and it is what the product uses.
`chat_rag/start-demo.ps1` runs exactly this command when
`artifacts/viewer-v3/index.html` is missing, so a fresh clone needs no manual
build step. A page that is already there is served as it is — that is how a
research build with embedded trees survives a restart.

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

Two sources, one shape.

```
embedded (build time)   frozen research trees -> viewer.corpus.load_corpus -> DATA.docs
live (runtime)          the RAG console, through the Viewer's own server
```

The browser only ever talks to `amsc.viewer.server` (default `:8765`). It never
addresses the console, so there is no CORS grant and no console address in the
page.

```
browser
  |
  +-- GET  /                          the built page
  +-- GET  /api/methods               the method registry, as it is NOW
  +-- GET  /api/workspace             -> console GET  /api/demo/workspace
  +-- GET  /api/live-document?doc=    -> console GET  /api/demo/viewer-analysis/<id>/payload
  +-- POST /api/live-prepare          -> console POST /api/demo/viewer-analysis/<id>
  +-- POST /api/retrieve|chat|compare    local ChatEngine; on an unseen live
                                         document it first pulls the rows from
                                         console GET .../chunks and indexes them
  +-- GET  /api/health, /api/docs, /api/chunk   this process's own catalog
```

So there is one path per question:

| the page needs | it asks | authoritative source |
|---|---|---|
| available documents | `/api/workspace` | the console's `DocumentTracker` + analysis states |
| methods and their metadata | `/api/methods` at boot, falling back to the embedded `methodOrder/methodLabels/methodSummaries/methodMeta` | `amsc.chunking.registry` — live when served, build-time when the page is opened as a file; `/api/demo/methods` for availability on this machine |
| chunk boundaries, units, pages | `/api/live-document` (or the embedded payload) | `viewer.corpus.load_corpus` |
| chunk rows to retrieve over | `/api/retrieve` → console `.../chunks` | the packaged `chunks.jsonl` |
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
browser reads it through /api/demo/viewer-analysis/<id>/payload
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

**And no rebuild.** The build embeds the registry, which used to mean a new
method was invisible until somebody remembered `python -m amsc.viewer.build` — a
step with no error message, only a missing column. A served page now asks
`amsc.viewer.server` for `GET /api/methods` at boot and prefers that answer,
so what the page lists is what the library has registered *now*. The embedded
copy remains the fallback for a page opened as a file (a research build with
no server), and an older server without the route changes nothing. Held by
`test_methods_registry.py::test_a_page_built_before_the_method_existed_still_lists_it_when_served`
and, from the console side,
`chat_rag/tests/unit/test_chunker_extension.py::test_the_viewer_is_told_about_it_without_a_page_rebuild`.

Rebuilding the page is still what you do when the *template* changes — the
page is the template, and no route can serve that.

**Deep Analysis is the one exception**, and only where it has to be: it is an
orchestration over a baseline partition, so it carries extra status (which model
ran, how many calls, the decision story) that a partition method has none of.
The page finds it by the registry's `deep` flag, never by its name.

## Debugging a failed package

1. **What does the console think?**
   `GET /api/demo/viewer-analysis/<doc_id>` — `status`, `error`, `methods` (per
   variant), `ready_methods`, `failed_methods`. A `failed` here with a working
   `/payload` means a *rebuild* failed and the last good analysis is still up.
2. **What is on disk?**
   `chat_rag/artifacts/viewer-live/<key>/` — `state.json` (with a `traceback`
   when the worker caught it), `units.jsonl` (the canonical), `run/` (the Deep
   tree), `variants/<method>/chunks.jsonl`, `viewer-payload.json`. No payload
   file means nothing was ever published.
3. **Which method?** `state.json` → `methods.<key>.error`. One variant failing
   leaves the others `ready`; the document stays open on what worked.
4. **Retry** with `POST /api/demo/viewer-analysis/<doc_id>` (re-queues) or
   `POST .../methods {"methods": [...]}` (adds variants). Neither re-parses the
   PDF: the canonical is on disk.
5. **Common causes.** No canonical and no way to recover one — a document
   ingested before this packaging existed, whose parser-cache entry is gone.
   Hybrid unavailable — the sentence-embedding model is not downloaded on this
   machine; `GET /api/demo/methods` says so with the reason.
6. **The logs.** `chat_rag/logs/` (`ViewerAnalysis`) for the worker;
   `viewer.err.log` under the launcher's log directory for the Viewer server.
7. **The page shows nothing.** Check `/api/workspace` through the Viewer server,
   not the console: an unreachable console is a rendered state
   (`connected: false` with a reason), not an error.

## The files to know

| path | what |
|---|---|
| `chunk/src/amsc/chunking/registry.py` | the method registry — method identity |
| `chunk/src/amsc/chunking/method.py` | the `ChunkMethod` / `PartitionResult` types — a leaf module, so a method module can import them and the registry can import the method |
| `chat_rag/tools/promote_chunk_pin.py` | moves the `amsc-poc` pin to a chunk commit and checks it holds |
| `chunk/src/amsc/viewer/corpus.py` | the payload reader — the cross-repo contract |
| `chunk/src/amsc/viewer/build.py` + `viewer/template.py` | the product page and its build |
| `chunk/src/amsc/viewer/server.py` | the service the browser talks to |
| `chat_rag/components/viewer/analysis.py` | packaging lifecycle and state |
| `chat_rag/components/viewer/methods.py` | this deployment's view of the registry |
| `chat_rag/app.py` (`/api/demo/*`) | the console API the Viewer server relays |
| `chat_rag/start-demo.ps1` | builds the shell if missing, starts both processes |
| `chunk/tools/serve_viewer_v3.ps1` | serves the Viewer **alone**, with `chat_rag/.env`'s keys loaded into that one process. `start-demo.ps1` starts both processes; this is the case it does not cover, and `amsc.viewer.server` deliberately reads no `.env` of its own |

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
