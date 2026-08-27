# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`amsc-poc` — **Adaptive Multi-Signal Semantic Chunking**: an LLM-free document chunker that
finds topic boundaries from a document's own semantic distribution. Target corpus is
Turkish-heavy KKB annual reports. This is a proof of concept with a frozen, replayable
evaluation checkpoint, not a production system.

Prose documentation (`README.md`, `docs/`) is in Turkish; code, identifiers and config keys
are English.

## Commands

Install (Python 3.11–3.13; extras are separate on purpose):

```powershell
py -3.11 -m pip install -e ".[dev]"          # tests
py -3.11 -m pip install -e ".[model]"        # real multilingual-e5-base
py -3.11 -m pip install -e ".[benchmark]"    # phase 4/5 retrieval benchmarks
py -3.11 -m pip install -e ".[checkpoint]"   # pymupdf4llm PDF adapter (version-pinned)
```

Tests (`addopts = -q --basetemp=.pytest-tmp`, `testpaths = tests`):

```powershell
py -3.11 -m pytest
py -3.11 -m pytest tests/unit/test_v4_selection.py
py -3.11 -m pytest tests/unit/test_v4_selection.py::test_name
py -3.11 -m pytest -k merge
```

Tests never download a model — `tests/conftest.py` provides deterministic doubles
(`WordTokenCounter`, `StaticBoundaryEmbedder`, `FakeModelTokenizer`, `RecordingBackend`).
Only a dedicated unit test exercises the real `cl100k_base` counter.

Chunking (`amsc` console script, or `python -m amsc.cli`):

```powershell
py -3.11 -m amsc.cli validate --input tests/fixtures/sample.units.jsonl
py -3.11 -m amsc.cli chunk --input data/kkb-2024.units.jsonl --config configs/v3.yaml --output artifacts/out
py -3.11 -m amsc.cli chunk --input data/kkb-2024.units.jsonl --config configs/v4.yaml --ablation a4 --output artifacts/out
```

Every other stage is its own `python -m amsc.<module>` entry point:

| Module | Purpose |
|---|---|
| `amsc.prepare_checkpoint` | PDF → canonical JSONL for selected pages (`--pages 40-55`) |
| `amsc.prepare_full_checkpoint` | Full mixed-orientation document, requires `--layout-profile`; `--canonical-profile v1-frozen\|v2-repaired\|v3-semantic` |
| `amsc.checkpoint_qa` | Human-readable QA preview of canonical JSONL |
| `amsc.evaluation` | `worksheet` / `evaluate` — the **authoritative** boundary + chunk metrics |
| `amsc.failure_analysis` | Prediction/gold/merge audit, `--run ID=DIR` (diagnostic only) |
| `amsc.phase3c_research` | Phase 3C semantic comparators C0–C3 |
| `amsc.v5_research` | Phase 3B scale-calibration B0–B3 |
| `amsc.run_retrieval_benchmark` | Phase 4 retrieval benchmark on KKB 2024 |
| `amsc.run_holdout_benchmark` | Phase 5 holdout validation on KKB 2022 |
| `amsc.chunk_benchmark` | Markdown / Hybrid / Structure-only comparison on time and quality (`--output` is **required**) |
| `amsc.semantic_roles` | Library only — the heading/section split; no CLI |
| `amsc.structural_qa` | Structural QA linter over a canonical corpus and its chunks |
| `amsc.viewer_v2` | Presentation-grade single-file HTML viewer over a completed chunk-benchmark tree (Sunum/Sorgu/Debug/Benchmark modes); pure reader, verifies the tree's `units_sha256` pin |
| `amsc.chunk_relations` | Derived continuation sidecars over frozen chunks (adjacent + same heading + joining section paths, nothing else), typed by the observable boundary: `TOKEN_BUDGET_CONTINUATION` only for a plain `budget_split`; label seams and markdown cuts get their own types. `expand_context` walks **only** TOKEN_BUDGET_CONTINUATION — never re-ranks, hard token budget, section change or any non-budget boundary is a hard stop |
| `amsc.semantic_assist` | Library only — **embedding-assisted research baseline** (not the product mode): `STANDARD` delegates to `structural_chunker`, `SEMANTIC_ASSIST` to `hybrid_chunker` (both byte-identical to the benchmarked arms); `eligible_sections` names the ambiguity surface embedder-free. `OpenRouterEmbeddingProvider` is adapter-only, NOT VERIFIED; Qwen3-Embedding-8B is reserved as a future *retrieval* embedding candidate |
| `amsc.llm_boundary_judge` | Library only — the product's **Deep Analysis** mode: structure-first chunking whose plain budget cuts with ≥2 admissible positions are judged SPLIT/KEEP by a backend generative LLM at ingest. Label seams stay structural; no judge / all-KEEP / parse or provider failure is byte-identical to `structural_chunker` (pinned). Structured decisions only (`reason_code` is audit, never steering); provider-agnostic `OpenAICompatibleJudgeProvider` (model id required, key env configurable, NOT VERIFIED); backend-only — no key or LLM call ever reaches viewer HTML |

