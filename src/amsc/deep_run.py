"""Runner for Deep Analysis: plan, collect, select, measure, write.

One entry point for the three ways the mode is exercised, which differ only in
where the votes come from:

    --no-llm            the deterministic contract alone (zero calls)
    --replay DIR        votes rebuilt from a previous run's cached responses
    --model ID          live calls through an OpenAI-compatible endpoint

All three write the same tree, so a report never has to ask which one produced
it. The pipeline itself lives in :mod:`amsc.deep_pipeline`; this module only
reads the units, builds the providers and writes the artifacts, so the file
layout is the one thing it owns.

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
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import deep_analysis as da
from .agentic_chunker import load_response_cache
from .deep_pipeline import (
    DEFAULT_ENDPOINT,
    REFERENCE_MODEL,
    DeepAnalysisResult,
    DeepAnalysisSettings,
    run_deep_analysis,
)
from .io import load_jsonl_units
from .llm_boundary_judge import OpenAICompatibleJudgeProvider
from .tokenization import TiktokenTokenCounter

__all__ = ["DEFAULT_ENDPOINT", "REFERENCE_MODEL", "refuse_output", "run", "write_tree", "main"]


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


def write_tree(
    result: DeepAnalysisResult,
    output: Path,
    *,
    units_path: Path | None = None,
    provider: Any | None = None,
    verifier_provider: Any | None = None,
) -> dict[str, Any]:
    """Write one run's artifacts under ``output``; return the summary written."""
    summary = dict(result.summary)
    if units_path is not None:
        summary["units_file"] = str(units_path)
    _write_jsonl(output / "chunks.jsonl", result.rows)
    _write_json(output / "selection-audit.json", result.audit)
    _write_json(output / "quality-vs-standard.json", result.quality)
    _write_json(output / "summary.json", summary)
    if result.mode != "deterministic":
        plans, outcomes = result.proposer_plans, result.proposer_outcomes
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
            [entry.__dict__ for entry in result.proposer_audit],
        )
    if result.verifier_checks:
        checks, check_outcomes = result.verifier_checks, result.verifier_outcomes
        _write_jsonl(
            output / "verifier" / "calls.jsonl",
            [
                {
                    "call_id": plan.call_id,
                    "group_key": plan.group_key,
                    "section_index": plan.section_index,
                    "first": plan.first,
                    "prompt_sha256": plan.prompt_sha256,
                    "prompt_chars": plan.prompt_chars,
                }
                for plan in checks
            ],
        )
        _write_jsonl(
            output / "verifier" / "responses.jsonl",
            [
                {
                    "prompt_sha256": plan.prompt_sha256,
                    "call_id": plan.call_id,
                    "model_id": getattr(verifier_provider, "model_id", None),
                    "status": outcome.status,
                    "response": outcome.response,
                }
                for plan, outcome in zip(checks, check_outcomes)
                if outcome.response is not None
            ],
        )
        _write_jsonl(
            output / "verifier" / "verdicts.jsonl",
            [
                {
                    "group_key": verdict.group_key,
                    "section_index": verdict.section_index,
                    "accepted": verdict.accepted,
                    "reason": verdict.reason,
                    "votes": list(verdict.votes),
                }
                for verdict in result.verifier_verdicts
            ],
        )
    return summary


def run(
    units_path: Path,
    output: Path,
    *,
    config: da.DeepConfig,
    encoding: str = "cl100k_base",
    provider: Any | None = None,
    cache: Mapping[str, str] | None = None,
    use_llm: bool = True,
    verify: bool = False,
    verifier_provider: Any | None = None,
    verifier_cache: Mapping[str, str] | None = None,
    concurrency: int = 8,
) -> dict[str, Any]:
    refuse_output(output)
    counter = TiktokenTokenCounter(encoding)
    units = load_jsonl_units(units_path)
    settings = DeepAnalysisSettings(
        config=config, use_llm=use_llm, verify=verify, concurrency=concurrency, encoding=encoding
    )
    result = run_deep_analysis(
        units,
        counter=counter,
        settings=settings,
        provider=provider,
        verifier_provider=verifier_provider,
        cache=cache,
        verifier_cache=verifier_cache,
    )
    return write_tree(
        result,
        output,
        units_path=units_path,
        provider=provider,
        verifier_provider=verifier_provider,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.deep_run",
        description="Deep Analysis: deterministic contract, optional proposer and verifier",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--encoding", default="cl100k_base")
    parser.add_argument("--no-llm", action="store_true", help="deterministic contract only")
    parser.add_argument("--replay", type=Path, help="a previous run's proposer/ directory")
    parser.add_argument("--model", help=f"live model id (reference: {REFERENCE_MODEL})")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--verify", action="store_true", help="second pass over every changed group")
    parser.add_argument("--verifier-model", help="model for the verifier (defaults to --model)")
    parser.add_argument("--verifier-replay", type=Path, help="a previous run's verifier/ directory")
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

    verifier_cache: dict[str, str] = {}
    if args.verifier_replay:
        responses = args.verifier_replay / "responses.jsonl"
        verifier_cache = load_response_cache(
            responses if responses.is_file() else args.verifier_replay
        )
    verifier_provider = None
    if args.verify and (args.verifier_model or args.model):
        verifier_provider = OpenAICompatibleJudgeProvider(
            args.verifier_model or args.model,
            endpoint=args.endpoint,
            api_key_env=args.api_key_env,
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
        verify=args.verify,
        verifier_provider=verifier_provider,
        verifier_cache=verifier_cache,
        concurrency=args.concurrency,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
