"""Deep Analysis: a quality-driven selector over the structure-first walk.

The Agentic Chunker asked a generative model to vote SPLIT/KEEP at the budget
cuts the greedy walk had already chosen, and let the latest SPLIT win. Scored
against blind human preference on KKB 2024 that produced 3 wins, 4 losses and
0 ties over 7 changed boundaries -- and the audit says why: of the twelve
Standard cuts a human called unacceptable, six were never shown to the model
(the call was rejected, or the window had a single candidate and was never
consulted), four were shown and mis-voted, and two have no correct boundary in
the canonical at all. The binary vote was not the bottleneck; *selection* was.

So this module inverts the arrangement. The deterministic quality contract of
:mod:`amsc.boundary_quality` becomes the objective rather than an after-the-fact
audit, and the model -- when it runs at all -- only supplies a preference among
partitions the contract already accepts.

    per section: enumerate every partition of the piece sequence
                 -> lexicographic cost, Standard's own partition wins ties
                 -> V0: revert the section unless its smell vector is <= Standard's

The cost vector, compared component by component:

    ( smells, forbidden_cuts, below_min, above_soft_max, strength_penalty,
      cuts_differing_from_standard, size_deviation )

`smells` are exactly the deterministic types the evaluator counts, so the
optimiser and the metric cannot drift apart. `forbidden_cuts` and
`strength_penalty` are the *only* channels a model can reach; the preference
term sits below every defect *and* every size counter, so a model chooses
among partitions the contract already rates equally rather than reshaping the
document, and both are absent unless votes are supplied -- which is what makes the guarantee
mechanical: **with no votes the output is a pure function of the canonical, and
no partition can ever leave a section structurally worse than Standard.**

Three consequences worth naming, because they are the measured wins:

* the admissible band is no longer ``[min, target]``. Any piece boundary whose
  blocks fit the hard cap is a candidate, with ``above_soft_max`` as a cost.
  Widening it is what reaches the forced single-candidate cuts (33 on KKB 2024)
  the vote-based design could never touch.
* the rejoin is inside the objective, not a post-pass veto. A below-min tail
  that keeps a label with its body is preferred to an orphaned label; Standard
  already emits 87 below-min chunks of 424, so this is not a new size class.
* Standard's partition is an explicit candidate and wins every tie, so a
  section only moves when the contract is *strictly* satisfied.

All numeric knobs are ``poc_initial_not_optimized`` and were not tuned against
a held-out set.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import boundary_quality as bq
from .io import load_jsonl_units
from .models import RawDocumentUnit
from .structural_chunker import RENDER_SEPARATOR, Piece, Section, _render, _sections
from .tokenization import TiktokenTokenCounter, TokenCounter

TUNING_STATUS = "poc_initial_not_optimized"

#: Cost components in comparison order. Every one is minimised.
COST_KEYS: tuple[str, ...] = (
    "smells",
    "forbidden",
    "below_min",
    "above_soft_max",
    "strength_penalty",
    "cut_diff",
    "size_deviation",
)

#: A cut the model rates below this costs; above it, it pays. Centring the
#: term matters more than its value: an uncentred ``-strength`` grows with the
#: number of cuts, so maximising it always prefers cutting more -- the same
#: degenerate objective as "the latest SPLIT wins", and it produced 494 chunks
#: against Standard's 424 the first time this ran.
NEUTRAL_STRENGTH = 2

ROLE_COMPLETE = "complete"
ROLE_INTRODUCES_NEXT = "introduces_next"
ROLE_CONTINUES_PREVIOUS = "continues_previous"
LEFT_ROLES = (ROLE_COMPLETE, ROLE_INTRODUCES_NEXT)
RIGHT_ROLES = (ROLE_COMPLETE, ROLE_CONTINUES_PREVIOUS)


@dataclass(frozen=True)
class DeepConfig:
    """Budgets identical to the benchmarked arms; nothing here was tuned."""

    min_tokens: int = 160
    target_tokens: int = 700
    soft_max_tokens: int = 900
    hard_max_tokens: int = 1126
    respect_semantic_roles: bool = True
    max_label_words: int = 12
    #: Weight of one unit of model strength against one deterministic cut
    #: difference. Strength sits *below* every smell term, so this only ever
    #: breaks ties among partitions the contract rates identically.
    strength_scale: int = 1
    tuning_status: str = TUNING_STATUS

    def quality(self) -> bq.QualityConfig:
        return bq.QualityConfig(
            min_tokens=self.min_tokens,
            target_tokens=self.target_tokens,
            soft_max_tokens=self.soft_max_tokens,
            hard_max_tokens=self.hard_max_tokens,
            max_label_words=self.max_label_words,
        )


@dataclass(frozen=True)
class BoundaryVote:
    """One model opinion about one candidate boundary of one section.

    ``strength`` 0-3 says how strongly a reader would want a break here;
    the two roles say whether either side *forbids* one. A boundary is
    forbidden when its left piece introduces what follows, its right piece
    continues what precedes, or the strength is zero -- three ways of saying
    the same thing, kept separate so the audit can tell them apart.
    """

    cut_after_unit_id: str
    strength: int = 0
    left: str = ROLE_COMPLETE
    right: str = ROLE_COMPLETE

    @property
    def forbidden(self) -> bool:
        return (
            self.strength <= 0
            or self.left == ROLE_INTRODUCES_NEXT
            or self.right == ROLE_CONTINUES_PREVIOUS
        )


Cost = tuple[int, int, int, int, int, int, int]
_INFEASIBLE: Cost = tuple([10**9] * len(COST_KEYS))  # type: ignore[assignment]


def _add(left: Cost, right: Cost) -> Cost:
    return tuple(a + b for a, b in zip(left, right))  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Standard's own partition, per section
# --------------------------------------------------------------------------


def _head_cost(section: Section, counter: TokenCounter) -> int:
    return counter.count(section.heading) + 2 if section.heading else 0


def standard_groups(
    section: Section, *, counter: TokenCounter, config: DeepConfig
) -> list[list[list[Piece]]]:
    """Standard's blocks for one section, grouped exactly as it rejoins them.

    A faithful restatement of ``structural_chunker.chunk_units`` steps 1 and 2
    restricted to one section -- the frozen module is never imported for its
    behaviour here, so this is pinned by test against its real output rather
    than trusted.
    """
    head = _head_cost(section, counter)
    seamed = config.respect_semantic_roles and any(piece.label for piece in section.pieces)
    ceiling = config.target_tokens if seamed else config.soft_max_tokens

    blocks: list[list[Piece]] = []
    if section.tokens <= ceiling:
        blocks = [list(section.pieces)]
    else:
        current: list[Piece] = []
        for piece in section.pieces:
            projected = head + sum(p.tokens for p in current) + piece.tokens
            at_label = piece.label and sum(p.tokens for p in current) >= config.min_tokens
            if current and (projected > config.target_tokens or at_label):
                blocks.append(current)
                current = []
            current.append(piece)
        if current:
            blocks.append(current)

    groups: list[list[list[Piece]]] = []
    sizes: list[int] = []
    for block in blocks:
        size = sum(p.tokens for p in block) + head
        if (
            groups
            and (sizes[-1] < config.min_tokens or size < config.min_tokens)
            and sizes[-1] + size <= config.target_tokens
        ):
            groups[-1].append(block)
            sizes[-1] += size
            continue
        groups.append([block])
        sizes.append(size)
    return groups


def _group_cuts(groups: Sequence[Sequence[Sequence[Piece]]]) -> tuple[int, ...]:
    """Piece indices at which one final chunk ends and the next begins."""
    cuts: list[int] = []
    offset = 0
    for group in groups[:-1]:
        offset += sum(len(block) for block in group)
        cuts.append(offset)
    return tuple(cuts)


# --------------------------------------------------------------------------
# the selector
# --------------------------------------------------------------------------


@dataclass
class SectionPlan:
    """What the selector decided for one section, and why."""

    index: int
    heading: str | None
    section_path: tuple[str, ...]
    standard_cuts: tuple[int, ...]
    chosen_cuts: tuple[int, ...]
    cost: Cost
    standard_cost: Cost
    verdict: str
    reverted: str | None = None
    vote_count: int = 0
    forbidden_count: int = 0

    @property
    def moved(self) -> bool:
        return self.chosen_cuts != self.standard_cuts

    def as_dict(self) -> dict[str, Any]:
        return {
            "section_index": self.index,
            "heading": self.heading,
            "section_path": list(self.section_path),
            "standard_cuts": list(self.standard_cuts),
            "chosen_cuts": list(self.chosen_cuts),
            "cost": dict(zip(COST_KEYS, self.cost)),
            "standard_cost": dict(zip(COST_KEYS, self.standard_cost)),
            "verdict": self.verdict,
            "reverted": self.reverted,
            "vote_count": self.vote_count,
            "forbidden_count": self.forbidden_count,
            "moved": self.moved,
        }


class _SectionSolver:
    """Lexicographic DP over the piece boundaries of one section."""

    def __init__(
        self,
        section: Section,
        *,
        units_by_id: Mapping[str, RawDocumentUnit],
        fitting_runs: Mapping[str, int],
        counter: TokenCounter,
        config: DeepConfig,
        votes: Mapping[str, BoundaryVote],
        standard_cuts: tuple[int, ...],
        conservative: bool = False,
    ) -> None:
        self.pieces = list(section.pieces)
        self.head = _head_cost(section, counter)
        self.config = config
        self.quality = config.quality()
        self.units_by_id = units_by_id
        self.fitting_runs = fitting_runs
        self.votes = votes
        self.standard_cuts = set(standard_cuts)
        #: Second pass: a cut that is not Standard's own may carry no smell at
        #: all, which makes the resulting vector component-wise <= Standard's.
        self.conservative = conservative
        self.prefix = [0]
        for piece in self.pieces:
            self.prefix.append(self.prefix[-1] + piece.tokens)

    def block_size(self, start: int, end: int) -> int:
        return self.head + self.prefix[end] - self.prefix[start]

    def block_cost(self, start: int, end: int) -> Cost:
        size = self.block_size(start, end)
        if size > self.config.hard_max_tokens:
            return _INFEASIBLE
        below = 1 if size < self.config.min_tokens else 0
        above = 1 if size > self.config.soft_max_tokens else 0
        deviation = abs(size - self.config.target_tokens)
        return (0, 0, below, above, 0, 0, deviation)

    def cut_cost(self, index: int) -> Cost:
        """Cost of cutting between ``pieces[index - 1]`` and ``pieces[index]``."""
        left_piece, right_piece = self.pieces[index - 1], self.pieces[index]
        left = self.units_by_id.get(bq.base_unit_id(left_piece.unit_id))
        right = self.units_by_id.get(bq.base_unit_id(right_piece.unit_id))
        smells = 0
        if left is not None and right is not None:
            smells = len(
                bq.boundary_smells(
                    left,
                    right,
                    left_raw_id=left_piece.unit_id,
                    right_raw_id=right_piece.unit_id,
                    config=self.quality,
                )
            )
        left_base = bq.base_unit_id(left_piece.unit_id)
        right_base = bq.base_unit_id(right_piece.unit_id)
        run = self.fitting_runs.get(left_base)
        if run is not None and run == self.fitting_runs.get(right_base):
            smells += 1
        vote = self.votes.get(left_piece.unit_id)
        forbidden = 1 if vote is not None and vote.forbidden else 0
        penalty = 0
        if vote is not None and not vote.forbidden:
            penalty = (NEUTRAL_STRENGTH - vote.strength) * self.config.strength_scale
        diff = -1 if index in self.standard_cuts else 1
        if self.conservative and smells and index not in self.standard_cuts:
            return _INFEASIBLE
        return (smells, forbidden, 0, 0, penalty, diff, 0)

    def solve(self) -> tuple[tuple[int, ...], Cost]:
        n = len(self.pieces)
        best: list[Cost] = [_INFEASIBLE] * (n + 1)
        back: list[int] = [-1] * (n + 1)
        best[0] = tuple([0] * len(COST_KEYS))  # type: ignore[assignment]
        for end in range(1, n + 1):
            for start in range(end - 1, -1, -1):
                if self.block_size(start, end) > self.config.hard_max_tokens and start < end - 1:
                    break
                if best[start] == _INFEASIBLE:
                    continue
                block = self.block_cost(start, end)
                if block == _INFEASIBLE:
                    continue
                cut = self.cut_cost(start) if start else _ZERO
                if cut == _INFEASIBLE:
                    continue
                cost = _add(_add(best[start], block), cut)
                if cost < best[end]:
                    best[end] = cost
                    back[end] = start
        if best[n] == _INFEASIBLE:
            return tuple(range(1, n)), _INFEASIBLE
        cuts: list[int] = []
        position = n
        while position > 0:
            start = back[position]
            if start > 0:
                cuts.append(start)
            position = start
        return tuple(sorted(cuts)), best[n]

    def forbidden_at(self, cuts: Sequence[int]) -> int:
        """How many of these cuts a vote marked forbidden."""
        total = 0
        for index in cuts:
            vote = self.votes.get(self.pieces[index - 1].unit_id)
            total += int(vote is not None and vote.forbidden)
        return total

    def cost_of(self, cuts: Sequence[int]) -> Cost:
        bounds = [0, *cuts, len(self.pieces)]
        total: Cost = tuple([0] * len(COST_KEYS))  # type: ignore[assignment]
        for start, end in zip(bounds, bounds[1:]):
            block = self.block_cost(start, end)
            if block == _INFEASIBLE:
                return _INFEASIBLE
            total = _add(total, block)
            if start:
                cut = self.cut_cost(start)
                if cut == _INFEASIBLE:
                    return _INFEASIBLE
                total = _add(total, cut)
        return total


_ZERO: Cost = tuple([0] * len(COST_KEYS))  # type: ignore[assignment]


def _fitting_run_index(
    units: Sequence[RawDocumentUnit], counter: TokenCounter, config: DeepConfig
) -> dict[str, int]:
    """Unit id -> id of the fitting list run it belongs to, for run-split cost."""
    index: dict[str, int] = {}
    for number, run in enumerate(bq.list_runs(units)):
        by_id = {unit.unit_id: unit for unit in units}
        text = "\n".join(by_id[unit_id].text for unit_id in run)
        if counter.count(text) > config.target_tokens:
            continue
        for unit_id in run:
            index[unit_id] = number
    return index


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


def _section_blocks(
    section: Section, cuts: Sequence[int]
) -> list[list[list[Piece]]]:
    bounds = [0, *cuts, len(section.pieces)]
    return [[list(section.pieces[start:end])] for start, end in zip(bounds, bounds[1:])]


def _as_section_blocks(
    groups: Sequence[Sequence[Sequence[Piece]]], key: bq.SectionKey, counter: TokenCounter,
    heading: str | None,
) -> bq.SectionBlocks:
    blocks: list[bq.Block] = []
    for number, group in enumerate(groups):
        pieces = [piece for block in group for piece in block]
        text = RENDER_SEPARATOR.join(_render(heading, block) for block in group)
        blocks.append(
            bq.Block(tuple(p.unit_id for p in pieces), counter.count(text), f"b{number}")
        )
    return bq.SectionBlocks(key=key, occurrence=0, blocks=blocks)


#: One final chunk before rendering: heading, its blocks, path, source section,
#: and whether the selector moved that section.
Assembled = tuple[str | None, list[list["Piece"]], tuple[str, ...], int, bool]


def _rejoin_across_sections(
    assembled: Sequence[Assembled], *, counter: TokenCounter, config: DeepConfig
) -> list[Assembled]:
    """Reproduce the frozen walk's one cross-section merge, and only that.

    ``structural_chunker`` rejoins undersized neighbours over the whole
    document, so two *different* sections that happen to print the same
    heading text under the same path can end up in one chunk (it happens once
    on KKB 2024, at the balance-sheet continuation). Selection here is
    per-section, so that merge is restored afterwards -- but never across a
    section the selector moved, where an undersized block is a deliberate
    choice the rejoin would silently undo.
    """
    out: list[Assembled] = []
    sizes: list[int] = []
    for heading, group, path, index, moved in assembled:
        size = counter.count(
            RENDER_SEPARATOR.join(_render(heading, block) for block in group)
        )
        if out:
            previous = out[-1]
            joinable = (
                previous[3] != index
                and previous[0] == heading
                and previous[2] == path
                and not previous[4]
                and not moved
                and (sizes[-1] < config.min_tokens or size < config.min_tokens)
                and sizes[-1] + size <= config.target_tokens
            )
            if joinable:
                out[-1] = (heading, [*previous[1], *group], path, index, moved)
                sizes[-1] += size
                continue
        out.append((heading, group, path, index, moved))
        sizes.append(size)
    return out


def chunk_units(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    config: DeepConfig = DeepConfig(),
    votes: Mapping[str, BoundaryVote] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Chunk ``units`` under the quality contract; return rows and an audit.

    With ``votes`` empty this is deterministic and depends on nothing but the
    canonical. Every section is either Standard's own partition or one whose
    smell vector is component-wise no larger.
    """
    votes = dict(votes or {})
    quality = config.quality()
    sections = _sections(units, counter, config.hard_max_tokens, config.respect_semantic_roles)
    units_by_id = {unit.unit_id: unit for unit in units}
    runs = bq.list_runs(units)
    fitting_runs = _fitting_run_index(units, counter, config)

    plans: list[SectionPlan] = []
    size_trades: list[int] = []
    declined_vote_gains: list[int] = []
    assembled: list[Assembled] = []
    for index, section in enumerate(sections):
        std_groups = standard_groups(section, counter=counter, config=config)
        std_cuts = _group_cuts(std_groups)
        key: bq.SectionKey = (
            section.heading,
            (tuple(section.section_path),) if section.section_path else (),
        )
        solver = _SectionSolver(
            section,
            units_by_id=units_by_id,
            fitting_runs=fitting_runs,
            counter=counter,
            config=config,
            votes=votes,
            standard_cuts=std_cuts,
        )
        chosen, cost = solver.solve()
        std_cost = solver.cost_of(std_cuts)
        section_votes = sum(
            1 for piece in section.pieces if piece.unit_id in votes
        )
        forbidden = sum(
            1 for piece in section.pieces
            if piece.unit_id in votes and votes[piece.unit_id].forbidden
        )

        standard_view = _as_section_blocks(std_groups, key, counter, section.heading)
        std_vector = bq.section_quality(
            standard_view, units_by_id, runs=runs, counter=counter, config=quality
        ).vector

        def judge(cuts: tuple[int, ...]) -> tuple[list[list[list[Piece]]], str, bool]:
            blocks = _section_blocks(section, cuts)
            view = _as_section_blocks(blocks, key, counter, section.heading)
            vector = bq.section_quality(
                view, units_by_id, runs=runs, counter=counter, config=quality
            ).vector
            over = any(block.token_count > config.hard_max_tokens for block in view.blocks)
            verdict, traded = bq.compare_tiered(std_vector, vector)
            if (
                verdict == bq.VERDICT_WORSE
                and not over
                and bq.compare_smells(std_vector, vector) != bq.VERDICT_WORSE
                and solver.forbidden_at(cuts) < solver.forbidden_at(std_cuts)
            ):
                # The model's own defect signal fell -- a boundary it called
                # forbidden is gone -- but a size counter grew without a
                # deterministic gain to pay for it. Declined on purpose: the
                # guarantee is worth more than the headroom, and a verifier
                # that can confirm the semantic gain is what would unlock it.
                declined_vote_gains.append(index)
            if traded:
                size_trades.append(index)
            return blocks, verdict, over

        groups = std_groups
        verdict = bq.VERDICT_TIE
        reverted: str | None = None
        if chosen != std_cuts:
            blocks, verdict, over_cap = judge(chosen)
            if verdict == bq.VERDICT_WORSE or over_cap:
                # The free optimum traded one smell type for another. Re-solve
                # with every non-Standard smelly cut forbidden, which makes the
                # vector component-wise no larger by construction.
                careful = _SectionSolver(
                    section,
                    units_by_id=units_by_id,
                    fitting_runs=fitting_runs,
                    counter=counter,
                    config=config,
                    votes=votes,
                    standard_cuts=std_cuts,
                    conservative=True,
                )
                retry, retry_cost = careful.solve()
                if retry != std_cuts:
                    retry_blocks, retry_verdict, retry_over = judge(retry)
                    if retry_verdict != bq.VERDICT_WORSE and not retry_over:
                        chosen, cost, groups, verdict = retry, retry_cost, retry_blocks, retry_verdict
                        reverted = "conservative_pass"
                if reverted is None:
                    reverted = "hard_cap" if over_cap else "smell_vector"
                    chosen, groups, verdict = std_cuts, std_groups, bq.VERDICT_TIE
            else:
                groups = blocks
        plans.append(
            SectionPlan(
                index=index,
                heading=section.heading,
                section_path=tuple(section.section_path),
                standard_cuts=std_cuts,
                chosen_cuts=chosen,
                cost=cost,
                standard_cost=std_cost,
                verdict=verdict,
                reverted=reverted,
                vote_count=section_votes,
                forbidden_count=forbidden,
            )
        )
        moved_section = chosen != std_cuts
        for group in groups:
            assembled.append(
                (
                    section.heading,
                    [list(block) for block in group],
                    tuple(section.section_path),
                    index,
                    moved_section,
                )
            )

    assembled = _rejoin_across_sections(assembled, counter=counter, config=config)
    document_id = units[0].document_id
    rows: list[dict[str, Any]] = []
    for number, (heading, group, path, _index, _moved) in enumerate(assembled, start=1):
        text = RENDER_SEPARATOR.join(_render(heading, block) for block in group)
        tokens = counter.count(text)
        if tokens > config.hard_max_tokens:  # pragma: no cover - guarded by revert
            raise AssertionError(f"chunk {number} exceeds hard cap: {tokens}")
        pieces = [piece for block in group for piece in block]
        rows.append(
            {
                "chunk_id": f"{document_id}:d-chunk-{number:04d}",
                "text": text,
                "unit_ids": [p.unit_id for p in pieces],
                "token_count": tokens,
                "pages": sorted({p.page for p in pieces if p.page is not None}),
                "section_paths": [list(path)] if path else [],
                "heading": heading,
                "split_strategies": sorted({p.strategy for p in pieces}),
            }
        )

    moved = [plan for plan in plans if plan.moved]
    audit = {
        "config": {**config.__dict__},
        "section_count": len(sections),
        "chunk_count": len(rows),
        "sections_moved": len(moved),
        "sections_reverted": sum(
            1 for plan in plans if plan.reverted in ("smell_vector", "hard_cap")
        ),
        "revert_reasons": {
            reason: sum(1 for plan in plans if plan.reverted == reason)
            for reason in ("smell_vector", "hard_cap", "conservative_pass")
        },
        "size_trade_count": len(set(size_trades)),
        "declined_vote_gain_count": len(set(declined_vote_gains)),
        "vote_count": len(votes),
        "forbidden_vote_count": sum(1 for vote in votes.values() if vote.forbidden),
        "verdicts": {
            verdict: sum(1 for plan in plans if plan.verdict == verdict)
            for verdict in (bq.VERDICT_BETTER, bq.VERDICT_TIE, bq.VERDICT_WORSE)
        },
        "sections": [plan.as_dict() for plan in plans if plan.moved or plan.reverted],
    }
    return rows, audit


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.deep_analysis",
        description="Deep Analysis chunking (deterministic quality contract).",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--encoding", default="cl100k_base")
    parser.add_argument("--min-tokens", type=int, default=160)
    parser.add_argument("--target-tokens", type=int, default=700)
    parser.add_argument("--soft-max-tokens", type=int, default=900)
    parser.add_argument("--hard-max-tokens", type=int, default=1126)
    parser.add_argument("--votes", type=Path, help="JSON file of boundary votes")
    args = parser.parse_args(argv)

    output = args.output.resolve()
    if any(part == "evaluation" for part in output.parts):
        raise SystemExit(f"refusing to write inside evaluation/: {output}")

    units = load_jsonl_units(args.input)
    counter = TiktokenTokenCounter(args.encoding)
    config = DeepConfig(
        min_tokens=args.min_tokens,
        target_tokens=args.target_tokens,
        soft_max_tokens=args.soft_max_tokens,
        hard_max_tokens=args.hard_max_tokens,
    )
    votes: dict[str, BoundaryVote] = {}
    if args.votes:
        payload = json.loads(args.votes.read_text(encoding="utf-8"))
        for entry in payload.get("boundaries", []):
            vote = BoundaryVote(
                cut_after_unit_id=str(entry["cut_after_unit_id"]),
                strength=int(entry.get("strength", 0)),
                left=str(entry.get("left", ROLE_COMPLETE)),
                right=str(entry.get("right", ROLE_COMPLETE)),
            )
            votes[vote.cut_after_unit_id] = vote

    rows, audit = chunk_units(units, counter=counter, config=config, votes=votes)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (output / "audit.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(audit, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({k: v for k, v in audit.items() if k != "sections"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
