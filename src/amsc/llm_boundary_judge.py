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
assembles generation context. One decision, at ingest, on a bounded local
excerpt.

Determinism and fallback:

* a plain budget cut with zero or one admissible position never calls the
  model, and a label-seam cut never does either;
* among candidates the model marked SPLIT, the **latest** wins (the cut that
  fills closest to the target -- greedy's own preference), so several SPLITs
  cannot make the result depend on call order;
* all-KEEP still cuts, at the greedy position, because the budget forces a
  cut -- the audit records ``forced_greedy_all_keep``;
* an unparseable or failing model response abandons the judge **for that
  step** and falls back to the deterministic structure cut, recorded as
  ``parse_error`` / ``provider_error``. Free-text reasoning is never an input
  to the algorithm: only the parsed ``decision`` and ``reason_code`` fields
  survive, and only ``decision`` steers anything.

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


def _excerpt(pieces: Sequence[Piece], *, tail: bool) -> str:
    """A bounded excerpt of the content just before or after a boundary."""
    text = pieces[-1].text if tail else pieces[0].text
    if len(text) <= EXCERPT_CHARS:
        return text
    return text[-EXCERPT_CHARS:] if tail else text[:EXCERPT_CHARS]


def build_prompt(
    *,
    heading: str | None,
    section_path: Sequence[str],
    before: Sequence[Piece],
    after: Sequence[Piece],
) -> str:
    """The one prompt shape the judge sends. Deterministic, local, bounded."""
    left, right = before[-1], after[0]
    return (
        "You judge ONE candidate chunk boundary inside one section of a "
        "document that is being split because it exceeds a size budget.\n"
        "Answer with a single JSON object and nothing else:\n"
        '{"decision": "SPLIT" | "KEEP", "reason_code": "TOPIC_SHIFT" | '
        '"CONTINUATION" | "LIST_CONTINUATION" | "TABLE_CONTINUATION" | '
        '"NEW_SUBTOPIC" | "OTHER"}\n'
        "SPLIT means: a reader would accept a chunk boundary here.\n"
        "KEEP means: the two sides belong together; prefer cutting elsewhere.\n"
        f"Section heading: {heading or '(none)'}\n"
        f"Section path: {' > '.join(section_path) or '(none)'}\n"
        f"Content before the candidate boundary "
        f"[{_unit_kind(left.unit_id)} {left.unit_id}]:\n"
        f"{_excerpt(before, tail=True)}\n"
        f"Content after the candidate boundary "
        f"[{_unit_kind(right.unit_id)} {right.unit_id}]:\n"
        f"{_excerpt(after, tail=False)}\n"
    )


_JSON_OBJECT = re.compile(r"\{.*?\}", re.S)


def parse_decision(raw: str) -> tuple[str, str] | None:
    """``(decision, reason_code)`` from a model answer, or None to fall back.

    Strict on the field that matters: an unknown decision refuses; an unknown
    or missing reason_code becomes ``OTHER`` because it never steers anything.
    """
    match = _JSON_OBJECT.search(raw or "")
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    decision = str(payload.get("decision", "")).strip().upper()
    if decision not in (DECISION_SPLIT, DECISION_KEEP):
        return None
    reason = str(payload.get("reason_code", "")).strip().upper()
    return decision, reason if reason in REASON_CODES else "OTHER"


def _judge_step(
    judge: BoundaryJudgeModel,
    section: Section,
    pieces: Sequence[Piece],
    start: int,
    admissible: Sequence[int],
    greedy: int,
    step: int,
) -> tuple[int, BoundaryAudit, dict[str, int]]:
    """Ask the model about every admissible cut of one planning step."""
    counts = {"calls": 0, "split": 0, "keep": 0, "fallback": 0}
    decisions: list[CandidateDecision] = []
    fallback: str | None = None
    for stop in admissible:
        prompt = build_prompt(
            heading=section.heading,
            section_path=section.section_path,
            before=pieces[start:stop],
            after=pieces[stop:],
        )
        try:
            counts["calls"] += 1
            raw = judge.complete(prompt)
        except Exception:
            fallback = "provider_error"
            break
        parsed = parse_decision(raw)
        if parsed is None:
            fallback = "parse_error"
            break
        decision, reason = parsed
        counts["split" if decision == DECISION_SPLIT else "keep"] += 1
        decisions.append(
            CandidateDecision(
                cut_after_unit_id=pieces[stop - 1].unit_id,
                cut_before_unit_id=pieces[stop].unit_id,
                decision=decision,
                reason_code=reason,
            )
        )

    chosen = greedy
    if fallback is None:
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
    positions; everywhere else the structural decision stands untouched.
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
            "consulted_boundary_count": consulted,
            "llm_call_count": calls,
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