Both preparers are thin CLI wrappers over an in-memory core —
`checkpoint_adapter.extract_canonical_units()` and
`prepare_full_checkpoint.extract_full_canonical_units()` — which return a
`CanonicalExtraction` and write nothing. Applications that need canonical units without
files (the `chat_rag` ingestion path does) call those directly, so there is exactly one
canonical extraction implementation. `extract_full_canonical_units` takes the layout
profile as **optional**: omit it and spread pages keep the frozen extractor's own reading
order, which is correct for ordinary portrait documents.

**Canonical profiles.** Every canonical repair is opt-in and off by default, so
`--canonical-profile v1-frozen` reproduces `data/*.units.jsonl` byte for byte (verified
against the pinned `units_sha256`). **The three profiles do not share a manifest
contract and must not be made to.** v1-frozen is the historical baseline: its manifest
predates `canonical_profile` and `units_sha256`, and the writer deliberately skips both
for that profile, so a v1 regeneration does not rewrite the one artifact whose value is
that it has not been rewritten. v1 is pinned instead by `data/kkb-2024.units.sha256`,
by literal constants in [test_canonical_pins.py](tests/integration/test_canonical_pins.py)
and by every config that consumes it. v2/v3 are generated artifacts and their manifests
must carry `canonical_profile` (profile id **and** the exact repair set),
`units_file` and a matching `units_sha256`. `v2-repaired` is the named set in
`prepare_full_checkpoint.V2_CANONICAL_REPAIRS`: visual-grid reconstruction, lead-in and
standfirst demotion, table-caption demotion, split-heading rejoin, hyphenated-heading
rejoin, missed numbered-heading promotion and
[heading_levels.py](src/amsc/heading_levels.py). `v3-semantic` adds
[semantic_roles.py](src/amsc/semantic_roles.py) on top. Each writes `data/*.units.v{2,3}.jsonl`
and records its repair set under `canonical_profile` in the manifest. [split_headings.py](src/amsc/split_headings.py) carries two rejoins that are geometric
opposites and cannot match each other's pairs: `rejoin_split_headings` merges heading
fragments printed **side by side** on one line (a bare `24.` beside its title),
`rejoin_hyphenated_headings` merges fragments **stacked** on two lines of one column, where
the upper one ends mid-word at a hyphen and the lower one resumes it in lower case. Both
signals stay narrow because two headings sharing a line are usually two real headings, and
two stacked headings are usually a title and its subtitle. The one guess in the hyphen rule
is dropping the hyphen: a hard hyphen in a compound that breaks at its own hyphen is
indistinguishable from a soft one without a lexicon. Fires twice on kkb-2024, never on
kkb-2022 — where the same defect exists but the continuation is three blocks away in another
column, so it stays a recorded limitation rather than a looser rule.

**Running-header removal is deliberately not in the set** — on kkb-2024
`drop_running_headers` deletes 42 furniture headings but also every occurrence of two real
numbered chapter titles, so it stays off and the banners stay a recorded limitation
(`artifacts/parser-audit/`).

