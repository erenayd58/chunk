"""Deep Analysis as one in-memory pipeline -- the product-facing entry point.

Everything :mod:`amsc.deep_run` used to do between "load the units" and
"write the tree" lives here, so an application that needs chunks without
files (the ``chat_rag`` ingestion path) calls :func:`chunk_document` and gets
rows plus a JSON-serialisable report, and the CLI stays a thin writer over
the same function. There is exactly one Deep Analysis implementation.

The stages, in order, each free to be skipped without changing the ones
before it:

1. **Standard** -- the frozen structure-first walk (``structural_chunker``).
2. **Proposer** -- one bounded prompt per section that still has a choice,
   collected in parallel through the shared cache-aware collector.
3. **Selector** -- the lexicographic DP under the quality contract; with no
   votes it is a pure function of the canonical and never worse than
   Standard on any smell type.
4. **Verifier** -- every change group the votes introduced is shown twice,
   in both orders, and kept only on unanimity; a reverted group falls back
   to the deterministic partition.
5. **Measure** -- ``boundary_quality.compare`` against Standard, so the
   report carries the same numbers the selector optimised.

**Failure policy.** The LLM is advisory. A missing key, an unreachable
endpoint, a malformed answer or a timed-out call each degrade to the
deterministic partition for the affected scope and are recorded in the
report's ``status`` -- the caller never gets an exception for a provider
problem and never gets a partition below the contract. A structural error
(bad canonical, hard-cap breach) still raises, because that is a bug.

No model is embedded: the settings name the models and the endpoint, and
the key is read from the environment at request time by the provider,
never by this module.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from . import boundary_quality as bq
from . import deep_analysis as da
from . import deep_proposer as dp
from . import deep_verifier as dv
from .agentic_chunker import CallOutcome
from .llm_boundary_judge import BoundaryJudgeModel, OpenAICompatibleJudgeProvider
from . import table_search_text
from .models import RawDocumentUnit
from .structural_chunker import _sections
from .structural_chunker import chunk_units as structural_chunk_units
from .tokenization import TiktokenTokenCounter, TokenCounter

DEFAULT_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
#: Self-hostable reference candidate. Nothing in the architecture depends on it.
REFERENCE_MODEL = "qwen/qwen3-30b-a3b-instruct-2507"

MODE_STANDARD = "standard"
MODE_DEEP = "deep"

#: ``status`` values a product caller can branch on.
STATUS_OK = "ok"  # every requested stage ran with a provider or a cache
STATUS_DETERMINISTIC = "deterministic"  # the LLM was not requested
STATUS_FALLBACK_NO_PROVIDER = "fallback_no_provider"  # key/endpoint missing
STATUS_FALLBACK_PROVIDER_ERROR = "fallback_provider_error"  # every call failed
STATUS_DEGRADED = "degraded"  # some calls failed; their sections stayed deterministic


@dataclass(frozen=True)
class DeepAnalysisSettings:
    """Everything a deployment configures, in one place, no secrets.

    ``proposer_model`` / ``verifier_model`` are ids the endpoint understands;
    ``api_key_env`` names the variable the provider reads at request time.
    ``verifier_model`` defaults to the proposer's, but a different family is
    the better choice when one is available -- a proposer's blind spot is
    the same model's blind spot as verifier.
    """

    config: da.DeepConfig = da.DeepConfig()
    use_llm: bool = True
    verify: bool = True
    proposer_model: str = REFERENCE_MODEL
    verifier_model: str | None = None
    endpoint: str = DEFAULT_ENDPOINT
    api_key_env: str = "OPENROUTER_API_KEY"
    concurrency: int = 8
    timeout_seconds: float = 120.0
    encoding: str = "cl100k_base"

    @property
    def effective_verifier_model(self) -> str:
        return self.verifier_model or self.proposer_model


@dataclass
class DeepAnalysisResult:
    """Rows plus every artifact the runner writes, in memory."""

    rows: list[dict[str, Any]]
    standard_rows: list[dict[str, Any]]
    audit: dict[str, Any]
    quality: dict[str, Any]
    summary: dict[str, Any]
    status: str
    mode: str
    proposer_plans: list[dp.PlannedProposal] = field(default_factory=list)
    proposer_outcomes: list[CallOutcome] = field(default_factory=list)
    proposer_audit: list[dp.ProposalOutcome] = field(default_factory=list)
    votes: dict[str, da.BoundaryVote] = field(default_factory=dict)
    verifier_checks: list[dv.PlannedComparison] = field(default_factory=list)
    verifier_outcomes: list[CallOutcome] = field(default_factory=list)
    verifier_verdicts: list[dv.GroupVerdict] = field(default_factory=list)
    deterministic_cuts: dict[int, tuple[int, ...]] = field(default_factory=dict)
    error: str | None = None


def build_providers(
    settings: DeepAnalysisSettings,
) -> tuple[BoundaryJudgeModel | None, BoundaryJudgeModel | None]:
    """The proposer and verifier transports, or ``(None, None)`` without LLM.

    Raises ``RuntimeError`` when the key variable is empty, so the caller can
    decide between refusing (a CLI live run) and falling back (the product).
    The key itself is never read here -- only whether it is set.
    """
    if not settings.use_llm:
        return None, None
    if not os.environ.get(settings.api_key_env, "").strip():
        raise RuntimeError(
            f"{settings.api_key_env} is not set; Deep Analysis cannot call a "
            "model without it (the key is read at request time and never stored)"
        )
    proposer = OpenAICompatibleJudgeProvider(
        settings.proposer_model,
        endpoint=settings.endpoint,
        api_key_env=settings.api_key_env,
        timeout_seconds=settings.timeout_seconds,
    )
    verifier: BoundaryJudgeModel | None = None
    if settings.verify:
        verifier = OpenAICompatibleJudgeProvider(
            settings.effective_verifier_model,
            endpoint=settings.endpoint,
            api_key_env=settings.api_key_env,
            timeout_seconds=settings.timeout_seconds,
        )
    return proposer, verifier


def run_standard(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    config: da.DeepConfig = da.DeepConfig(),
) -> list[dict[str, Any]]:
    """The Standard partition at the Deep config -- the frozen walk, untouched."""
    return structural_chunk_units(
        units,
        counter=counter,
        min_tokens=config.min_tokens,
        target_tokens=config.target_tokens,
        soft_max_tokens=config.soft_max_tokens,
        hard_max_tokens=config.hard_max_tokens,
        respect_semantic_roles=config.respect_semantic_roles,
    )


def _status(
    *,
    use_llm: bool,
    provider: Any | None,
    cache: Mapping[str, str] | None,
    proposer_audit: Sequence[dp.ProposalOutcome],
) -> str:
    if not use_llm:
        return STATUS_DETERMINISTIC
    if not proposer_audit:
        return STATUS_OK
    transports = {entry.transport for entry in proposer_audit}
    answered = {entry.transport for entry in proposer_audit if entry.transport in ("ok", "cached")}
    if not answered:
        return STATUS_FALLBACK_PROVIDER_ERROR
    if transports - {"ok", "cached"}:
        return STATUS_DEGRADED
    return STATUS_OK


def run_deep_analysis(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    settings: DeepAnalysisSettings = DeepAnalysisSettings(),
    provider: BoundaryJudgeModel | None = None,
    verifier_provider: BoundaryJudgeModel | None = None,
    cache: Mapping[str, str] | None = None,
    verifier_cache: Mapping[str, str] | None = None,
) -> DeepAnalysisResult:
    """Plan, collect, select, verify, measure -- and return everything.

    ``provider=None`` with a ``cache`` is a replay: a prompt the cache does
    not hold is a ``replay_miss``, deterministically equivalent to the
    original run's provider error. ``settings.use_llm=False`` skips the
    proposer and verifier entirely.
    """
    config = settings.config
    timing: dict[str, float] = {}

    started = time.perf_counter()
    standard = run_standard(units, counter=counter, config=config)
    timing["standard"] = time.perf_counter() - started

    plans: list[dp.PlannedProposal] = []
    outcomes: list[CallOutcome] = []
    votes: dict[str, da.BoundaryVote] = {}
    proposer_audit: list[dp.ProposalOutcome] = []
    call_seconds = 0.0
    if settings.use_llm:
        plans = dp.plan_calls(units, counter=counter, config=config)
        started = time.perf_counter()
        outcomes = dp.collect(
            plans, provider=provider, cache=cache, concurrency=settings.concurrency
        )
        call_seconds = time.perf_counter() - started
        votes, proposer_audit = dp.votes_from_outcomes(plans, outcomes)

    started = time.perf_counter()
    rows, audit = da.chunk_units(units, counter=counter, config=config, votes=votes)
    select_seconds = time.perf_counter() - started

    verifier_summary: dict[str, Any] | None = None
    verify_seconds = 0.0
    checks: list[dv.PlannedComparison] = []
    check_outcomes: list[CallOutcome] = []
    verdicts: list[dv.GroupVerdict] = []
    deterministic_cuts: dict[int, tuple[int, ...]] = {}
    if settings.verify and votes:
        # The deterministic partition is the baseline every proposal is judged
        # against, and the fallback for every group the verifier does not keep.
        _base_rows, base_audit = da.chunk_units(units, counter=counter, config=config)
        sections = _sections(
            units, counter, config.hard_max_tokens, config.respect_semantic_roles
        )
        base_cuts = {int(k): tuple(v) for k, v in base_audit["cuts_by_section"].items()}
        deterministic_cuts = dict(base_cuts)
        proposed_cuts = {int(k): tuple(v) for k, v in audit["cuts_by_section"].items()}
        groups: list[dv.ChangeGroup] = []
        for index, section in enumerate(sections):
            groups.extend(
                dv.change_groups(
                    base_cuts.get(index, ()),
                    proposed_cuts.get(index, ()),
                    len(section.pieces),
                    section_index=index,
                    heading=section.heading,
                )
            )
        checks = dv.plan_comparisons(sections, groups, config=config)
        started = time.perf_counter()
        check_outcomes = dv.collect(
            checks,
            provider=verifier_provider,
            cache=verifier_cache,
            concurrency=settings.concurrency,
        )
        verify_seconds = time.perf_counter() - started
        verdicts = dv.decide(groups, checks, check_outcomes)
        accepted = {verdict.group_key: verdict.accepted for verdict in verdicts}
        override = {
            index: dv.merge_cuts(
                base_cuts.get(index, ()),
                proposed_cuts.get(index, ()),
                [group for group in groups if group.section_index == index],
                accepted,
            )
            for index in {group.section_index for group in groups}
        }
        started = time.perf_counter()
        rows, audit = da.chunk_units(
            units, counter=counter, config=config, votes=votes, cut_override=override
        )
        select_seconds += time.perf_counter() - started
        verifier_summary = dv.summarise(verdicts)

    report = bq.compare(units, standard, rows, counter=counter, config=config.quality())
    smells = lambda totals: sum(totals[key] for key in bq.SMELL_TYPES)  # noqa: E731

    mode = (
        "deterministic" if not settings.use_llm else ("live" if provider else "replay")
    )
    status = _status(
        use_llm=settings.use_llm, provider=provider, cache=cache, proposer_audit=proposer_audit
    )
    # What the LLM layer changed in the final partition, counted on final
    # cuts: sections whose final cuts differ from the deterministic ones.
    final_cuts = {int(k): tuple(v) for k, v in audit["cuts_by_section"].items()}
    llm_moved_sections = sum(
        1 for index, cuts in final_cuts.items()
        if deterministic_cuts and deterministic_cuts.get(index, ()) != cuts
    ) if deterministic_cuts else 0

    summary = {
        "document_id": units[0].document_id,
        "unit_count": len(units),
        "mode": mode,
        "status": status,
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
        "llm_effect": {
            "sections_changed_by_llm": llm_moved_sections,
            "verifier_accepted_groups": (verifier_summary or {}).get("accepted", 0),
            "verifier_reverted_groups": (verifier_summary or {}).get("reverted", 0),
        },
        "proposer": dp.summarise(proposer_audit) if settings.use_llm else None,
        "verifier": verifier_summary,
        "verifier_model_id": getattr(verifier_provider, "model_id", None),
        "timing_seconds": {
            "standard": round(timing["standard"], 3),
            "llm_calls": round(call_seconds, 3),
            "verifier_calls": round(verify_seconds, 3),
            "selection": round(select_seconds, 3),
        },
        "claim_discipline": {
            "tuning_status": da.TUNING_STATUS,
            "note": "Results are model-dependent and replay-deterministic only; "
            "no production winner is declared.",
        },
    }
    return DeepAnalysisResult(
        rows=rows,
        standard_rows=standard,
        audit=audit,
        quality=report,
        summary=summary,
        status=status,
        mode=mode,
        proposer_plans=plans,
        proposer_outcomes=outcomes,
        proposer_audit=proposer_audit,
        votes=votes,
        verifier_checks=checks,
        verifier_outcomes=check_outcomes,
        verifier_verdicts=verdicts,
        deterministic_cuts=deterministic_cuts,
    )


# --------------------------------------------------------------------------
# the product entry point
# --------------------------------------------------------------------------


@dataclass
class ProductChunkingResult:
    """What an application gets back: rows, a mode, a status and a report.

    ``rows`` follow the structural chunker's row schema in every mode, so a
    consumer indexes them the same way whatever the user picked at upload.
    ``report`` is JSON-serialisable and carries counts only -- no prompt
    text, no document text beyond what the rows already hold, no key.
    """

    mode: str
    status: str
    rows: list[dict[str, Any]]
    report: dict[str, Any]
    deep: DeepAnalysisResult | None = None
    error: str | None = None


def chunk_document(
    units: Sequence[RawDocumentUnit],
    *,
    mode: str = MODE_STANDARD,
    settings: DeepAnalysisSettings = DeepAnalysisSettings(),
    counter: TokenCounter | None = None,
    provider: BoundaryJudgeModel | None = None,
    verifier_provider: BoundaryJudgeModel | None = None,
    cache: Mapping[str, str] | None = None,
    verifier_cache: Mapping[str, str] | None = None,
) -> ProductChunkingResult:
    """Chunk one document in the mode the user chose at upload.

    ``standard`` is the frozen structure-first walk. ``deep`` runs the full
    pipeline; when no provider is given one is built from ``settings``, and
    if that is impossible (no key) the deterministic contract runs alone and
    ``status`` says so. Deep never returns a partition that is worse than
    Standard on any smell type, and with no usable model answer it returns
    the deterministic partition -- the LLM is advisory, the contract is not.
    """
    if mode not in (MODE_STANDARD, MODE_DEEP):
        raise ValueError(f"unknown chunking mode {mode!r}; expected standard or deep")
    counter = counter or TiktokenTokenCounter(settings.encoding)
    if mode == MODE_STANDARD:
        rows = run_standard(units, counter=counter, config=settings.config)
        return ProductChunkingResult(
            mode=mode,
            status=STATUS_OK,
            rows=rows,
            report={
                "mode": mode,
                "status": STATUS_OK,
                "chunk_count": len(rows),
                "config": {**settings.config.__dict__},
                "uses_llm": False,
            },
        )

    error: str | None = None
    effective = settings
    if settings.use_llm and provider is None and not cache:
        try:
            provider, built_verifier = build_providers(settings)
            if verifier_provider is None:
                verifier_provider = built_verifier
        except RuntimeError as exc:
            error = str(exc)
            effective = replace(settings, use_llm=False)
    elif settings.use_llm and settings.verify and verifier_provider is None and provider is not None:
        verifier_provider = provider

    result = run_deep_analysis(
        units,
        counter=counter,
        settings=effective,
        provider=provider,
        verifier_provider=verifier_provider,
        cache=cache,
        verifier_cache=verifier_cache,
    )
    status = STATUS_FALLBACK_NO_PROVIDER if error else result.status
    result.status = status
    result.summary["status"] = status
    if error:
        result.error = error
        result.summary["fallback_reason"] = error
    # A chunk carrying a table gets a second, searchable representation of it.
    # Deep only: Standard returns above, before this point, so the frozen
    # structure-first arm is byte-identical to what it always was. ``text`` is
    # untouched, so the answer model and every citation still read the table
    # exactly as the document wrote it.
    enriched = table_search_text.enrich_rows(result.rows, units)
    report = {
        **result.summary,
        "uses_llm": bool(result.votes),
        "table_search_text_chunks": enriched,
    }
    return ProductChunkingResult(
        mode=mode, status=status, rows=result.rows, report=report, deep=result, error=error
    )
