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
| `amsc.prepare_full_checkpoint` | Full mixed-orientation document, requires `--layout-profile` |
| `amsc.checkpoint_qa` | Human-readable QA preview of canonical JSONL |
| `amsc.evaluation` | `worksheet` / `evaluate` — the **authoritative** boundary + chunk metrics |
| `amsc.failure_analysis` | Prediction/gold/merge audit, `--run ID=DIR` (diagnostic only) |
| `amsc.phase3c_research` | Phase 3C semantic comparators C0–C3 |
| `amsc.v5_research` | Phase 3B scale-calibration B0–B3 |
| `amsc.run_retrieval_benchmark` | Phase 4 retrieval benchmark on KKB 2024 |
| `amsc.run_holdout_benchmark` | Phase 5 holdout validation on KKB 2022 |

Both preparers are thin CLI wrappers over an in-memory core —
`checkpoint_adapter.extract_canonical_units()` and
`prepare_full_checkpoint.extract_full_canonical_units()` — which return a
`CanonicalExtraction` and write nothing. Applications that need canonical units without
files (the `chat_rag` ingestion path does) call those directly, so there is exactly one
canonical extraction implementation. `extract_full_canonical_units` takes the layout
profile as **optional**: omit it and spread pages keep the frozen extractor's own reading
order, which is correct for ordinary portrait documents.

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