**Looking like a heading and bearing hierarchy are two different claims**, and conflating
them is what made a card grid open twenty-nine sections where a reader sees one.
[semantic_roles.py](src/amsc/semantic_roles.py) separates them: every heading gets a
`semantic_role` (`section` / `group` / `item` / `display`) and the `opens_section` that role
implies, via `models.ROLE_OPENS_SECTION` — the single contract every consumer of
`section_path` depends on. Four rules decide it, each one claim about layout or orthography;
section numbering overrides all of them, because a heading opening `7.` or `2.4` is the
document's own statement of its structure. `SectionHierarchyBuilder` then touches the stack
only for a heading marked `opens_section`, and a corpus carrying no decision (`None`) opens
at every heading exactly as before. The contract: **`section_path` changes only at a
hierarchy-bearing unit**. Read it as a structural guarantee, not a measurement — the builder
touches the stack only when `opens_section is not False`, so the reported "0 violations" holds
even if every role decision were inverted. What it does *not* guarantee is that the roles are
right, and nothing downstream cross-checks them: `heading_level` is derived from the same flag,
and `role_reason` is computed but never written to `RawDocumentUnit`.

**`section_path` is not display metadata.** `thresholds.py` scopes each boundary's adaptive
threshold by the longest common prefix of the two units' `section_path`, so a change that only
rewrites paths still moves V2/V3/V4 boundaries. It *is* inert for the three chunk-benchmark arms
and for BM25, which index chunk text only — do not generalise from those runs. Downstream,
`chat_rag`'s contextual enhancer joins `section_paths[0]` into a `Section: …` line that reaches
the indexed text.

`structural_qa.check_section_consistency` reads that same invariant through one predicate,
`_opens_section(unit)`: a unit that opens a section must be the tail of its own path, and a unit
that does not must carry the previous unit's path unchanged. Before it did, the linter demanded
the tail of *every* heading and reported 260 (kkb-2024) and 322 (kkb-2022) HIGH findings against
the role model working correctly — while excusing the unit after a label from any check at all.
Totals on a role-free corpus are unchanged, which is what makes the predicate safe.

`heading_levels.assign_heading_levels` exists because PyMuPDF4LLM's layout backend writes
`##` for every section-header box: all 508 kkb-2024 headings arrived at level 2, so each
evicted the one before it and every `section_path` was one element long. Levels come from
*relative* type size, with two overrides that both say the same thing — the document's own
numbering outranks its typography: an unnumbered heading may not out-rank the numbered one
enclosing it (a standfirst is routinely set larger than its chapter title), and two numbered
headings at the same numbering depth are siblings whatever size they are printed at. A third
override comes from the role pass rather than from numbering: **a run of `group` keys sits at
one tier**, because a key partitions the section it sits in and two keys of one partition are
siblings however each is printed. Without it kkb-2024's timeline, whose year labels are set
at 20pt and 9pt on the same page, read as `8. KİLOMETRE TAŞLARI > 1995 > 2009`. The run is
closed by the next heading that is not a key, and a key printed deeper than the one that
opened the run (`2.4` under `2`) keeps its own tier. Levels
are anchored to the document's shallowest heading, so a genuinely flat corpus comes out
unchanged, and tiers past the schema's sixth level merge **into** it. That merge direction
was reversed once, on measurement: merging the shallow end was right while item labels still
consumed tiers, and wrong once roles kept them off the stack (63.6% vs 48.1% of kkb-2024
content units naming their chapter; identical on kkb-2022, where no path is deep enough for
the cap to bite). **Beware the metric itself**: an earlier version counted every `^\d+\.`
heading as a chapter, so local list numbering inflated it to 100% and hid the defect it was
meant to measure. Chapters are now the longest strictly increasing run of depth-1 section
numbers in reading order — 33 on each corpus.

A canonical re-extraction invalidates every gold set pinned to the old sha.
[gold_repin.py](src/amsc/gold_repin.py) carries a gold set across **only** when every
evidence unit id still resolves to the same page and byte-identical text; otherwise it
refuses and the key needs re-authoring. Provenance is written to a sibling
`.provenance.json` because `RetrievalGoldSet` forbids unknown keys.

## Architecture

Pipeline (`docs/implementasyon-plani.md` has the full version-by-version breakdown):

```
canonical JSONL → strict validation → heading attachment → rendered-token hard-split
planning → cache-aware boundary embedding → semantic shift features → threshold
estimation → interval selection → non-semantic short-tail cleanup → (V4) semantic-safe
merge → configured-counter hard-cap invariant → chunks.jsonl + boundaries.jsonl
```

