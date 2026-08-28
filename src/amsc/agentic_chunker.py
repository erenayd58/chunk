"""Agentic Chunker -- section-annotate, parallel vote collection, guided walk.

The fourth research arm beside markdown / hybrid / structure-first: the
structural chunker's own walk, with a generative LLM consulted about chunk
boundaries -- but never in charge of them. Three deterministic phases wrap
one parallel LLM phase:

1. **Call plan** (deterministic): every oversized section whose all-KEEP
   dry-walk would consult at least one multi-candidate window gets one
   prompt (or, past the caps, several deterministic segment prompts)
   marking EVERY internal non-label piece boundary as a ``[CANDIDATE Cn]``.
   Candidates are structure's own; the LLM never invents a position.
2. **Vote collection** (parallel): sections are independent, so all calls
   run concurrently. Responses are cached by ``sha256(prompt)`` -- a replay
   run reconstructs the prompts deterministically from canonical + config,
   verifies the hashes, and needs no provider. The same-prompt-set claim is
   deliberately narrow: it holds for the same canonical input AND the same
   config/candidate plan; changing caps, budgets or eligibility changes the
   plan, and the hash key makes a stale answer unusable rather than wrong.
3. **Parse + coherence guard** (deterministic): the strict window parser is
   reused unchanged. **In this arm, reason_code steers -- but only as a
   veto**: a SPLIT whose own reason says continuation
   (CONTINUATION / LIST_CONTINUATION / TABLE_CONTINUATION) is demoted to an
   abstain, so a self-contradictory vote can never create a cut. A call
   whose demoted SPLITs exceed ``max(coherence_min_violations,
   ceil(coherence_violation_ratio * candidate_count))`` is rejected whole
   (``coherence_violation``). Deep Analysis (:mod:`amsc.llm_boundary_judge`)
   keeps its stricter "reason never steers" contract; the divergence is
   intentional and this docstring is its record.
4. **Vote-guided walk** (deterministic): the structural walk, byte for
   byte, with one change -- a plain budget cut offering two or more
   admissible positions takes the LATEST effective-SPLIT-voted admissible
   position, else greedy. Label seams stay structure's own cuts; the hard
   cap assert stays; with no votes, an all-KEEP model, or any failure the
   output is byte-identical to :func:`amsc.structural_chunker.chunk_units`.

**Known coverage limit** (accepted, guarded): ``at_label`` fires on
``current >= min_tokens`` without the heading cost while admissibility
includes it, so an admissible stop sitting immediately before a label piece
the walk passed can be unvoted. Such stops are exactly the label-position
stops the plan never marks; the walk asserts that any unplanned admissible
stop is one of them, so a genuine candidate-coverage regression fails loud
instead of degrading silently.

**Artifacts carry no raw prompt text.** ``judge/calls.jsonl`` records the
candidate table and ``prompt_sha256`` only; replay rebuilds the prompt and
checks the hash. ``--dump-prompts`` exists for local debugging and must
point outside the artifact tree. No API key, endpoint, or wall-clock value
is ever written to an artifact.

All numeric knobs here are ``poc_initial_not_optimized``; results are
model-dependent and only replay-deterministic. No winner is declared.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .llm_boundary_judge import (
    DECISION_KEEP,
    DECISION_SPLIT,
    TUNING_STATUS,
    BoundaryJudgeModel,
    OpenAICompatibleJudgeProvider,
    build_window_prompt,
    candidate_labels,
    parse_window_decisions,
)
from .models import RawDocumentUnit
from .structural_chunker import (
    RENDER_SEPARATOR,
    Piece,
    Section,
    _render,
    _sections,
)
from .tokenization import TokenCounter

ARM_KIND = "agentic_structure_llm"
SELECTION_RULE = "latest_effective_split_else_greedy"

#: A SPLIT carrying one of these reasons contradicts itself; the vote is
#: demoted to an abstain (it can veto nothing into existence).
COHERENCE_VETO_REASONS = ("CONTINUATION", "LIST_CONTINUATION", "TABLE_CONTINUATION")

#: A KEEP carrying one of these reasons is incoherent but harmless (KEEP is
#: the safe default); it passes through and is only counted.
INCOHERENT_KEEP_REASONS = ("TOPIC_SHIFT", "NEW_SUBTOPIC")

ABSTAIN = "ABSTAIN"


@dataclass(frozen=True)
class AgenticConfig:
    """Budgets identical to the benchmarked arms; agentic knobs are new
    and, like every number here, ``poc_initial_not_optimized``."""

    min_tokens: int = 160
    target_tokens: int = 700
    soft_max_tokens: int = 900
    hard_max_tokens: int = 1126
    respect_semantic_roles: bool = True
    max_candidates_per_call: int = 24
    max_prompt_chars: int = 30_000
    coherence_min_violations: int = 2
    coherence_violation_ratio: float = 0.20
    concurrency: int = 8
    tuning_status: str = TUNING_STATUS


def coherence_threshold(candidate_count: int, config: AgenticConfig) -> int:
    """Demoted SPLITs a call may carry before the whole call is rejected."""
    return max(
        config.coherence_min_violations,
        math.ceil(config.coherence_violation_ratio * candidate_count),
    )


# --------------------------------------------------------------------------
# phase 1: the deterministic call plan
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedCandidate:
    label: str
    stop: int
    cut_after_unit_id: str
    cut_before_unit_id: str


@dataclass(frozen=True)
class PlannedCall:
    call_id: str
    section_index: int
    section_heading: str | None
    section_path: tuple[str, ...]
    candidates: tuple[PlannedCandidate, ...]
    #: In-memory only. Never persisted; artifacts carry prompt_sha256.
    prompt: str
    prompt_sha256: str
    prompt_chars: int


@dataclass(frozen=True)
class SectionPlan:
    section_index: int
    oversized: bool
    dry_windows: int
    candidate_stops: tuple[int, ...]
    calls: tuple[PlannedCall, ...]
    dropped_stops: tuple[int, ...]


@dataclass
class CallPlan:
    sections: list[Section]
    section_plans: list[SectionPlan]

    @property
    def calls(self) -> list[PlannedCall]:
        return [call for plan in self.section_plans for call in plan.calls]


def _candidate_stops(pieces: Sequence[Piece]) -> tuple[int, ...]:
    """Every internal boundary that is not a label position.

    A stop before a label piece is a label seam -- structure's own cut,
    never offered to the model.
    """
    return tuple(
        stop for stop in range(1, len(pieces)) if not pieces[stop].label
    )


def _is_oversized(section: Section, config: AgenticConfig) -> bool:
    seamed = config.respect_semantic_roles and any(
        piece.label for piece in section.pieces
    )
    ceiling = config.target_tokens if seamed else config.soft_max_tokens
    return section.tokens > ceiling


def _segment(
    section: Section,
    stops: Sequence[int],
    config: AgenticConfig,
) -> tuple[list[tuple[list[int], str]], list[int]]:
    """Deterministic segments of at most ``max_candidates_per_call`` stops,
    bisected further while a segment's prompt exceeds ``max_prompt_chars``.
    A single-candidate segment that still cannot fit is dropped: that
    region simply stays unvoted (pure structural behaviour)."""

    def prompt_for(segment: Sequence[int]) -> str:
        return build_window_prompt(
            heading=section.heading,
            section_path=section.section_path,
            pieces=section.pieces,
            start=0,
            admissible=list(segment),
        )

    cap = config.max_candidates_per_call
    pending = [list(stops[index : index + cap]) for index in range(0, len(stops), cap)]
    built: list[tuple[list[int], str]] = []
    dropped: list[int] = []
    while pending:
        segment = pending.pop(0)
        prompt = prompt_for(segment)
        if len(prompt) <= config.max_prompt_chars:
            built.append((segment, prompt))
            continue
        if len(segment) == 1:
            dropped.extend(segment)
            continue
        middle = len(segment) // 2
        pending[0:0] = [segment[:middle], segment[middle:]]
    return built, dropped


def section_call_plan(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    config: AgenticConfig = AgenticConfig(),
) -> CallPlan:
    """Which sections get called, with which candidates, in which prompts.

    Pure function of (canonical units, config): the prompt set is exactly
    reproducible for the same pair, and only for the same pair.
    """
    sections = _sections(
        units, counter, config.hard_max_tokens, config.respect_semantic_roles
    )
    section_plans: list[SectionPlan] = []
    for section_index, section in enumerate(sections):
        oversized = _is_oversized(section, config)
        if not oversized:
            section_plans.append(
                SectionPlan(section_index, False, 0, (), (), ())
            )
            continue
        _, dry_windows = _walk_section(
            section, counter, config, votes=None, planned_stops=None,
            section_index=section_index, window_sink=None,
        )
        stops = _candidate_stops(section.pieces)
        if dry_windows == 0 or len(stops) < 2:
            section_plans.append(
                SectionPlan(section_index, True, dry_windows, stops, (), ())
            )
            continue
        segments, dropped = _segment(section, stops, config)
        calls = []
        for segment_index, (segment, prompt) in enumerate(segments):
            labels = candidate_labels(len(segment))
            candidates = tuple(
                PlannedCandidate(
                    label=label,
                    stop=stop,
                    cut_after_unit_id=section.pieces[stop - 1].unit_id,
                    cut_before_unit_id=section.pieces[stop].unit_id,
                )
                for label, stop in zip(labels, segment)
            )
            calls.append(
                PlannedCall(
                    call_id=f"call-{section_index:04d}-{segment_index:02d}",
                    section_index=section_index,
                    section_heading=section.heading,
                    section_path=tuple(section.section_path),
                    candidates=candidates,
                    prompt=prompt,
                    prompt_sha256=hashlib.sha256(
                        prompt.encode("utf-8")
                    ).hexdigest(),
                    prompt_chars=len(prompt),
                )
            )
        section_plans.append(
            SectionPlan(
                section_index, True, dry_windows, stops,
                tuple(calls), tuple(dropped),
            )
        )
    return CallPlan(sections=sections, section_plans=section_plans)


# --------------------------------------------------------------------------
# phase 2: parallel vote collection (cache-first, provider optional)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CallOutcome:
    call_id: str
    status: str  # ok | cached | provider_error | replay_miss
    response: str | None


def collect_votes(
    calls: Sequence[PlannedCall],
    *,
    provider: BoundaryJudgeModel | None,
    cache: Mapping[str, str] | None = None,
    concurrency: int = 8,
) -> list[CallOutcome]:
    """One ``complete()`` per planned call; independent, so concurrent.

    ``cache`` maps prompt_sha256 to a raw response; hits never reach the
    provider. With ``provider=None`` (replay) a miss becomes
    ``replay_miss`` -- deterministically equivalent to the original run's
    provider error. Results are assembled in plan order regardless of
    completion order.
    """
    cache = cache or {}
    outcomes: dict[str, CallOutcome] = {}
    to_call: list[PlannedCall] = []
    for call in calls:
        if call.prompt_sha256 in cache:
            outcomes[call.call_id] = CallOutcome(
                call.call_id, "cached", cache[call.prompt_sha256]
            )
        elif provider is None:
            outcomes[call.call_id] = CallOutcome(call.call_id, "replay_miss", None)
        else:
            to_call.append(call)

    def run(call: PlannedCall) -> CallOutcome:
        try:
            return CallOutcome(call.call_id, "ok", provider.complete(call.prompt))
        except Exception:
            return CallOutcome(call.call_id, "provider_error", None)

    if to_call:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            for outcome in pool.map(run, to_call):
                outcomes[outcome.call_id] = outcome
    return [outcomes[call.call_id] for call in calls]


# --------------------------------------------------------------------------
# phase 3: strict parse + coherence guard
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Vote:
    stop: int
    call_id: str
    candidate_label: str
    cut_after_unit_id: str
    cut_before_unit_id: str
    decision_raw: str
    reason_code: str
    effective: str  # SPLIT | KEEP | ABSTAIN
    demoted: bool
    incoherent_keep: bool


@dataclass(frozen=True)
class CallAudit:
    call_id: str
    section_index: int
    candidate_count: int
    status: str  # ok | cached | parse_error | provider_error | replay_miss | coherence_violation
    demoted_split_count: int
    incoherent_keep_count: int
    coherence_threshold: int


def apply_guard(
    call: PlannedCall,
    outcome: CallOutcome,
    config: AgenticConfig,
) -> tuple[dict[int, Vote], CallAudit]:
    """Votes of one call after the strict parser and the coherence veto."""
    threshold = coherence_threshold(len(call.candidates), config)

    def audit(status: str, demoted: int = 0, incoherent: int = 0) -> CallAudit:
        return CallAudit(
            call_id=call.call_id,
            section_index=call.section_index,
            candidate_count=len(call.candidates),
            status=status,
            demoted_split_count=demoted,
            incoherent_keep_count=incoherent,
            coherence_threshold=threshold,
        )

    if outcome.response is None:
        return {}, audit(outcome.status)
    parsed = parse_window_decisions(
        outcome.response, [candidate.label for candidate in call.candidates]
    )
    if parsed is None:
        return {}, audit("parse_error")

    votes: dict[int, Vote] = {}
    demoted_count = 0
    incoherent_count = 0
    for candidate in call.candidates:
        decision, reason = parsed[candidate.label]
        demoted = decision == DECISION_SPLIT and reason in COHERENCE_VETO_REASONS
        incoherent = decision == DECISION_KEEP and reason in INCOHERENT_KEEP_REASONS
        demoted_count += int(demoted)
        incoherent_count += int(incoherent)
        votes[candidate.stop] = Vote(
            stop=candidate.stop,
            call_id=call.call_id,
            candidate_label=candidate.label,
            cut_after_unit_id=candidate.cut_after_unit_id,
            cut_before_unit_id=candidate.cut_before_unit_id,
            decision_raw=decision,
            reason_code=reason,
            effective=ABSTAIN if demoted else decision,
            demoted=demoted,
            incoherent_keep=incoherent,
        )
    if demoted_count > threshold:
        return {}, audit("coherence_violation", demoted_count, incoherent_count)
    return votes, audit(outcome.status, demoted_count, incoherent_count)


# --------------------------------------------------------------------------
# phase 4: the vote-guided deterministic walk
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowAudit:
    section_index: int
    section_heading: str | None
    section_path: tuple[str, ...]
    step: int
    candidate_count: int
    decisions: tuple[dict[str, Any], ...]
    chosen_after_unit_id: str
    chosen_equals_greedy: bool
    fallback: str | None
    applied_call_id: str | None


def _walk_section(
    section: Section,
    counter: TokenCounter,
    config: AgenticConfig,
    *,
    votes: Mapping[int, Vote] | None,
    planned_stops: Sequence[int] | None,
    section_index: int,
    window_sink: list[WindowAudit] | None,
) -> tuple[list[Section], int]:
    """The structural walk, votes consulted at multi-candidate windows.

    ``votes=None`` is the free all-KEEP dry-walk used by the call plan;
    it chooses greedy everywhere and only counts windows. The walk is
    otherwise a step-for-step mirror of ``structural_chunker.chunk_units``
    (same seamed ceiling handled by the caller, same label-seam cuts, same
    greedy budget cuts, same re-test after an early cut).
    """
    head_cost = counter.count(section.heading) + 2 if section.heading else 0
    pieces = section.pieces
    totals = [0]
    for piece in pieces:
        totals.append(totals[-1] + piece.tokens)

    def size(start: int, stop: int) -> int:
        return head_cost + totals[stop] - totals[start]

    planned = set(planned_stops) if planned_stops is not None else None
    cuts: list[int] = []
    start = 0
    index = 0
    current_tokens = 0
    windows = 0
    step = 0
    while index < len(pieces):
        piece = pieces[index]
        projected = head_cost + current_tokens + piece.tokens
        at_label = piece.label and current_tokens >= config.min_tokens
        if index > start and (projected > config.target_tokens or at_label):
            greedy = index
            chosen = greedy
            if not at_label:
                admissible = [
                    stop
                    for stop in range(start + 1, index + 1)
                    if config.min_tokens <= size(start, stop) <= config.target_tokens
                ]
                if len(admissible) >= 2:
                    windows += 1
                    if votes is not None:
                        step += 1
                        if planned is not None:
                            for stop in admissible:
                                # The design guard: every non-label
                                # admissible stop must have been a planned
                                # candidate; only label-position stops the
                                # walk passed may be unplanned.
                                assert stop in planned or pieces[stop].label, (
                                    f"unplanned non-label admissible stop before "
                                    f"{pieces[stop].unit_id}"
                                )
                        approved = [
                            stop
                            for stop in admissible
                            if stop in votes
                            and votes[stop].effective == DECISION_SPLIT
                        ]
                        if approved:
                            chosen = approved[-1]
                            fallback = None
                        else:
                            demoted_here = any(
                                stop in votes and votes[stop].demoted
                                for stop in admissible
                            )
                            all_keep = bool(votes) and all(
                                stop in votes
                                and votes[stop].effective == DECISION_KEEP
                                for stop in admissible
                            )
                            fallback = (
                                "forced_greedy_after_coherence"
                                if demoted_here
                                else "forced_greedy_all_keep"
                                if all_keep
                                else "structural_fallback"
                            )
                        if window_sink is not None:
                            window_sink.append(
                                WindowAudit(
                                    section_index=section_index,
                                    section_heading=section.heading,
                                    section_path=tuple(section.section_path),
                                    step=step,
                                    candidate_count=len(admissible),
                                    decisions=tuple(
                                        {
                                            "cut_after_unit_id": votes[stop].cut_after_unit_id,
                                            "cut_before_unit_id": votes[stop].cut_before_unit_id,
                                            "decision_raw": votes[stop].decision_raw,
                                            "reason_code": votes[stop].reason_code,
                                            "effective": votes[stop].effective,
                                            "call_id": votes[stop].call_id,
                                        }
                                        for stop in admissible
                                        if stop in votes
                                    ),
                                    chosen_after_unit_id=pieces[chosen - 1].unit_id,
                                    chosen_equals_greedy=chosen == greedy,
                                    fallback=fallback,
                                    applied_call_id=(
                                        votes[chosen].call_id
                                        if chosen != greedy and chosen in votes
                                        else None
                                    ),
                                )
                            )
            cuts.append(chosen)
            start = chosen
            current_tokens = totals[index] - totals[chosen]
            continue  # re-test this piece against the shortened block
        current_tokens += piece.tokens
        index += 1

    blocks: list[Section] = []
    block_start = 0
    for stop in [*cuts, len(pieces)]:
        if stop <= block_start:
            continue
        block = Section(section.heading, section.section_path)
        block.pieces.extend(pieces[block_start:stop])
        blocks.append(block)
        block_start = stop
    return blocks, windows


@dataclass(frozen=True)
class AgenticChunkResult:
    chunks: list[dict[str, Any]]
    window_audit: tuple[WindowAudit, ...]
    diagnostics: dict[str, Any]


def chunk_units_agentic(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    votes_by_section: Mapping[int, Mapping[int, Vote]],
    plan: CallPlan,
    config: AgenticConfig = AgenticConfig(),
) -> AgenticChunkResult:
    """The final chunks. With no votes anywhere this is byte-identical to
    ``structural_chunker.chunk_units`` (chunk ids aside)."""
    window_sink: list[WindowAudit] = []
    split_sections: list[Section] = []
    plans = {plan_.section_index: plan_ for plan_ in plan.section_plans}
    for section_index, section in enumerate(plan.sections):
        if not _is_oversized(section, config):
            split_sections.append(section)
            continue
        section_plan = plans[section_index]
        blocks, _ = _walk_section(
            section,
            counter,
            config,
            votes=votes_by_section.get(section_index, {}),
            planned_stops=section_plan.candidate_stops,
            section_index=section_index,
            window_sink=window_sink,
        )
        split_sections.extend(blocks)

    # Undersized same-section neighbours are rejoined -- the structural
    # chunker's own step, mirrored exactly.
    Block = tuple[str | None, list[Piece], tuple[str, ...]]
    groups: list[list[Block]] = []
    sizes: list[int] = []
    for section in split_sections:
        block: Block = (section.heading, section.pieces, section.section_path)
        block_size = section.tokens + (
            counter.count(section.heading) + 2 if section.heading else 0
        )
        same_section = bool(groups) and (
            groups[-1][-1][0] == section.heading
            and groups[-1][-1][2] == section.section_path
        )
        if (
            same_section
            and (sizes[-1] < config.min_tokens or block_size < config.min_tokens)
            and sizes[-1] + block_size <= config.target_tokens
        ):
            groups[-1].append(block)
            sizes[-1] += block_size
            continue
        groups.append([block])
        sizes.append(block_size)

    document_id = units[0].document_id
    chunks: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        text = RENDER_SEPARATOR.join(
            _render(heading, pieces) for heading, pieces, _ in group
        )
        tokens = counter.count(text)
        assert tokens <= config.hard_max_tokens, (
            f"chunk {index} exceeds hard cap: {tokens}"
        )
        group_pieces = [piece for _, block_pieces, _ in group for piece in block_pieces]
        paths: list[list[str]] = []
        for _, _, path in group:
            if path and list(path) not in paths:
                paths.append(list(path))
        chunks.append(
            {
                "chunk_id": f"{document_id}:a-chunk-{index:04d}",
                "text": text,
                "unit_ids": [piece.unit_id for piece in group_pieces],
                "token_count": tokens,
                "pages": sorted(
                    {piece.page for piece in group_pieces if piece.page is not None}
                ),
                "section_paths": paths,
                "heading": group[0][0],
                "split_strategies": sorted(
                    {piece.strategy for piece in group_pieces}
                ),
            }
        )

    moved = sum(1 for window in window_sink if not window.chosen_equals_greedy)
    diagnostics = {
        "arm_kind": ARM_KIND,
        "selection_rule": SELECTION_RULE,
        "section_count": len(plan.sections),
        "oversized_section_count": sum(
            1 for plan_ in plan.section_plans if plan_.oversized
        ),
        "decision_window_count": len(window_sink),
        "changed_from_greedy_count": moved,
        "tuning_status": config.tuning_status,
    }
    return AgenticChunkResult(
        chunks=chunks,
        window_audit=tuple(window_sink),
        diagnostics=diagnostics,
    )


# --------------------------------------------------------------------------
# the library entry: plan -> collect -> guard -> walk
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AgenticRun:
    plan: CallPlan
    outcomes: list[CallOutcome]
    call_audit: list[CallAudit]
    votes_by_section: dict[int, dict[int, Vote]]
    result: AgenticChunkResult
    diagnostics: dict[str, Any]


def run_agentic(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    provider: BoundaryJudgeModel | None,
    config: AgenticConfig = AgenticConfig(),
    cache: Mapping[str, str] | None = None,
) -> AgenticRun:
    """End to end. ``provider=None`` with a cache is replay; ``provider=None``
    without one is Structure-only behaviour under the agentic id scheme."""
    plan = section_call_plan(units, counter=counter, config=config)
    outcomes = collect_votes(
        plan.calls,
        provider=provider,
        cache=cache,
        concurrency=config.concurrency,
    )
    votes_by_section: dict[int, dict[int, Vote]] = {}
    call_audit: list[CallAudit] = []
    outcome_by_id = {outcome.call_id: outcome for outcome in outcomes}
    for call in plan.calls:
        votes, audit = apply_guard(call, outcome_by_id[call.call_id], config)
        call_audit.append(audit)
        if votes:
            votes_by_section.setdefault(call.section_index, {}).update(votes)
    result = chunk_units_agentic(
        units,
        counter=counter,
        votes_by_section=votes_by_section,
        plan=plan,
        config=config,
    )

    statuses = [audit.status for audit in call_audit]
    provider_calls = sum(
        1 for outcome in outcomes if outcome.status in ("ok", "provider_error")
    )
    outcome_statuses = [outcome.status for outcome in outcomes]
    diagnostics = {
        **result.diagnostics,
        "planned_call_count": len(plan.calls),
        "provider_call_count": provider_calls,
        "cache_hit_count": outcome_statuses.count("cached"),
        "parse_error_call_count": statuses.count("parse_error"),
        "provider_error_call_count": statuses.count("provider_error"),
        "replay_miss_call_count": statuses.count("replay_miss"),
        "coherence_rejected_call_count": statuses.count("coherence_violation"),
        "demoted_vote_count": sum(
            audit.demoted_split_count
            for audit in call_audit
            if audit.status not in ("coherence_violation",)
        ),
        "incoherent_keep_count": sum(
            audit.incoherent_keep_count for audit in call_audit
        ),
        "candidate_decision_count": sum(
            len(votes) for votes in votes_by_section.values()
        ),
        "dropped_candidate_count": sum(
            len(plan_.dropped_stops) for plan_ in plan.section_plans
        ),
        "model_id": getattr(provider, "model_id", None),
    }
    return AgenticRun(
        plan=plan,
        outcomes=outcomes,
        call_audit=call_audit,
        votes_by_section=votes_by_section,
        result=result,
        diagnostics=diagnostics,
    )


# --------------------------------------------------------------------------
# helpers for fixtures and the smoke gate
# --------------------------------------------------------------------------


def slice_units_by_pages(
    units: Sequence[RawDocumentUnit], first_page: int, last_page: int
) -> list[RawDocumentUnit]:
    """A deterministic page slice of a frozen canonical corpus.

    Filtering preserves ids, order and text byte for byte -- the parser is
    never re-run. Used by the live smoke gate (KKB 2022 p.68-75)."""
    sliced = [
        unit
        for unit in units
        if unit.source is not None
        and unit.source.page is not None
        and first_page <= unit.source.page <= last_page
    ]
    if not sliced:
        raise ValueError(
            f"no units on pages {first_page}-{last_page}; widen the range"
        )
    return sliced


# --------------------------------------------------------------------------
# artifact builder (CLI)
# --------------------------------------------------------------------------


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def load_response_cache(path: Path) -> dict[str, str]:
    cache: dict[str, str] = {}
    if not path.is_file():
        return cache
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cache[row["prompt_sha256"]] = row["response"]
    return cache


def _refuse_output(output: Path) -> None:
    resolved = output.resolve()
    for part in resolved.parts:
        if part == "evaluation":
            raise ValueError(
                "refusing to write into evaluation/ -- frozen results live there"
            )
    for ancestor in [resolved, *resolved.parents]:
        if (ancestor / "benchmark-summary.json").is_file():
            raise ValueError(
                f"refusing to write into the frozen benchmark tree at {ancestor}"
            )


def build_artifact(
    *,
    units_path: Path,
    output: Path,
    provider: BoundaryJudgeModel | None,
    config: AgenticConfig = AgenticConfig(),
    counter: TokenCounter | None = None,
    expected_sha256: str | None = None,
    pages: tuple[int, int] | None = None,
    replay: bool = False,
    frozen_tree: Path | None = None,
    dump_prompts: Path | None = None,
) -> dict[str, Any]:
    """Run the pipeline and write the agentic artifact tree.

    Never writes into evaluation/ or a frozen benchmark tree; never writes
    raw prompt text, keys, endpoints, or wall-clock values."""
    from .evaluation import sha256_file
    from .io import load_jsonl_units

    _refuse_output(output)
    canonical_sha = sha256_file(units_path)
    if expected_sha256 and canonical_sha != expected_sha256:
        raise ValueError(
            f"units sha mismatch: expected {expected_sha256}, got {canonical_sha}"
        )
    units = load_jsonl_units(units_path)
    if pages is not None:
        units = slice_units_by_pages(units, pages[0], pages[1])

    if counter is None:
        from .tokenization import TiktokenTokenCounter

        counter = TiktokenTokenCounter("cl100k_base")

    cache_path = output / "judge" / "responses.jsonl"
    cache = load_response_cache(cache_path)
    if replay and provider is not None:
        raise ValueError("replay mode takes no provider; it reads the cache only")
    if replay and not cache:
        raise ValueError(f"replay mode needs an existing {cache_path}")

    run = run_agentic(
        units, counter=counter, provider=provider, config=config, cache=cache
    )

    if dump_prompts is not None:
        dump = dump_prompts.resolve()
        if str(dump).startswith(str(output.resolve())):
            raise ValueError(
                "--dump-prompts must point outside the artifact tree; raw "
                "prompts are local debug output, never an artifact"
            )
        dump.mkdir(parents=True, exist_ok=True)
        for call in run.plan.calls:
            (dump / f"{call.call_id}.txt").write_text(
                call.prompt, encoding="utf-8", newline="\n"
            )

    model_id = getattr(provider, "model_id", None)
    mode = "replay" if replay else ("live" if provider is not None else "no_provider")

    calls_rows = []
    audit_by_id = {audit.call_id: audit for audit in run.call_audit}
    for call in run.plan.calls:
        audit = audit_by_id[call.call_id]
        calls_rows.append(
            {
                "call_id": call.call_id,
                "section_index": call.section_index,
                "section_heading": call.section_heading,
                "section_path": list(call.section_path),
                "candidates": [
                    {
                        "id": candidate.label,
                        "cut_after_unit_id": candidate.cut_after_unit_id,
                        "cut_before_unit_id": candidate.cut_before_unit_id,
                    }
                    for candidate in call.candidates
                ],
                "prompt_sha256": call.prompt_sha256,
                "prompt_chars": call.prompt_chars,
                "status": audit.status,
                "demoted_split_count": audit.demoted_split_count,
                "incoherent_keep_count": audit.incoherent_keep_count,
                "coherence_threshold": audit.coherence_threshold,
            }
        )

    response_rows = []
    outcome_by_id = {outcome.call_id: outcome for outcome in run.outcomes}
    for call in run.plan.calls:
        outcome = outcome_by_id[call.call_id]
        if outcome.response is None:
            continue
        response_rows.append(
            {
                "call_id": call.call_id,
                "prompt_sha256": call.prompt_sha256,
                "model_id": model_id if outcome.status == "ok" else None,
                "response": outcome.response,
            }
        )

    window_rows = [
        {
            "section_index": window.section_index,
            "section_heading": window.section_heading,
            "section_path": list(window.section_path),
            "step": window.step,
            "candidate_count": window.candidate_count,
            "decisions": list(window.decisions),
            "chosen_after_unit_id": window.chosen_after_unit_id,
            "chosen_equals_greedy": window.chosen_equals_greedy,
            "fallback": window.fallback,
            "applied_call_id": window.applied_call_id,
        }
        for window in run.result.window_audit
    ]

    from .chunk_benchmark import normalize_unit_ids_for_retrieval
    from .chunk_mapping import map_chunks

    # The same row normalization the benchmarked arms get: fragment ids are
    # reduced to canonical base ids (kept in fragment_unit_ids) so retrieval
    # scoring and the viewer see the shared schema.
    normalized = [normalize_unit_ids_for_retrieval(row) for row in run.result.chunks]
    mapping = map_chunks(units, normalized)

    agentic_dir = output / "agentic"
    _write_jsonl(agentic_dir / "chunks.jsonl", normalized)
    _write_json(agentic_dir / "mapping.json", mapping.as_dict())
    _write_jsonl(output / "judge" / "calls.jsonl", calls_rows)
    _write_jsonl(cache_path, response_rows)
    _write_jsonl(output / "judge" / "audit.jsonl", window_rows)
    _write_json(output / "judge" / "summary.json", run.diagnostics)

    moved_windows = [row for row in window_rows if not row["chosen_equals_greedy"]]
    _write_json(
        output / "boundary-diff.json",
        {
            "document_id": units[0].document_id,
            "summary": {
                "decision_windows": len(window_rows),
                "moved": len(moved_windows),
                "kept": len(window_rows) - len(moved_windows),
            },
            "windows": window_rows,
        },
    )

    resolved = {
        "arm_kind": ARM_KIND,
        "selection_rule": SELECTION_RULE,
        "config": asdict(config),
        "mode": mode,
        "model_id": model_id,
        "pages": list(pages) if pages else None,
        "units_file": units_path.name,
        "units_sha256": canonical_sha,
    }
    _write_json(output / "resolved-config.json", resolved)

    manifest: dict[str, Any] = {
        "arm_kind": ARM_KIND,
        "canonical_sha256": canonical_sha,
        "chunks_sha256": hashlib.sha256(
            (agentic_dir / "chunks.jsonl").read_bytes()
        ).hexdigest(),
        "config_sha256": hashlib.sha256(
            json.dumps(resolved, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "mode": mode,
        "model_id": model_id,
    }
    if frozen_tree is not None:
        frozen_manifest = json.loads(
            (frozen_tree / "manifest.json").read_text(encoding="utf-8")
        )
        if pages is None and frozen_manifest.get("canonical_sha256") != canonical_sha:
            raise ValueError(
                "the agentic run and the frozen benchmark tree disagree on the "
                "canonical corpus; refusing to record a frozen_reference"
            )
        manifest["frozen_reference"] = {
            "tree": frozen_tree.as_posix(),
            "canonical_sha256": frozen_manifest.get("canonical_sha256"),
            "arm_chunk_sha256": frozen_manifest.get("arm_chunk_sha256"),
        }
    _write_json(output / "manifest.json", manifest)
    return run.diagnostics


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Agentic Chunker artifact builder (backend only; the "
        "API key is read from the environment at call time and never stored)"
    )
    parser.add_argument("--units", required=True, type=Path)
    parser.add_argument("--expected-sha", default=None)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pages", default=None, help="A-B page slice (smoke)")
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--endpoint", default="https://openrouter.ai/api/v1/chat/completions"
    )
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--concurrency", type=int, default=None)
    parser.add_argument("--frozen-tree", default=None, type=Path)
    parser.add_argument("--dump-prompts", default=None, type=Path)
    args = parser.parse_args(argv)

    config = AgenticConfig()
    if args.concurrency:
        config = AgenticConfig(**{**asdict(config), "concurrency": args.concurrency})

    provider: BoundaryJudgeModel | None = None
    if args.replay:
        if args.model:
            parser.error("--replay takes no --model; it reads the cache only")
    elif args.model:
        provider = OpenAICompatibleJudgeProvider(
            args.model, endpoint=args.endpoint, api_key_env=args.api_key_env
        )
    else:
        parser.error("either --model (live) or --replay is required")

    pages = None
    if args.pages:
        first, _, last = args.pages.partition("-")
        pages = (int(first), int(last or first))

    diagnostics = build_artifact(
        units_path=args.units,
        output=args.output,
        provider=provider,
        config=config,
        expected_sha256=args.expected_sha,
        pages=pages,
        replay=args.replay,
        frozen_tree=args.frozen_tree,
        dump_prompts=args.dump_prompts,
    )
    print(json.dumps(diagnostics, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
