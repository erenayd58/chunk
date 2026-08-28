"""The Deep Analysis proposer: what the model is actually asked.

The old judge asked a binary question -- SPLIT or KEEP at this budget cut --
under a prompt that defined SPLIT as "a reader would *accept* a boundary
here". Permissibility is not preference, the model answered the question it
was asked, and 328 of 586 answers were SPLIT with 159 of those contradicting
their own stated reason. Worse, a binary vote cannot say *which side* of a
label the boundary belongs on, which is how a section came back with its
heading stranded.

So the question changed shape. For each candidate boundary the model returns
three things:

    {"id": "B7", "strength": 2, "left": "complete", "right": "complete"}

``strength`` 0-3 is preference: how much a reader would want a break here.
``left`` says whether the piece before the boundary is finished or introduces
what follows; ``right`` says whether the piece after it stands on its own or
continues what precedes. Either role can veto the boundary, and each unit is
asked about at both of its boundaries, so "this belongs with what comes after
*and* what comes before" is expressible -- which the binary vote never was.

Three deliberate constraints:

* **size is never mentioned.** No tokens, no chunk, no target. Size is the
  selector's business; a model told about budgets starts optimising them.
* **only boundaries the deterministic layer would accept are marked.** A cut
  that strands a lead-in is already forbidden by
  :mod:`amsc.boundary_quality`, so offering it invites an answer nobody can
  act on. This removes roughly a third of the markers.
* **the model never sees the partition.** It scores boundaries; the DP in
  :mod:`amsc.deep_analysis` picks the partition, and strength enters that
  objective *below* every smell term, so no answer here can produce a
  defective chunk.

Artifacts carry ``prompt_sha256`` and the raw responses, never prompt text:
replay reconstructs prompts deterministically from the same canonical and
config. Results are model-dependent and only replay-deterministic.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from . import boundary_quality as bq
from .agentic_chunker import CallOutcome, collect_votes
from .deep_analysis import (
    DeepConfig,
    ROLE_COMPLETE,
    ROLE_CONTINUES_PREVIOUS,
    ROLE_INTRODUCES_NEXT,
    BoundaryVote,
    _SectionSolver,
    _fitting_run_index,
    _group_cuts,
    _head_cost,
    standard_groups,
)
from .llm_boundary_judge import BoundaryJudgeModel
from .models import RawDocumentUnit
from .structural_chunker import Piece, Section, _sections
from .tokenization import TokenCounter

PROMPT_TEMPLATE_VERSION = "deep-proposer-v2"

#: Longest excerpt of one piece shown to the model. Long tables are the reason:
#: a reader decides a boundary from the head and tail of what surrounds it.
MAX_PIECE_CHARS = 1200
#: Most boundaries offered in one call. Sections past this are segmented.
MAX_MARKERS = 16

_INSTRUCTIONS = """You are judging where a Turkish corporate annual report can be divided.

Below is one section of the document. Its content is shown as numbered pieces
[U1], [U2], ... in reading order. Between some pieces there is a marked
boundary [B1], [B2], ... Only marked boundaries are under consideration.

For every marked boundary answer three questions.

1. "strength" (a number 0-3): how strongly does a reader need a break here?
   0 = these two pieces are one thought and must stay together
   1 = a break is possible but nothing changes topic
   2 = a new sub-topic starts after the boundary
   3 = a clearly different subject starts after the boundary

2. "before" - about the piece immediately BEFORE this boundary.
   Allowed values, and nothing else:
     "finished"         = it finishes what it was saying
     "introduces_next"  = it announces, titles or introduces what comes after
                          it (a label, a heading-like line, or a sentence that
                          promises a table, a list or an explanation)

3. "after" - about the piece immediately AFTER this boundary.
   Allowed values, and nothing else:
     "standalone"          = a reader could start here and understand it
     "continues_previous"  = it needs the piece before it to be understood
                             (it refers back to it, continues its sentence,
                             or is a note or footnote about it)

"introduces_next" is only ever a value of "before".
"continues_previous" is only ever a value of "after".

Answer with JSON only, one object per marked boundary, exactly this shape:

{"boundaries": [{"id": "B1", "strength": 2, "before": "finished", "after": "standalone"}]}