**Versions are cumulative and each adds exactly one algorithmic difference.** V1 fixed
threshold → V2 hierarchical adaptive threshold → V3 multi-scale `1↔1`/`2↔2`/`3↔3` shift →
V4 threshold-relative selection + soft structural support + semantic-safe merge. V1–V3 share
`chunker.py`; **V4 has its own orchestration** ([v4_chunker.py](src/amsc/v4_chunker.py),
[v4_selection.py](src/amsc/v4_selection.py), [structure.py](src/amsc/structure.py),
[strength.py](src/amsc/strength.py), [merge.py](src/amsc/merge.py)) precisely so V4
conditionals never leak into the V1–V3 facades. Keep it that way — do not add version
branches to [chunker.py](src/amsc/chunker.py).

Seams that exist to be swapped without touching orchestration:

- `TokenCounter` ([tokenization.py](src/amsc/tokenization.py)) is deliberately independent of
  the embedding tokenizer. When the production tokenizer is learned, only the adapter changes.
- `SemanticThresholdEstimator` ([thresholds.py](src/amsc/thresholds.py)) and
  `SemanticFeatureExtractor` ([features.py](src/amsc/features.py)) are protocols; the selector
  is agnostic to which implementation runs.
- Boundary embedding and retrieval embedding are **separate interfaces with separate cache
  namespaces** (`.cache/boundary-embeddings` vs `.cache/retrieval-benchmark-v1`). The
  retrieval evaluator must never reach into the boundary embedder.

**The chunk-benchmark layer is chunker-agnostic on purpose.**
[chunk_benchmark.py](src/amsc/chunk_benchmark.py) compares three arms — `markdown_recursive`
([markdown_chunker.py](src/amsc/markdown_chunker.py)), `hybrid_h1`
([hybrid_chunker.py](src/amsc/hybrid_chunker.py)) and `structure_first`
([structural_chunker.py](src/amsc/structural_chunker.py)) — over one frozen canonical input
with BM25-only retrieval, so only the chunker varies. It **imports** the frozen metric
functions from `retrieval_benchmark.py` rather than restating them, which imposes four
conditions documented at the top of the module (frozen `RetrievalHit`, `top_ks == [1,3,5]`,
`int`/`float` casts, `documents` passed separately). Chunk rows are reduced to canonical unit
ids before scoring (`normalize_unit_ids_for_retrieval`) because `_to_document` filters unknown
ids and would silently leave fragment-bearing chunks unscorable.
[chunk_mapping.py](src/amsc/chunk_mapping.py) is the single chunk↔unit resolver — an
offset/provenance/normalized/sequential ladder that reports `unmapped` rather than guessing —
and both [chunk_quality.py](src/amsc/chunk_quality.py) and
[chunk_viewer.py](src/amsc/chunk_viewer.py) consume it. `chunk_quality` subtracts a
`lint(units, [])` parser baseline before comparing arms, because most `structural_qa` findings
are properties of the parser and identical across arms.

Config ([config.py](src/amsc/config.py)): all models are `extra="forbid"`; `load_config()`
dispatches on `algorithm.version` to `V1Config`/`V2Config`/`V3Config`/`V4Config`. Each config
exposes a `config_hash` (sha256 of the canonical JSON dump, truncated to 16) and every run
writes `resolved-config.json` alongside its outputs. Adding a config key means adding it to
the strict model.

Canonical input contract ([io.py](src/amsc/io.py), [models.py](src/amsc/models.py)): exactly
one `document_id` per file, unique `unit_id`, unique and strictly increasing `order`. The
checkpoint preparers emit `.units.jsonl` plus same-basename `.manifest.json` (source PDF
SHA256, pymupdf4llm version, extraction params) and `.visual-provenance.jsonl` (lossless
picture-region provenance; picture regions become single `paragraph` units rather than
extending the canonical schema).

## Working conventions

**Frozen artifacts are load-bearing.** [evaluation/](evaluation/), `data/*.units.jsonl` and
`tests/fixtures/*-golden/` are checked-in results, not scratch space. Git tags mark each
freeze (`v1-baseline`, `v2-adaptive-threshold`, `v3-multiscale-context`,
`phase3a-failure-analysis`, `phase3b-scale-calibration-negative-result`,
`phase3c-development-result`, `phase4-retrieval-development-benchmark`,
`phase5-holdout-validation`). Integration tests under [tests/integration/](tests/integration/)
assert **byte-identical** goldens and pinned metric values — e.g.
[test_v5_research_frozen.py](tests/integration/test_v5_research_frozen.py) checks that B0
equals the authoritative V3 output byte-for-byte, and pins floats like `0.5517241379310344`.
If such a test fails, the regression is in the code; do not regenerate the golden to make it
pass unless the user explicitly asks for a re-freeze.

