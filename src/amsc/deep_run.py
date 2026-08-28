"""Runner for Deep Analysis: plan, collect, select, measure, write.

One entry point for the three ways the mode is exercised, which differ only in
where the votes come from:

    --no-llm            the deterministic contract alone (zero calls)
    --replay DIR        votes rebuilt from a previous run's cached responses
    --model ID          live calls through an OpenAI-compatible endpoint

All three write the same tree, so a report never has to ask which one produced
it. The comparison against Standard is computed here with the same
``boundary_quality`` functions the selector optimises, and the artifact records
both the tiered verdicts and the strict ones.

Artifacts never contain prompt text or an API key -- ``calls.jsonl`` carries
``prompt_sha256`` and the boundary plan, ``responses.jsonl`` the raw model
output beside that hash. A replay reconstructs prompts from the same canonical
and config, so a changed prompt template is a cache miss rather than a silent
mismatch.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import boundary_quality as bq
from . import deep_analysis as da
from . import deep_proposer as dp
from .agentic_chunker import CallOutcome, load_response_cache
from .io import load_jsonl_units
from .llm_boundary_judge import OpenAICompatibleJudgeProvider
from .structural_chunker import chunk_units as structural_chunk_units
from .tokenization import TiktokenTokenCounter

DEFAULT_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
#: Self-hostable reference candidate. Nothing in the architecture depends on it.
REFERENCE_MODEL = "qwen/qwen3-30b-a3b-instruct-2507"


def refuse_output(output: Path) -> None:
    resolved = output.resolve()
    for part in resolved.parts:
        if part == "evaluation":
            raise SystemExit(f"refusing to write into evaluation/: {resolved}")
    for ancestor in [resolved, *resolved.parents]:
        if (ancestor / "benchmark-summary.json").is_file():
            raise SystemExit(f"refusing to write into the frozen benchmark tree at {ancestor}")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def run(
    units_path: Path,
    output: Path,
    *,
    config: da.DeepConfig,
    encoding: str = "cl100k_base",
    provider: Any | None = None,
    cache: Mapping[str, str] | None = None,
    use_llm: bool = True,
    concurrency: int = 8,
) -> dict[str, Any]:
    refuse_output(output)
    counter = TiktokenTokenCounter(encoding)
    units = load_jsonl_units(units_path)

    standard = structural_chunk_units(
        units,
        counter=counter,
        min_tokens=config.min_tokens,
        target_tokens=config.target_tokens,
        soft_max_tokens=config.soft_max_tokens,
        hard_max_tokens=config.hard_max_tokens,
        respect_semantic_roles=config.respect_semantic_roles,
    )

    plans: list[dp.PlannedProposal] = []
    outcomes: list[CallOutcome] = []
    votes: dict[str, da.BoundaryVote] = {}
    proposer_audit: list[dp.ProposalOutcome] = []
    call_seconds = 0.0
    if use_llm:
        plans = dp.plan_calls(units, counter=counter, config=config)
        started = time.perf_counter()
        outcomes = dp.collect(plans, provider=provider, cache=cache, concurrency=concurrency)
        call_seconds = time.perf_counter() - started
        votes, proposer_audit = dp.votes_from_outcomes(plans, outcomes)

    started = time.perf_counter()
    rows, audit = da.chunk_units(units, counter=counter, config=config, votes=votes)
    select_seconds = time.perf_counter() - started

    report = bq.compare(units, standard, rows, counter=counter, config=config.quality())
    smells = lambda totals: sum(totals[key] for key in bq.SMELL_TYPES)  # noqa: E731

    summary = {
        "document_id": units[0].document_id,
        "units_file": str(units_path),
        "unit_count": len(units),
        "mode": "deterministic" if not use_llm else ("live" if provider else "replay"),
        "model_id": getattr(provider, "model_id", None),
        "prompt_template_version": dp.PROMPT_TEMPLATE_VERSION,
        "config": {**config.__dict__},
        "chunk_count": {"standard": len(standard), "deep": len(rows)},
        "smell_total": {
            "standard": smells(report["totals"]["standard"]),
            "deep": smells(report["totals"]["deep"]),
        },
        "totals": report["totals"],
        "verdicts_tiered": report["verdicts_tiered"],
        "structural_regression_count": report["structural_regression_count"],
        "strict_regression_count": report["strict_regression_count"],
        "size_trade_count": report["size_trade_count"],
        "change_group_count": report["change_group_count"],
        "selection": {
            key: audit[key]
            for key in (
                "sections_moved", "sections_reverted", "revert_reasons",
                "size_trade_count", "vote_count", "forbidden_vote_count",
            )
        },
        "proposer": dp.summarise(proposer_audit) if use_llm else None,
        "timing_seconds": {
            "llm_calls": round(call_seconds, 3),
            "selection": round(select_seconds, 3),
        },
        "claim_discipline": {
            "tuning_status": da.TUNING_STATUS,
            "note": "Results are model-dependent and replay-deterministic only; "
            "no production winner is declared.",
        },
    }

    _write_jsonl(output / "chunks.jsonl", rows)
    _write_json(output / "selection-audit.json", audit)
    _write_json(output / "quality-vs-standard.json", report)
    _write_json(output / "summary.json", summary)
    if use_llm:
        _write_jsonl(
            output / "proposer" / "calls.jsonl",
            [
                {
                    "call_id": plan.call_id,
                    "section_index": plan.section_index,
                    "prompt_sha256": plan.prompt_sha256,
                    "prompt_chars": plan.prompt_chars,
                    "boundaries": [
                        {
                            "label": boundary.label,
                            "cut_after_unit_id": boundary.cut_after_unit_id,
                            "cut_before_unit_id": boundary.cut_before_unit_id,
                        }
                        for boundary in plan.boundaries
                    ],
                }
                for plan in plans
            ],
        )
        _write_jsonl(
            output / "proposer" / "responses.jsonl",
            [
                {
                    "prompt_sha256": plan.prompt_sha256,
                    "call_id": plan.call_id,
                    "model_id": getattr(provider, "model_id", None),
                    "status": outcome.status,
                    "response": outcome.response,
                }
                for plan, outcome in zip(plans, outcomes)
                if outcome.response is not None
            ],
        )
        _write_jsonl(
            output / "proposer" / "audit.jsonl",
            [entry.__dict__ for entry in proposer_audit],
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.deep_run",
        description="Run Deep Analysis over a canonical corpus and measure it.",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--encoding", default="cl100k_base")
    parser.add_argument("--no-llm", action="store_true", help="deterministic contract only")
    parser.add_argument("--replay", type=Path, help="a previous run's proposer/ directory")
    parser.add_argument("--model", help=f"live model id (reference: {REFERENCE_MODEL})")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--min-tokens", type=int, default=160)
    parser.add_argument("--target-tokens", type=int, default=700)
    parser.add_argument("--soft-max-tokens", type=int, default=900)
    parser.add_argument("--hard-max-tokens", type=int, default=1126)
    args = parser.parse_args(argv)

    if args.model and args.no_llm:
        raise SystemExit("--model and --no-llm are mutually exclusive")

    cache: dict[str, str] = {}
    if args.replay:
        responses = args.replay / "responses.jsonl"
        if not responses.is_file():
            responses = args.replay
        cache = load_response_cache(responses)
        if not cache:
            raise SystemExit(f"no cached responses under {args.replay}")

    provider = None
    if args.model:
        if not os.environ.get(args.api_key_env, "").strip():
            raise SystemExit(
                f"{args.api_key_env} is not set; refusing to start a live run "
                "(the key is read at request time and never stored)"
            )
        provider = OpenAICompatibleJudgeProvider(
            args.model, endpoint=args.endpoint, api_key_env=args.api_key_env
        )

    summary = run(
        args.input,
        args.output,
        config=da.DeepConfig(
            min_tokens=args.min_tokens,
            target_tokens=args.target_tokens,
            soft_max_tokens=args.soft_max_tokens,
            hard_max_tokens=args.hard_max_tokens,
        ),
        encoding=args.encoding,
        provider=provider,
        cache=cache,
        use_llm=not args.no_llm,
        concurrency=args.concurrency,
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "totals"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