Every marked boundary must appear exactly once. Do not add commentary.
Do not consider length: how long the parts are is not your decision.
"""


@dataclass(frozen=True)
class PlannedBoundary:
    label: str
    stop: int
    cut_after_unit_id: str
    cut_before_unit_id: str


@dataclass(frozen=True)
class PlannedProposal:
    call_id: str
    section_index: int
    section_heading: str | None
    section_path: tuple[str, ...]
    boundaries: tuple[PlannedBoundary, ...]
    #: In-memory only. Never persisted; artifacts carry prompt_sha256.
    prompt: str
    prompt_sha256: str
    prompt_chars: int

    @property
    def candidates(self) -> tuple[PlannedBoundary, ...]:  # collect_votes compatibility
        return self.boundaries


def _excerpt(text: str) -> str:
    body = text.strip()
    if len(body) <= MAX_PIECE_CHARS:
        return body
    half = MAX_PIECE_CHARS // 2
    return f"{body[:half].rstrip()}\n[...]\n{body[-half:].lstrip()}"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_prompt(
    section: Section, pieces: Sequence[Piece], marks: Mapping[int, str]
) -> str:
    """One section, its pieces, and the boundaries under consideration.

    ``marks`` maps a piece index (the boundary *before* that piece) to its
    label. Nothing about size, chunking or the current partition appears.
    """
    lines: list[str] = [_INSTRUCTIONS, ""]
    if section.heading:
        lines.append(f"SECTION: {section.heading.strip()}")
    if section.section_path:
        lines.append("PATH: " + " > ".join(part.strip() for part in section.section_path))
    lines.append("")
    for index, piece in enumerate(pieces):
        if index in marks:
            lines.append(f"[{marks[index]}]")
        lines.append(f"[U{index + 1}] {_excerpt(piece.text)}")
    lines.append("")
    lines.append("Marked boundaries: " + ", ".join(marks[key] for key in sorted(marks)))
    return "\n".join(lines)


def plan_calls(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    config: DeepConfig = DeepConfig(),
) -> list[PlannedProposal]:
    """One call per section that has a boundary the selector could still choose.

    A boundary is offered only when it is *deterministically clean*: the
    quality layer records no smell for it, and both sides fit the hard cap.
    Sections whose every internal boundary is already forbidden are skipped
    entirely -- there is nothing for a model to decide there.
    """
    sections = _sections(units, counter, config.hard_max_tokens, config.respect_semantic_roles)
    units_by_id = {unit.unit_id: unit for unit in units}
    fitting = _fitting_run_index(units, counter, config)
    plans: list[PlannedProposal] = []
    for index, section in enumerate(sections):
        groups = standard_groups(section, counter=counter, config=config)
        head = _head_cost(section, counter)
        if len(groups) < 2 and section.tokens + head <= config.target_tokens:
            continue
        solver = _SectionSolver(
            section,
            units_by_id=units_by_id,
            fitting_runs=fitting,
            counter=counter,
            config=config,
            votes={},
            standard_cuts=_group_cuts(groups),
        )
        clean = [
            stop
            for stop in range(1, len(section.pieces))
            if solver.cut_cost(stop)[0] == 0
            and not section.pieces[stop].label
        ]
        if not clean:
            continue
        for number, batch in enumerate(
            [clean[start : start + MAX_MARKERS] for start in range(0, len(clean), MAX_MARKERS)]
        ):
            marks = {stop: f"B{position + 1}" for position, stop in enumerate(batch)}
            prompt = build_prompt(section, section.pieces, marks)
            boundaries = tuple(
                PlannedBoundary(
                    label=marks[stop],
                    stop=stop,
                    cut_after_unit_id=section.pieces[stop - 1].unit_id,
                    cut_before_unit_id=section.pieces[stop].unit_id,
                )
                for stop in batch
            )
            plans.append(
                PlannedProposal(
                    call_id=f"prop-{index:04d}-{number:02d}",
                    section_index=index,
                    section_heading=section.heading,
                    section_path=tuple(section.section_path),
                    boundaries=boundaries,
                    prompt=prompt,
                    prompt_sha256=_digest(prompt),
                    prompt_chars=len(prompt),
                )
            )
    return plans


# --------------------------------------------------------------------------
# strict parsing
# --------------------------------------------------------------------------

_JSON_BLOCK = re.compile(r"\{.*\}", re.S)
_STRENGTHS = (0, 1, 2, 3)


_BEFORE_WIRE = {
    "finished": ROLE_COMPLETE,
    "complete": ROLE_COMPLETE,
    "standalone": ROLE_COMPLETE,
    "introduces_next": ROLE_INTRODUCES_NEXT,
    # A model that answers "continues_previous" here is describing the *other*
    # boundary of that piece -- whether it continues what precedes it says
    # nothing about whether a chunk may end after it. Neutral, not a veto.
    "continues_previous": ROLE_COMPLETE,
}
_AFTER_WIRE = {
    "standalone": ROLE_COMPLETE,
    "complete": ROLE_COMPLETE,
    "finished": ROLE_COMPLETE,
    "continues_previous": ROLE_CONTINUES_PREVIOUS,
    # Symmetrically: a piece that introduces what follows *it* is a perfectly
    # good place for a chunk to start.
    "introduces_next": ROLE_COMPLETE,
}


def _normalise_before(value: Any) -> str | None:
    return _BEFORE_WIRE.get(str(value).strip().lower()) if value is not None else None


def _normalise_after(value: Any) -> str | None:
    return _AFTER_WIRE.get(str(value).strip().lower()) if value is not None else None


def parse_proposal(
    raw: str | None, expected: Sequence[str]
) -> tuple[dict[str, tuple[int, str, str]], str]:
    """``(by_label, status)``; anything unexpected refuses the whole call.

    A partial answer is refused rather than repaired: a missing boundary is
    indistinguishable from a boundary the model silently merged into another,
    and guessing there is how a chunker acquires an unexplainable cut.
    """
    if raw is None:
        return {}, "no_response"
    match = _JSON_BLOCK.search(raw)
    if match is None:
        return {}, "unparsable"
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}, "unparsable"
    rows = payload.get("boundaries") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        return {}, "unparsable"
    out: dict[str, tuple[int, str, str]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            return {}, "malformed_row"
        label = str(row.get("id", ""))
        if label not in expected or label in out:
            return {}, "unknown_or_duplicate_id"
        try:
            strength = int(row.get("strength"))
        except (TypeError, ValueError):
            return {}, "malformed_row"
        if strength not in _STRENGTHS:
            return {}, "malformed_row"
        before = _normalise_before(row.get("before", row.get("left")))
        after = _normalise_after(row.get("after", row.get("right")))
        if before is None or after is None:
            return {}, "malformed_row"
        out[label] = (strength, before, after)
    if set(out) != set(expected):
        return {}, "incomplete"
    return out, "ok"


@dataclass(frozen=True)
class ProposalOutcome:
    call_id: str
    section_index: int
    status: str
    transport: str
    boundary_count: int
    accepted: int
    forbidden: int


def votes_from_outcomes(
    plans: Sequence[PlannedProposal], outcomes: Sequence[CallOutcome]
) -> tuple[dict[str, BoundaryVote], list[ProposalOutcome]]:
    """Fold raw responses into per-boundary votes plus a per-call audit."""
    votes: dict[str, BoundaryVote] = {}
    audit: list[ProposalOutcome] = []
    by_id = {outcome.call_id: outcome for outcome in outcomes}
    for plan in plans:
        outcome = by_id.get(plan.call_id)
        raw = outcome.response if outcome else None
        expected = [boundary.label for boundary in plan.boundaries]
        parsed, status = parse_proposal(raw, expected)
        forbidden = 0
        for boundary in plan.boundaries:
            if boundary.label not in parsed:
                continue
            strength, left, right = parsed[boundary.label]
            vote = BoundaryVote(
                cut_after_unit_id=boundary.cut_after_unit_id,
                strength=strength,
                left=left,
                right=right,
            )
            votes[boundary.cut_after_unit_id] = vote
            forbidden += int(vote.forbidden)
        audit.append(
            ProposalOutcome(
                call_id=plan.call_id,
                section_index=plan.section_index,
                status=status,
                transport=outcome.status if outcome else "missing",
                boundary_count=len(plan.boundaries),
                accepted=len(parsed),
                forbidden=forbidden,
            )
        )
    return votes, audit


def collect(
    plans: Sequence[PlannedProposal],
    *,
    provider: BoundaryJudgeModel | None,
    cache: Mapping[str, str] | None = None,
    concurrency: int = 8,
) -> list[CallOutcome]:
    """Run the plan through the shared cache-aware parallel collector."""
    return collect_votes(plans, provider=provider, cache=cache, concurrency=concurrency)


def summarise(audit: Sequence[ProposalOutcome]) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    transports: dict[str, int] = {}
    for entry in audit:
        statuses[entry.status] = statuses.get(entry.status, 0) + 1
        transports[entry.transport] = transports.get(entry.transport, 0) + 1
    return {
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "call_count": len(audit),
        "boundary_count": sum(entry.boundary_count for entry in audit),
        "accepted_boundary_count": sum(entry.accepted for entry in audit),
        "forbidden_boundary_count": sum(entry.forbidden for entry in audit),
        "call_status": dict(sorted(statuses.items())),
        "transport_status": dict(sorted(transports.items())),
    }