Benchmark configs pin `units_sha256` and the runners verify it. Changing canonical input
invalidates every downstream frozen result.

**This repo shares one Python environment with the sibling `chat_rag` app, which pins
`amsc-poc` to a GitHub commit** (`chat_rag/requirements.txt:3`). Running
`pip install -r chat_rag/requirements.txt` silently replaces your editable install with
that pinned build, so local `src/amsc/` edits stop taking effect and no error is raised.
After touching chat_rag dependencies, re-run `py -3.11 -m pip install -e .` here and
confirm with `py -3.11 -c "import amsc; print(amsc.__file__)"` — it must resolve inside
this repo, not `site-packages`.

**Never run the retrieval benchmarks with their default `--output`.** In
`configs/holdout-benchmark-v1.yaml` the `candidates.{v3,v4,c3}.chunks` paths point *into*
`evaluation/holdout-kkb-2022/retrieval-benchmark/results/` — the same directory
`amsc.run_holdout_benchmark` writes to by default, so a default run overwrites its own frozen
inputs. It has already happened once: the checked-in `results/v3/chunks.jsonl` and
`results/v4/chunks.jsonl` are in the benchmark's slim 5-key corpus format
(`chunk_id`/`pages`/`text`/`token_count`/`unit_ids`), while `results/c3/chunks.jsonl` still
carries the original 19-key chunker schema. Always pass an explicit `--output` under
`artifacts/`.

**`evaluate_checkpoint()` in [evaluation.py](src/amsc/evaluation.py) is the single
authoritative metric.** Layers like [failure_analysis.py](src/amsc/failure_analysis.py)
re-derive diagnostics but assert equality against the persisted `metrics.json`. Never let a
diagnostic layer change prediction classification, HIGH/REVIEW semantics, region filtering, or
exact/±1 matching. The primary metric is ±1 one-to-one F1 over the 15 HIGH gold boundaries;
exact F1 is a secondary diagnostic; `review` records are excluded from the primary metric.

**Determinism is a hard requirement.** No wall-clock, no RNG, no set-iteration order on output
paths. JSON/JSONL is written with `newline="\n"`, `ensure_ascii=False` and (for JSON)
`sort_keys=True`. Tie-breaks are explicitly frozen orderings — see the merge proposal ranking
in `docs/implementasyon-plani.md`.

**Claim discipline.** All numeric parameters (`0.20` fixed threshold, `160/700/900/1126` token
limits, `0.35/0.26/0.39` scale weights, `0.80/0.20` selection weights, `0.04` relaxation,
`0.12` semantic floor, `0.50` merge guard) are PoC starting values, marked
`tuning_status: poc_initial_not_optimized`. They were **not** tuned against the checkpoint.
Likewise: `hard_max_tokens=1126` is guaranteed only under the configured PoC counter
(`hard_cap_semantics=configured_poc_counter_only`), the `legacy` benchmark candidate is a
compatibility adapter for the public `MurselTasgin/chat_rag` code and not KKB's production
chunker, and **no production winner has been declared**. Preserve these hedges in code,
configs, docs and summaries rather than smoothing them into stronger claims.

Out of scope by decision (`docs/kararlar-ve-baglam.md`): improving PDF/DOCX parsing quality,
per-boundary LLM calls, reproducing the production system, redesigning RAG/reranking. A5
contextualization is intentionally unimplemented
(`contextualization.role: optional_ablation_not_implemented`).

Commit messages use `feat: …` for algorithm versions and `checkpoint: …` for freezes.

## Reference

- [Bağlam ve kararlar](docs/kararlar-ve-baglam.md) — per-version implementation decisions and constraints
- [Seçilen çözüm](docs/secilen-cozum.md) — the chosen approach
- [İmplementasyon planı](docs/implementasyon-plani.md) — module map, data flow, per-version algorithm detail
- [Proje raporu](docs/buddy-proje-raporu.md) — phase-by-phase results and current status
