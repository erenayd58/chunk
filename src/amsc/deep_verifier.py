"""The verifier: a second opinion on every boundary the proposer moved.

Blind labelling of 39 change groups on KKB 2024 said the proposer is worth
something and cannot be trusted alone: its partition was preferred 22 times
against the deterministic one's 14, but it was also judged *unacceptable*
seven times against one. A mode that is better on average and occasionally
much worse is exactly what the product may not ship.

So nothing the proposer moves is kept on its own say-so. Each **change
group** -- the span between two cuts both partitions agree on -- is shown to
the model as two finished alternatives, in full, with their boundaries marked,
and the question is which one a reader would rather have. It is asked twice
with the two alternatives swapped, and the proposal is kept only when it wins
*both* times. A disagreement between the two orders is position bias, not a
judgement, and reverts.

Three properties make this safe rather than merely careful:

* the unit of decision is the change group, never a single cut. Accepting one
  cut from one partition next to a cut kept from the other yields a chunk
  neither side proposed -- and one that no size or smell check ever saw.
* reverting is free and always available: the deterministic partition is a
  complete, already-verified answer for every group.
* the deterministic contract still runs *after* the verifier, so even a
  unanimous mistake cannot produce a chunk that breaks the hard cap or
  carries a smell Standard did not have.

The prompt shows text only -- no scores, no marker ids, no hint of which
alternative came from where.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .agentic_chunker import CallOutcome, collect_votes
from .deep_analysis import DeepConfig
from .llm_boundary_judge import BoundaryJudgeModel
from .structural_chunker import RENDER_SEPARATOR, Piece, Section, _render

PROMPT_TEMPLATE_VERSION = "deep-verifier-v1"

MAX_BLOCK_CHARS = 2400

_INSTRUCTIONS = """Two ways of dividing the same passage of a Turkish corporate
annual report are shown below. The text is identical in both; only the places
where it is divided differ. Each part is introduced by a line of dashes.

Decide which division a reader would rather have. A better division keeps a
title with the text it introduces, keeps a sentence and its continuation
together, keeps a list with the sentence that announces it, and puts a change
of subject at a break rather than inside a part.

Do not consider how long the parts are.

Answer with JSON only, exactly this shape:

{"better": "ONE", "confidence": "high"}

"better" must be "ONE", "TWO" or "EQUAL". "confidence" must be "high" or "low".
"""


@dataclass(frozen=True)
class ChangeGroup:
    """One span where two partitions of a section disagree."""

    section_index: int
    heading: str | None
    start: int
    end: int
    base_cuts: tuple[int, ...]
    proposed_cuts: tuple[int, ...]

    @property
    def key(self) -> str:
        return f"cg-{self.section_index:04d}-{self.start}-{self.end}"


def change_groups(
    base: Sequence[int], proposed: Sequence[int], piece_count: int, *,
    section_index: int, heading: str | None,
) -> list[ChangeGroup]:
    """Maximal spans between shared cuts in which the two partitions differ."""
    base_set, proposed_set = set(base), set(proposed)
    common = sorted((base_set & proposed_set) | {0, piece_count})
    groups: list[ChangeGroup] = []
    for start, end in zip(common, common[1:]):
        inside_base = tuple(sorted(cut for cut in base_set if start < cut < end))
        inside_proposed = tuple(sorted(cut for cut in proposed_set if start < cut < end))
        if inside_base == inside_proposed:
            continue
        groups.append(
            ChangeGroup(section_index, heading, start, end, inside_base, inside_proposed)
        )
    return groups


def _excerpt(text: str) -> str:
    body = text.strip()
    if len(body) <= MAX_BLOCK_CHARS:
        return body
    half = MAX_BLOCK_CHARS // 2
    return f"{body[:half].rstrip()}\n[...]\n{body[-half:].lstrip()}"


def render_partition(
    section: Section, group: ChangeGroup, cuts: Sequence[int], heading: str | None
) -> str:
    """The group's text under one partition, its internal breaks marked."""
    bounds = [group.start, *cuts, group.end]
    parts: list[str] = []
    for number, (start, end) in enumerate(zip(bounds, bounds[1:]), start=1):
        block = section.pieces[start:end]
        parts.append(f"--- part {number} ---")
        parts.append(_excerpt(_render(heading if number == 1 else None, block)))
    return "\n".join(parts)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PlannedComparison:
    call_id: str
    group_key: str
    section_index: int
    #: Which alternative was shown first: "base" or "proposed".
    first: str
    prompt: str
    prompt_sha256: str
    prompt_chars: int

    @property
    def candidates(self) -> tuple[()]:  # collect_votes compatibility
        return ()


