"""Deep Analysis: structure-first chunking with a backend LLM boundary judge.

The product's two ingest modes:

    Standard       -- Structure-only. Fast and deterministic.
    Deep Analysis  -- Structure + LLM-assisted chunking: on important
                      documents, hard chunk boundaries are judged by a
                      generative model **during backend ingest only**.

The judge's scope is deliberately tiny. Structure decides everything it can
decide: where sections begin, that an oversized section must be cut, which
cuts are admissible under the size rules -- and a label seam (a run-in
subheading a reader already pauses at) is structure's own cut, never sent to
the model. The LLM is consulted **only at a plain budget cut where more than
one admissible position exists**, and its whole vocabulary is ``SPLIT`` /
``KEEP`` per candidate boundary. It never chats with a user, never generates
an answer, never retrieves, never touches the vector index, and never
assembles generation context. One decision window, at ingest, on a bounded
local excerpt.

**One provider call per decision window** (the v2 batching): all admissible
candidates of one planning step are marked ``[CANDIDATE Cn]`` inside a single
prompt -- shared context shown once, never repeated per candidate -- and the
model answers a JSON array with one ``SPLIT``/``KEEP`` per candidate. The
model is never offered the final selection (no ``selected_candidate``); the
choice among its per-candidate verdicts stays a client-side deterministic
rule. On KKB 2024 this turns 232 per-candidate calls into 49 window calls
without moving a single boundary decision rule.

Determinism and fallback:

* a plain budget cut with zero or one admissible position never calls the
  model, and a label-seam cut never does either;
* among candidates the model marked SPLIT, the **latest** wins (the cut that
  fills closest to the target -- greedy's own preference), so several SPLITs
  cannot make the result depend on answer order;
* all-KEEP still cuts, at the greedy position, because the budget forces a
  cut -- the audit records ``forced_greedy_all_keep``;
* an unparseable or failing model response abandons the judge **for that
  whole window** and falls back to the deterministic structure cut, recorded
  as ``parse_error`` / ``provider_error``. The parser is strict about
  everything that steers: a missing, duplicate, or unknown ``candidate_id``
  or an invalid ``decision`` refuses the entire window -- a half-parsed
  answer never mixes with structural defaults. Free-text reasoning is never
  an input to the algorithm: only the parsed ``decision`` and ``reason_code``
  fields survive, and only ``decision`` steers anything.

The splitting walk is ``structural_chunker.chunk_units`` step for step -- the
same seamed ceiling, the same label-seam cuts, the same greedy budget cuts --
with the judge as the single injection point. With a judge that answers KEEP
everywhere, or no judge at all, the output is byte-identical to
:func:`amsc.structural_chunker.chunk_units`; a test pins that, which is what
keeps the shared skeleton honest.

**Backend-only.** The API key of a real provider is read from a configurable
environment variable at request time and is never written to disk, artifacts
or any viewer HTML; browsers never call a model. The provider interface is
generative-model-agnostic (MiniMax-class models included) and no model name
is hardcoded -- :class:`OpenAICompatibleJudgeProvider` requires the model id
explicitly and is **NOT VERIFIED** against any live service. Embeddings play
no role here: Qwen3-Embedding-8B is reserved as a future *retrieval*
embedding candidate, and the embedding-assisted hybrid stays a research
baseline in :mod:`amsc.hybrid_chunker` / :mod:`amsc.semantic_assist`.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, Sequence

from .models import RawDocumentUnit
from .structural_chunker import (
    RENDER_SEPARATOR,
    Piece,
    Section,
    _render,
    _sections,
)
from .tokenization import TokenCounter

TUNING_STATUS = "poc_initial_not_optimized"

DECISION_SPLIT = "SPLIT"
DECISION_KEEP = "KEEP"

#: The audit vocabulary. ``reason_code`` never steers the algorithm; it exists
#: so a human can read why the model said what it said without free text
#: becoming an input.
REASON_CODES = (
    "TOPIC_SHIFT",
    "CONTINUATION",
    "LIST_CONTINUATION",
    "TABLE_CONTINUATION",
    "NEW_SUBTOPIC",
    "OTHER",
)

#: Character budget per excerpt side sent to the model. Local context only.
EXCERPT_CHARS = 700

#: Marks elided text inside a long piece excerpt.
ELISION = "[...]"

_UNIT_KIND = {"h": "heading", "p": "paragraph", "l": "list", "t": "table", "v": "visual"}


class ProductChunkingMode(str, Enum):
    """The user-facing ingest switch."""

    STANDARD = "standard"
    DEEP_ANALYSIS = "deep_analysis"


class BoundaryJudgeModel(Protocol):
    """A generative model that answers one bounded prompt with text.

    Provider-agnostic on purpose: anything that can complete a prompt --
    an OpenAI-compatible endpoint, a MiniMax-class company model, a test
    double -- fits. The judge builds the prompt and parses the answer; the
    provider only transports.
    """

    @property
    def model_id(self) -> str: ...

    def complete(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class JudgeConfig:
    min_tokens: int = 160
    target_tokens: int = 700
    soft_max_tokens: int = 900
    hard_max_tokens: int = 1126
    respect_semantic_roles: bool = True
    tuning_status: str = TUNING_STATUS


@dataclass(frozen=True)
class CandidateDecision:
    """One candidate boundary as the model judged it."""

    cut_after_unit_id: str
    cut_before_unit_id: str
    decision: str
    reason_code: str


@dataclass(frozen=True)
class BoundaryAudit:
    """One consulted planning step, exactly as it happened.

    This is the whole surface a viewer may later show: where the model was
    asked, what it answered, what was chosen, and whether structure had to
    take over.
    """

    section_heading: str | None
    section_path: tuple[str, ...]
    step: int
    candidate_count: int
    decisions: tuple[CandidateDecision, ...]
    chosen_after_unit_id: str
    chosen_equals_greedy: bool
    fallback: str | None
    model_id: str | None


@dataclass(frozen=True)
class JudgeChunkResult:
    mode: ProductChunkingMode
    chunks: list[dict[str, Any]]
    diagnostics: dict[str, Any]
    audit: tuple[BoundaryAudit, ...]


def _unit_kind(unit_id: str) -> str:
    return _UNIT_KIND.get(unit_id.split("-", 1)[0], "unknown")


def _span_excerpt(text: str, *, head: bool, tail: bool) -> str:
    """A bounded view of one piece inside a window prompt.

    ``head`` keeps the opening (it is the context after a preceding
    candidate), ``tail`` keeps the ending (context before a following one);
    a middle piece keeps both, with the middle of its text elided.
    """
    budget = EXCERPT_CHARS * (int(head) + int(tail))
    if len(text) <= budget:
        return text
    if head and tail:
        return f"{text[:EXCERPT_CHARS]}\n{ELISION}\n{text[-EXCERPT_CHARS:]}"
    return text[:EXCERPT_CHARS] if head else text[-EXCERPT_CHARS:]


def candidate_labels(count: int) -> list[str]:
    """``C1`` .. ``Cn`` in candidate (document) order."""
    return [f"C{ordinal}" for ordinal in range(1, count + 1)]


def build_window_prompt(
    *,
    heading: str | None,
    section_path: Sequence[str],
    pieces: Sequence[Piece],
    start: int,
    admissible: Sequence[int],
) -> str:
    """The one prompt per decision window. Deterministic, local, bounded.

    Every admissible cut appears once as a ``[CANDIDATE Cn | cut before ...]``
    marker between the two pieces it would separate; each piece's text is
    shown once (excerpted), never repeated per candidate, so the model
    compares all candidates in one shared context. The final selection is
    deliberately not on offer -- the model judges each candidate on its own.
    """
    labels = dict(zip(admissible, candidate_labels(len(admissible))))
    lo, hi = min(admissible), max(admissible)
    lines = [
        "You judge candidate chunk boundaries inside one section of a "
        "document that is being split because it exceeds a size budget.",
        f"The text below contains {len(admissible)} candidate boundaries, "
        "marked [CANDIDATE Cn | cut before ...] in document order.",
        "For EVERY candidate, decide SPLIT or KEEP. Do not pick a best "
        "candidate; judge each boundary on its own.",
        "Answer with a single JSON array and nothing else, one object per "
        "candidate, for example:",
        '[{"candidate_id": "C1", "decision": "SPLIT", '
        '"reason_code": "TOPIC_SHIFT"}, '
        '{"candidate_id": "C2", "decision": "KEEP", '
        '"reason_code": "CONTINUATION"}]',
        '"decision" must be "SPLIT" or "KEEP". "reason_code" must be one '
        "of: " + ", ".join(REASON_CODES) + ".",
        "SPLIT means: a reader would accept a chunk boundary here.",
        "KEEP means: the two sides belong together; prefer cutting elsewhere.",
        f"Section heading: {heading or '(none)'}",
        f"Section path: {' > '.join(section_path) or '(none)'}",
    ]
    if lo - 1 > start:
        lines.append(
            f"(The chunk under construction already holds {lo - 1 - start} "
            "earlier unit(s) of this section, not shown.)"
        )
    lines.append(f"Text (excerpts; {ELISION} marks elided text):")
    for position in range(lo - 1, hi + 1):
        piece = pieces[position]
        kind = _unit_kind(piece.unit_id)
        if position in labels:
            lines.append(
                f"[CANDIDATE {labels[position]} | cut before "
                f"{kind} {piece.unit_id}]"
            )
        lines.append(f"[{kind} {piece.unit_id}]")
        lines.append(_span_excerpt(piece.text, head=position >= lo, tail=position < hi))
    return "\n".join(lines) + "\n"


_CODE_FENCE = re.compile(r"```[a-zA-Z0-9_-]*")


def _payload_rows(raw: str) -> list[Any] | None:
    """The JSON array in a model answer, tolerating fences and one wrapper.

    Accepted shapes: a bare array; an object whose ``decisions`` key holds
    the array; either of those inside a markdown code fence or surrounding
    prose. Nothing is ever completed by guesswork -- if no candidate slice
    parses as JSON, the answer is refused.
    """
    text = _CODE_FENCE.sub("", raw or "").strip()
    candidates = [text]
    array_start, array_end = text.find("["), text.rfind("]")
    if 0 <= array_start < array_end:
        candidates.append(text[array_start : array_end + 1])
    object_start, object_end = text.find("{"), text.rfind("}")
    if 0 <= object_start < object_end:
        candidates.append(text[object_start : object_end + 1])
    for candidate in candidates:
        try:
            loaded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            loaded = loaded.get("decisions")
        if isinstance(loaded, list):
            return loaded
    return None


def parse_window_decisions(
    raw: str, expected_candidate_ids: Sequence[str]
) -> dict[str, tuple[str, str]] | None:
    """Per-candidate ``(decision, reason_code)`` by id, or None to fall back.

    Strict on everything that steers: every expected candidate exactly once,
    no unknown or duplicate ids, decisions strictly SPLIT/KEEP. Any deviation
    refuses the WHOLE window so a half-parsed answer never mixes with
    structural defaults. Only ``reason_code`` is lenient (unknown becomes
    ``OTHER``) because it never steers anything.
    """
    rows = _payload_rows(raw)
    if rows is None:
        return None
    expected = set(expected_candidate_ids)
    decisions: dict[str, tuple[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            return None
        candidate_id = str(row.get("candidate_id", "")).strip()
        if candidate_id not in expected or candidate_id in decisions:
            return None
        decision = str(row.get("decision", "")).strip().upper()
        if decision not in (DECISION_SPLIT, DECISION_KEEP):
            return None
        reason = str(row.get("reason_code", "")).strip().upper()
        decisions[candidate_id] = (
            decision,
            reason if reason in REASON_CODES else "OTHER",
        )
    if set(decisions) != expected:
        return None
    return decisions


def _judge_step(
    judge: BoundaryJudgeModel,
    section: Section,
    pieces: Sequence[Piece],
    start: int,
    admissible: Sequence[int],
    greedy: int,
    step: int,
) -> tuple[int, BoundaryAudit, dict[str, int]]:
    """One decision window: one provider call, one decision per candidate."""
    counts = {"calls": 0, "split": 0, "keep": 0, "fallback": 0}
    labels = candidate_labels(len(admissible))
    prompt = build_window_prompt(
        heading=section.heading,
        section_path=section.section_path,
        pieces=pieces,
        start=start,
        admissible=admissible,
    )
    decisions: list[CandidateDecision] = []
    fallback: str | None = None
    parsed: dict[str, tuple[str, str]] | None = None
    try:
        counts["calls"] += 1
        raw = judge.complete(prompt)
    except Exception:
        fallback = "provider_error"
    else:
        parsed = parse_window_decisions(raw, labels)
        if parsed is None:
            fallback = "parse_error"

    chosen = greedy
    if fallback is None and parsed is not None:
        for label, stop in zip(labels, admissible):
            decision, reason = parsed[label]
            counts["split" if decision == DECISION_SPLIT else "keep"] += 1
            decisions.append(
                CandidateDecision(
                    cut_after_unit_id=pieces[stop - 1].unit_id,
                    cut_before_unit_id=pieces[stop].unit_id,
                    decision=decision,
                    reason_code=reason,
                )
            )
        approved = [
            stop
            for stop, verdict in zip(admissible, decisions)
            if verdict.decision == DECISION_SPLIT
        ]
        if approved:
            chosen = approved[-1]
        else:
            fallback = "forced_greedy_all_keep"
    else:
        counts["fallback"] = 1

    entry = BoundaryAudit(
        section_heading=section.heading,
        section_path=tuple(section.section_path),
        step=step,
        candidate_count=len(admissible),
        decisions=tuple(decisions),
        chosen_after_unit_id=pieces[chosen - 1].unit_id,
        chosen_equals_greedy=chosen == greedy,
        fallback=fallback,
        model_id=getattr(judge, "model_id", None),
    )
    return chosen, entry, counts


def chunk_units_with_judge(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    judge: BoundaryJudgeModel | None,
    config: JudgeConfig = JudgeConfig(),
) -> JudgeChunkResult:
    """Structure-first chunking; the judge speaks only at real choices.

    The splitting walk reproduces ``structural_chunker.chunk_units`` exactly
    (seamed ceiling, label-seam cuts, greedy budget cuts). The judge's single
    injection point is a plain budget cut with two or more admissible
    positions -- one provider call for that whole window, one structured
    decision per candidate; everywhere else the structural decision stands
    untouched.
    """
    sections = _sections(
        units, counter, config.hard_max_tokens, config.respect_semantic_roles
    )

    audit: list[BoundaryAudit] = []
    consulted = calls = fallbacks = changed = 0
    split_votes = keep_votes = 0
    step = 0

    split_sections: list[Section] = []
    for section in sections:
        seamed = config.respect_semantic_roles and any(
            piece.label for piece in section.pieces
        )
        ceiling = config.target_tokens if seamed else config.soft_max_tokens
        if section.tokens <= ceiling:
            split_sections.append(section)
            continue
        head_cost = counter.count(section.heading) + 2 if section.heading else 0
        pieces = section.pieces
        totals = [0]
        for piece in pieces:
            totals.append(totals[-1] + piece.tokens)

        def size(start: int, stop: int) -> int:
            return head_cost + totals[stop] - totals[start]

        cuts: list[int] = []
        start = 0
        index = 0
        current_tokens = 0
        while index < len(pieces):
            piece = pieces[index]
            projected = head_cost + current_tokens + piece.tokens
            at_label = piece.label and current_tokens >= config.min_tokens
            if index > start and (projected > config.target_tokens or at_label):
                greedy = index
                chosen = greedy
                # A label seam is structure's own cut; only a plain budget
                # cut with a genuine choice consults the model.
                if judge is not None and not at_label:
                    admissible = [
                        stop
                        for stop in range(start + 1, index + 1)
                        if config.min_tokens
                        <= size(start, stop)
                        <= config.target_tokens
                    ]
                    if len(admissible) >= 2:
                        consulted += 1
                        step += 1
                        chosen, entry, counts = _judge_step(
                            judge, section, pieces, start, admissible, greedy, step
                        )
                        audit.append(entry)
                        calls += counts["calls"]
                        split_votes += counts["split"]
                        keep_votes += counts["keep"]
                        fallbacks += counts["fallback"]
                        if chosen != greedy:
                            changed += 1
                cuts.append(chosen)
                start = chosen
                current_tokens = totals[index] - totals[chosen]
                continue  # re-test this piece against the shortened block
            current_tokens += piece.tokens
            index += 1

        block_start = 0
        for stop in [*cuts, len(pieces)]:
            if stop <= block_start:
                continue
            block = Section(section.heading, section.section_path)
            block.pieces.extend(pieces[block_start:stop])
            split_sections.append(block)
            block_start = stop

    # Undersized same-section neighbours are rejoined -- the structural
    # chunker's own step, mirrored the way the hybrid arm mirrors it, and
    # guarded the same way: the no-judge path is asserted byte-identical to
    # structural_chunker.chunk_units.
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
                "chunk_id": f"{document_id}:s-chunk-{index:04d}",
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

    return JudgeChunkResult(
        mode=ProductChunkingMode.DEEP_ANALYSIS
        if judge is not None
        else ProductChunkingMode.STANDARD,
        chunks=chunks,
        diagnostics={
            "mode": "deep_analysis" if judge is not None else "standard",
            "llm_boundary_judge": judge is not None,
            "section_count": len(sections),
            # decision_window_count / provider_call_count /
            # candidate_decision_count are the batching-era names; the
            # consulted_boundary_count and llm_call_count spellings stay
            # because chat_rag's ingest report reads them.
            "consulted_boundary_count": consulted,
            "decision_window_count": consulted,
            "llm_call_count": calls,
            "provider_call_count": calls,
            "candidate_decision_count": split_votes + keep_votes,
            "split_votes": split_votes,
            "keep_votes": keep_votes,
            "fallback_count": fallbacks,
            "changed_from_greedy_count": changed,
            "tuning_status": config.tuning_status,
        },
        audit=tuple(audit),
    )


def chunk_with_product_mode(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    mode: ProductChunkingMode = ProductChunkingMode.STANDARD,
    judge: BoundaryJudgeModel | None = None,
    config: JudgeConfig = JudgeConfig(),
) -> JudgeChunkResult:
    """The product switch: Standard, or Deep Analysis with a judge."""
    if mode is ProductChunkingMode.STANDARD:
        return chunk_units_with_judge(units, counter=counter, judge=None, config=config)
    if judge is None:
        raise ValueError(
            "Deep Analysis needs a boundary judge model; Standard does not"
        )
    return chunk_units_with_judge(units, counter=counter, judge=judge, config=config)


def audit_rows(result: JudgeChunkResult) -> list[dict[str, Any]]:
    """The audit as plain rows -- what a viewer may show, and nothing more."""
    rows: list[dict[str, Any]] = []
    for entry in result.audit:
        rows.append(
            {
                "section_heading": entry.section_heading,
                "section_path": list(entry.section_path),
                "step": entry.step,
                "candidate_count": entry.candidate_count,
                "decisions": [
                    {
                        "cut_after_unit_id": verdict.cut_after_unit_id,
                        "cut_before_unit_id": verdict.cut_before_unit_id,
                        "decision": verdict.decision,
                        "reason_code": verdict.reason_code,
                    }
                    for verdict in entry.decisions
                ],
                "chosen_after_unit_id": entry.chosen_after_unit_id,
                "chosen_equals_greedy": entry.chosen_equals_greedy,
                "fallback": entry.fallback,
                "model_id": entry.model_id,
            }
        )
    return rows


# --------------------------------------------------------------------------
# provider adapter (backend-only; NOT VERIFIED against any live service)
# --------------------------------------------------------------------------

JUDGE_ADAPTER_STATUS = "adapter_only_not_verified"


class OpenAICompatibleJudgeProvider:
    """Chat-completions transport for the judge. Backend ingest only.

    No model is hardcoded: ``model`` is required, and the key's environment
    variable name is configurable so a company deployment (a MiniMax-class
    model behind a different gateway) needs no code change. Only the minimal
    OpenAI-compatible payload is sent (``model`` + ``messages``); nothing else
    about the provider is assumed. The key is read from the environment at
    request time, used in the Authorization header, and never persisted.
    """

    status = JUDGE_ADAPTER_STATUS

    def __init__(
        self,
        model: str,
        *,
        endpoint: str,
        api_key_env: str = "OPENROUTER_API_KEY",
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model = model
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    @property
    def model_id(self) -> str:
        return self.model

    def _key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise RuntimeError(
                f"{self.api_key_env} is not set; the boundary judge cannot run "
                "without it (and it is never stored)"
            )
        return key

    def complete(self, prompt: str) -> str:
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(
                {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._key()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError(
                "judge endpoint returned an unexpected shape; refusing to guess"
            ) from error