def plan_comparisons(
    sections: Sequence[Section],
    groups: Sequence[ChangeGroup],
    *,
    config: DeepConfig = DeepConfig(),
) -> list[PlannedComparison]:
    """Two calls per group: the same pair, in both orders."""
    plans: list[PlannedComparison] = []
    for number, group in enumerate(groups):
        section = sections[group.section_index]
        heading = section.heading
        base = render_partition(section, group, group.base_cuts, heading)
        proposed = render_partition(section, group, group.proposed_cuts, heading)
        for order, (first, one, two) in enumerate(
            (("base", base, proposed), ("proposed", proposed, base))
        ):
            prompt = "\n".join(
                [
                    _INSTRUCTIONS,
                    "",
                    "=== DIVISION ONE ===",
                    one,
                    "",
                    "=== DIVISION TWO ===",
                    two,
                ]
            )
            plans.append(
                PlannedComparison(
                    call_id=f"ver-{number:04d}-{order}",
                    group_key=group.key,
                    section_index=group.section_index,
                    first=first,
                    prompt=prompt,
                    prompt_sha256=_digest(prompt),
                    prompt_chars=len(prompt),
                )
            )
    return plans


_JSON_BLOCK = re.compile(r"\{.*?\}", re.S)
_CHOICES = ("ONE", "TWO", "EQUAL")


def parse_comparison(raw: str | None) -> tuple[str | None, str]:
    """``(choice, status)`` where choice is ONE/TWO/EQUAL or None."""
    if raw is None:
        return None, "no_response"
    match = _JSON_BLOCK.search(raw)
    if match is None:
        return None, "unparsable"
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None, "unparsable"
    if not isinstance(payload, Mapping):
        return None, "unparsable"
    choice = str(payload.get("better", "")).strip().upper()
    if choice not in _CHOICES:
        return None, "malformed"
    return choice, "ok"


@dataclass(frozen=True)
class GroupVerdict:
    group_key: str
    section_index: int
    accepted: bool
    reason: str
    votes: tuple[str, ...]


def decide(
    groups: Sequence[ChangeGroup],
    plans: Sequence[PlannedComparison],
    outcomes: Sequence[CallOutcome],
) -> list[GroupVerdict]:
    """Accept a group only when the proposal wins in both presentation orders."""
    by_call = {outcome.call_id: outcome for outcome in outcomes}
    answers: dict[str, list[tuple[str, str | None]]] = {}
    for plan in plans:
        choice, _status = parse_comparison(
            by_call[plan.call_id].response if plan.call_id in by_call else None
        )
        answers.setdefault(plan.group_key, []).append((plan.first, choice))

    verdicts: list[GroupVerdict] = []
    for group in groups:
        rounds = answers.get(group.key, [])
        picks: list[str] = []
        for first, choice in rounds:
            if choice is None:
                picks.append("none")
            elif choice == "EQUAL":
                picks.append("equal")
            elif choice == "ONE":
                picks.append(first)
            else:
                picks.append("proposed" if first == "base" else "base")
        accepted = len(picks) == 2 and all(pick == "proposed" for pick in picks)
        if accepted:
            reason = "unanimous"
        elif "none" in picks:
            reason = "no_answer"
        elif len(set(picks)) > 1:
            reason = "order_dependent"
        elif picks and picks[0] == "equal":
            reason = "equal"
        else:
            reason = "base_preferred"
        verdicts.append(
            GroupVerdict(group.key, group.section_index, accepted, reason, tuple(picks))
        )
    return verdicts


def merge_cuts(
    base: Sequence[int],
    proposed: Sequence[int],
    groups: Sequence[ChangeGroup],
    verdicts: Mapping[str, bool],
) -> tuple[int, ...]:
    """Base cuts everywhere, the proposal's cuts inside accepted groups only."""
    cuts = set(base)
    for group in groups:
        if not verdicts.get(group.key, False):
            continue
        cuts -= set(group.base_cuts)
        cuts |= set(group.proposed_cuts)
    return tuple(sorted(cuts))


def collect(
    plans: Sequence[PlannedComparison],
    *,
    provider: BoundaryJudgeModel | None,
    cache: Mapping[str, str] | None = None,
    concurrency: int = 8,
) -> list[CallOutcome]:
    return collect_votes(plans, provider=provider, cache=cache, concurrency=concurrency)


def summarise(verdicts: Sequence[GroupVerdict]) -> dict[str, Any]:
    reasons: dict[str, int] = {}
    for verdict in verdicts:
        reasons[verdict.reason] = reasons.get(verdict.reason, 0) + 1
    return {
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "group_count": len(verdicts),
        "accepted": sum(1 for verdict in verdicts if verdict.accepted),
        "reverted": sum(1 for verdict in verdicts if not verdict.accepted),
        "reasons": dict(sorted(reasons.items())),
    }
