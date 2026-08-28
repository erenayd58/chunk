"""Deterministic boundary quality for structure-first chunk partitions.

Kademe 0 of the Deep Analysis v2 plan: the shape-based *smell* inventory, the
per-section quality vector, the "never structurally worse than Standard"
comparison rule, and the *change groups* a verifier judges. Everything here
is a pure function of canonical units and chunk rows -- no model, no wall
clock, no word lists. Every predicate reads typography (emphasis wrapping),
punctuation (a trailing ``:``, sentence ends), orthography (a lower-case
start, a footnote marker), unit type/role, and adjacency. Anaphora and topic
are deliberately absent: they are the LLM's domain and are judged by the
verifier, never by a lexicon.

**Contract.** Smells are attached to *sections* and computed on the *final*
blocks of a partition. Two partitions of the same section are compared per
smell type: Deep is *not worse* than Standard iff ``count_D[t] <= count_S[t]``
for every type ``t`` (a multiset subset); it is *strictly better* iff the sum
is smaller and no type is larger; equal vectors tie. Blocks in
``(target, soft_max]`` are not a smell. Blocks below ``min`` and above
``soft_max`` are counted under the same ``<=`` rule because Standard already
emits both (87 and 16 of 424 chunks on KKB 2024).

Only partitions of the *same* section sequence can be compared -- the
structure-first family (Structure-only, Agentic, Deep Analysis). The markdown
arm has no sections in this sense and is out of scope.

All numeric knobs are ``poc_initial_not_optimized``.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .chunk_mapping import base_unit_id
from .models import RawDocumentUnit, SemanticRole, UnitType
from .tokenization import TokenCounter

TUNING_STATUS = "poc_initial_not_optimized"

#: The deterministic smell types, in report order.
SMELL_TYPES: tuple[str, ...] = (
    "orphan_label",
    "lead_in_cut",
    "fragment_cut",
    "table_split",
    "run_split_when_fits",
    "continuation_cut",
)
#: Size counters compared under the same ``<=`` rule; never a smell by themselves.
SIZE_COUNTERS: tuple[str, ...] = ("below_min", "above_soft_max")
VECTOR_KEYS: tuple[str, ...] = SMELL_TYPES + SIZE_COUNTERS

VERDICT_BETTER = "better"
VERDICT_TIE = "tie"
VERDICT_WORSE = "worse"


@dataclass(frozen=True)
class QualityConfig:
    """Budgets identical to the benchmarked arms plus the label-shape cap."""

    min_tokens: int = 160
    target_tokens: int = 700
    soft_max_tokens: int = 900
    hard_max_tokens: int = 1126
    max_label_words: int = 12
    tuning_status: str = TUNING_STATUS


# --------------------------------------------------------------------------
# shape predicates (typography, punctuation, orthography -- never a lexicon)
# --------------------------------------------------------------------------

_EMPHASIS_EDGE = re.compile(r"^[\s*_]+|[\s*_]+$")
_EMPHASIS_WRAPPED = re.compile(r"^[*_]{1,3}(?=\S).*\S[*_]{1,3}\s*:?$", re.S)
_SENTENCE_END = (".", "!", "?", "…")
_PLACEHOLDER = re.compile(r"^\s*[*_]*\s*==>")
_FOOTNOTE_START = re.compile(r"^(?:\(\*+\)|\*+(?=\s)|\(\d{1,2}\)(?=\s))")
_ENUMERATOR_START = re.compile(r"^\(?[a-z]{1,4}[.)](?=\s)")
_LIST_MARKER_START = re.compile(r"^(?:[-*+•]|\d+[.)])\s")
_OPENING_QUOTES = "\"'“‘"


def strip_emphasis(text: str) -> str:
    """Text without its leading/trailing markdown emphasis and whitespace."""
    return _EMPHASIS_EDGE.sub("", text)


def is_emphasis_wrapped(text: str) -> bool:
    """A single line whose whole content sits inside bold(-italic) markers."""
    stripped = text.strip()
    if "\n" in stripped or "**" not in stripped:
        return False
    return _EMPHASIS_WRAPPED.match(stripped) is not None


def is_display(unit: RawDocumentUnit) -> bool:
    return unit.type == UnitType.HEADING and unit.semantic_role == SemanticRole.DISPLAY


def is_label_like(unit: RawDocumentUnit, *, max_words: int = 12) -> bool:
    """A unit that names what follows it and must not end a chunk.

    A heading that does not open a section is a label by the canonical's own
    decision -- unless its role is ``display`` (a slogan or banner labels
    nothing; 36 of the 42 Standard chunk tails ending in a heading are
    display headings and are not orphans). A paragraph is label-like on shape
    alone: one line, wholly emphasis-wrapped, short, no sentence end, at
    least one alphabetic word, not a picture placeholder.
    """
    if unit.type == UnitType.HEADING:
        return unit.opens_section is False and not is_display(unit)
    if unit.type != UnitType.PARAGRAPH:
        return False
    text = unit.text.strip()
    if _PLACEHOLDER.match(text) or not is_emphasis_wrapped(text):
        return False
    inner = strip_emphasis(text).rstrip(":").strip()
    if not inner or inner.endswith(_SENTENCE_END):
        return False
    if len(inner.split()) > max_words:
        return False
    return any(character.isalpha() for character in inner)


def is_lead_in(unit: RawDocumentUnit) -> bool:
    """A non-heading unit that ends with a colon introduces what follows."""
    if unit.type == UnitType.HEADING:
        return False
    return strip_emphasis(unit.text).endswith(":")


def continues_previous(unit: RawDocumentUnit) -> bool:
    """A paragraph that cannot open a chunk on orthographic evidence alone:
    it starts with a footnote marker, or with a lower-case letter (a
    sentence broken across units). List items and enumerators (``ii.``,
    ``a)``) start lower-case by convention and are excluded."""
    if unit.type != UnitType.PARAGRAPH:
        return False
    text = strip_emphasis(unit.text)
    if _FOOTNOTE_START.match(text):
        return True
    text = text.lstrip(_OPENING_QUOTES)
    if not text:
        return False
    if _LIST_MARKER_START.match(text) or _ENUMERATOR_START.match(text):
        return False
    first = text[0]
    return first.isalpha() and first.islower()


# --------------------------------------------------------------------------
# partitions: chunk rows -> ordered blocks grouped by section
# --------------------------------------------------------------------------


SectionKey = tuple[str | None, tuple[tuple[str, ...], ...]]


@dataclass(frozen=True)
class Block:
    unit_ids: tuple[str, ...]  # raw ids: fragment-qualified where the row carries them
    token_count: int
    chunk_id: str


@dataclass
class SectionBlocks:
    key: SectionKey
    occurrence: int
    blocks: list[Block] = field(default_factory=list)

    @property
    def unit_ids(self) -> tuple[str, ...]:
        return tuple(unit_id for block in self.blocks for unit_id in block.unit_ids)

    @property
    def cuts(self) -> tuple[int, ...]:
        """Internal cut positions in the section's raw-id index space."""
        positions: list[int] = []
        offset = 0
        for block in self.blocks[:-1]:
            offset += len(block.unit_ids)
            positions.append(offset)
        return tuple(positions)

    def describe(self) -> dict[str, Any]:
        heading, paths = self.key
        return {
            "heading": heading,
            "section_paths": [list(path) for path in paths],
            "occurrence": self.occurrence,
        }


def _row_ids(row: Mapping[str, Any]) -> tuple[str, ...]:
    ids = row.get("fragment_unit_ids") or row.get("unit_ids") or []
    return tuple(str(unit_id) for unit_id in ids)


def _section_key(row: Mapping[str, Any]) -> SectionKey:
    paths = row.get("section_paths") or []
    return (
        row.get("heading"),
        tuple(tuple(str(part) for part in path) for path in paths),
    )


def partition_from_rows(
    rows: Sequence[Mapping[str, Any]], counter: TokenCounter | None = None
) -> list[SectionBlocks]:
    """Consecutive rows sharing ``(heading, section_paths)`` form one section.

    Rows that omit ``token_count`` are counted with ``counter`` from their
    text; a row with neither is refused rather than guessed.
    """
    sections: list[SectionBlocks] = []
    occurrences: dict[SectionKey, int] = {}
    for row in rows:
        key = _section_key(row)
        if "token_count" in row:
            tokens = int(row["token_count"])
        elif counter is not None and "text" in row:
            tokens = counter.count(str(row["text"]))
        else:
            raise ValueError(
                f"chunk {row.get('chunk_id')!r} carries neither token_count nor text"
            )
        block = Block(_row_ids(row), tokens, str(row.get("chunk_id", "")))
        if not block.unit_ids:
            raise ValueError(f"chunk {block.chunk_id!r} has no unit ids")
        if sections and sections[-1].key == key:
            sections[-1].blocks.append(block)
            continue
        occurrence = occurrences.get(key, 0)
        occurrences[key] = occurrence + 1
        sections.append(SectionBlocks(key=key, occurrence=occurrence, blocks=[block]))
    return sections


# --------------------------------------------------------------------------
# smells
# --------------------------------------------------------------------------


def boundary_smells(
    left: RawDocumentUnit,
    right: RawDocumentUnit,
    *,
    left_raw_id: str,
    right_raw_id: str,
    config: QualityConfig = QualityConfig(),
) -> list[str]:
    """Smells of one internal cut between ``left`` (tail) and ``right`` (head)."""
    if base_unit_id(left_raw_id) == base_unit_id(right_raw_id):
        return ["table_split" if left.type == UnitType.TABLE else "fragment_cut"]
    smells: list[str] = []
    if is_label_like(left, max_words=config.max_label_words):
        smells.append("orphan_label")
    if is_lead_in(left):
        smells.append("lead_in_cut")
    if continues_previous(right):
        smells.append("continuation_cut")
    return smells


def list_runs(units: Sequence[RawDocumentUnit]) -> list[tuple[str, ...]]:
    """Maximal runs of adjacent ``list`` units sharing one ``section_path``."""
    runs: list[tuple[str, ...]] = []
    current: list[str] = []
    current_path: tuple[str, ...] | None = None
    for unit in units:
        path = tuple(unit.section_path or ())
        if unit.type == UnitType.LIST and (not current or path == current_path):
            current.append(unit.unit_id)
            current_path = path
            continue
        if len(current) >= 2:
            runs.append(tuple(current))
        current = [unit.unit_id] if unit.type == UnitType.LIST else []
        current_path = path if unit.type == UnitType.LIST else None
    if len(current) >= 2:
        runs.append(tuple(current))
    return runs


def _empty_vector() -> dict[str, int]:
    return {key: 0 for key in VECTOR_KEYS}


@dataclass
class SectionQuality:
    section: SectionBlocks
    vector: dict[str, int]
    boundaries: list[dict[str, Any]]
    split_runs: list[tuple[str, ...]]

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.section.describe(),
            "block_count": len(self.section.blocks),
            "vector": dict(self.vector),
            "boundaries": list(self.boundaries),
            "split_runs_when_fit": [list(run) for run in self.split_runs],
        }


def section_quality(
    section: SectionBlocks,
    units_by_id: Mapping[str, RawDocumentUnit],
    *,
    runs: Sequence[tuple[str, ...]],
    counter: TokenCounter,
    config: QualityConfig,
) -> SectionQuality:
    vector = _empty_vector()
    boundaries: list[dict[str, Any]] = []
    for left_block, right_block in zip(section.blocks, section.blocks[1:]):
        left_raw, right_raw = left_block.unit_ids[-1], right_block.unit_ids[0]
        left = units_by_id.get(base_unit_id(left_raw))
        right = units_by_id.get(base_unit_id(right_raw))
        if left is None or right is None:
            raise KeyError(
                f"chunk boundary {left_raw} | {right_raw} names a unit outside the corpus"
            )
        smells = boundary_smells(
            left, right, left_raw_id=left_raw, right_raw_id=right_raw, config=config
        )
        for smell in smells:
            vector[smell] += 1
        boundaries.append(
            {"cut_after_unit_id": left_raw, "cut_before_unit_id": right_raw, "smells": smells}
        )
    for block in section.blocks:
        if block.token_count < config.min_tokens:
            vector["below_min"] += 1
        if block.token_count > config.soft_max_tokens:
            vector["above_soft_max"] += 1

    # A list run split across blocks while the whole run would fit one block.
    block_of: dict[str, int] = {}
    for index, block in enumerate(section.blocks):
        for raw_id in block.unit_ids:
            block_of.setdefault(base_unit_id(raw_id), index)
    split_runs: list[tuple[str, ...]] = []
    for run in runs:
        if run[0] not in block_of:
            continue
        indices = {block_of[unit_id] for unit_id in run if unit_id in block_of}
        if len(indices) < 2:
            continue
        run_text = "\n".join(units_by_id[unit_id].text for unit_id in run)
        if counter.count(run_text) <= config.target_tokens:
            vector["run_split_when_fits"] += 1
            split_runs.append(run)
    return SectionQuality(section, vector, boundaries, split_runs)


# --------------------------------------------------------------------------
# the comparison rule and the change groups
# --------------------------------------------------------------------------


def compare_vectors(standard: Mapping[str, int], deep: Mapping[str, int]) -> str:
    """``worse`` if any type grew; ``tie`` if all equal; else ``better``."""
    if any(deep.get(key, 0) > standard.get(key, 0) for key in VECTOR_KEYS):
        return VERDICT_WORSE
    if all(deep.get(key, 0) == standard.get(key, 0) for key in VECTOR_KEYS):
        return VERDICT_TIE
    return VERDICT_BETTER


def compare_smells(standard: Mapping[str, int], deep: Mapping[str, int]) -> str:
    """The same rule restricted to the six *defect* types.

    ``below_min`` and ``above_soft_max`` describe the size *distribution*, not
    a boundary defect: a 943-token block under a 1126-token hard cap is not a
    regression in the sense a reader would recognise, while an orphaned label
    is. Keeping the two apart is what lets a selector pay a soft-size counter
    to remove a real defect -- a trade this module reports rather than hides
    (see :func:`compare_tiered`).
    """
    if any(deep.get(key, 0) > standard.get(key, 0) for key in SMELL_TYPES):
        return VERDICT_WORSE
    if all(deep.get(key, 0) == standard.get(key, 0) for key in SMELL_TYPES):
        return VERDICT_TIE
    return VERDICT_BETTER


def compare_tiered(
    standard: Mapping[str, int], deep: Mapping[str, int]
) -> tuple[str, bool]:
    """``(verdict, size_traded)`` under the two-tier contract.

    Tier 1 -- no smell type may grow, ever. Tier 2 -- a size counter may grow
    only as the price of a strictly smaller smell total. ``size_traded`` says
    a soft size counter was paid, so a report can show what the improvement
    cost. A partition that grows a size counter without removing a smell is
    ``worse``, exactly as under :func:`compare_vectors`.
    """
    verdict = compare_smells(standard, deep)
    if verdict == VERDICT_WORSE:
        return VERDICT_WORSE, False
    grew = any(deep.get(key, 0) > standard.get(key, 0) for key in SIZE_COUNTERS)
    if not grew:
        return compare_vectors(standard, deep), False
    smells_s = sum(standard.get(key, 0) for key in SMELL_TYPES)
    smells_d = sum(deep.get(key, 0) for key in SMELL_TYPES)
    if smells_d < smells_s:
        return VERDICT_BETTER, True
    return VERDICT_WORSE, False


def change_groups(standard: SectionBlocks, deep: SectionBlocks) -> list[dict[str, Any]]:
    """Maximal spans between cuts common to both partitions where they differ.

    A verifier accepts or reverts a whole group, never a single cut: a cut
    accepted from one partition next to a cut kept from the other yields a
    block neither partition contained.
    """
    if standard.unit_ids != deep.unit_ids:
        raise ValueError(
            "partitions cover different unit sequences in section "
            f"{standard.describe()}"
        )
    ids = standard.unit_ids
    cuts_s, cuts_d = set(standard.cuts), set(deep.cuts)
    common = sorted((cuts_s & cuts_d) | {0, len(ids)})
    groups: list[dict[str, Any]] = []
    for start, end in zip(common, common[1:]):
        inside_s = sorted(cut for cut in cuts_s if start < cut < end)
        inside_d = sorted(cut for cut in cuts_d if start < cut < end)
        if inside_s == inside_d:
            continue
        groups.append(
            {
                "start_index": start,
                "end_index": end,
                "unit_ids": list(ids[start:end]),
                "standard_cuts_after": [ids[cut - 1] for cut in inside_s],
                "deep_cuts_after": [ids[cut - 1] for cut in inside_d],
            }
        )
    return groups


def measure(
    units: Sequence[RawDocumentUnit],
    rows: Sequence[Mapping[str, Any]],
    *,
    counter: TokenCounter,
    config: QualityConfig = QualityConfig(),
) -> dict[str, Any]:
    """Smell vectors of every section of one partition, plus totals."""
    units_by_id = {unit.unit_id: unit for unit in units}
    runs = list_runs(units)
    sections = partition_from_rows(rows, counter)
    qualities = [
        section_quality(section, units_by_id, runs=runs, counter=counter, config=config)
        for section in sections
    ]
    totals = _empty_vector()
    for quality in qualities:
        for key, value in quality.vector.items():
            totals[key] += value
    return {
        "config": {**config.__dict__},
        "section_count": len(sections),
        "block_count": sum(len(section.blocks) for section in sections),
        "internal_boundary_count": sum(len(section.blocks) - 1 for section in sections),
        "totals": totals,
        "sections": [quality.as_dict() for quality in qualities],
    }


def compare(
    units: Sequence[RawDocumentUnit],
    standard_rows: Sequence[Mapping[str, Any]],
    deep_rows: Sequence[Mapping[str, Any]],
    *,
    counter: TokenCounter,
    config: QualityConfig = QualityConfig(),
) -> dict[str, Any]:
    """Section-by-section verdicts of ``deep`` against ``standard``.

    Both partitions must walk the same section sequence with the same raw
    unit ids; anything else is refused rather than aligned heuristically.
    """
    units_by_id = {unit.unit_id: unit for unit in units}
    runs = list_runs(units)
    standard_sections = partition_from_rows(standard_rows, counter)
    deep_sections = partition_from_rows(deep_rows, counter)
    if [s.key for s in standard_sections] != [d.key for d in deep_sections]:
        raise ValueError("the two partitions do not walk the same section sequence")

    sections: list[dict[str, Any]] = []
    verdicts = {VERDICT_BETTER: 0, VERDICT_TIE: 0, VERDICT_WORSE: 0}
    verdicts_tiered = {VERDICT_BETTER: 0, VERDICT_TIE: 0, VERDICT_WORSE: 0}
    size_trades = 0
    totals_standard, totals_deep = _empty_vector(), _empty_vector()
    regressions: list[dict[str, Any]] = []
    group_count = 0
    for index, (standard, deep) in enumerate(zip(standard_sections, deep_sections)):
        quality_s = section_quality(
            standard, units_by_id, runs=runs, counter=counter, config=config
        )
        quality_d = section_quality(
            deep, units_by_id, runs=runs, counter=counter, config=config
        )
        verdict = compare_vectors(quality_s.vector, quality_d.vector)
        tiered, size_traded = compare_tiered(quality_s.vector, quality_d.vector)
        groups = change_groups(standard, deep)
        verdicts[verdict] += 1
        verdicts_tiered[tiered] += 1
        size_trades += int(size_traded)
        group_count += len(groups)
        for key in VECTOR_KEYS:
            totals_standard[key] += quality_s.vector[key]
            totals_deep[key] += quality_d.vector[key]
        entry = {
            **standard.describe(),
            "section_index": index,
            "verdict": verdict,
            "verdict_tiered": tiered,
            "size_traded": size_traded,
            "standard": {"vector": quality_s.vector, "block_count": len(standard.blocks)},
            "deep": {"vector": quality_d.vector, "block_count": len(deep.blocks)},
            "change_groups": groups,
        }
        if tiered == VERDICT_WORSE:
            regressions.append(entry)
        if groups or verdict != VERDICT_TIE:
            sections.append(entry)
    return {
        "config": {**config.__dict__},
        "section_count": len(standard_sections),
        "verdicts": verdicts,
        "verdicts_tiered": verdicts_tiered,
        "structural_regression_count": verdicts_tiered[VERDICT_WORSE],
        "strict_regression_count": verdicts[VERDICT_WORSE],
        "size_trade_count": size_trades,
        "change_group_count": group_count,
        "totals": {"standard": totals_standard, "deep": totals_deep},
        "regressions": regressions,
        "sections_with_differences": sections,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")


def refuse_frozen_output(output: Path) -> None:
    for part in output.resolve().parts:
        if part == "evaluation":
            raise ValueError("refusing to write into evaluation/ -- frozen results live there")


def main(argv: Sequence[str] | None = None) -> None:
    from .io import load_jsonl_units
    from .tokenization import TiktokenTokenCounter

    parser = argparse.ArgumentParser(
        description="Deterministic boundary smells of a structure-first chunk "
        "partition, optionally compared against a Standard partition"
    )
    parser.add_argument("--units", required=True, type=Path)
    parser.add_argument("--chunks", required=True, type=Path, help="the partition to measure")
    parser.add_argument("--against", type=Path, default=None, help="the Standard partition")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--encoding", default="cl100k_base")
    parser.add_argument("--min-tokens", type=int, default=QualityConfig.min_tokens)
    parser.add_argument("--target-tokens", type=int, default=QualityConfig.target_tokens)
    parser.add_argument("--soft-max-tokens", type=int, default=QualityConfig.soft_max_tokens)
    parser.add_argument("--hard-max-tokens", type=int, default=QualityConfig.hard_max_tokens)
    args = parser.parse_args(argv)

    refuse_frozen_output(args.output)
    config = QualityConfig(
        min_tokens=args.min_tokens,
        target_tokens=args.target_tokens,
        soft_max_tokens=args.soft_max_tokens,
        hard_max_tokens=args.hard_max_tokens,
    )
    units = load_jsonl_units(args.units)
    counter = TiktokenTokenCounter(args.encoding)
    rows = load_rows(args.chunks)
    report: dict[str, Any] = {"measure": measure(units, rows, counter=counter, config=config)}
    if args.against is not None:
        standard_rows = load_rows(args.against)
        report["compare"] = compare(units, standard_rows, rows, counter=counter, config=config)
    write_json(args.output, report)
    summary: dict[str, Any] = {
        "totals": report["measure"]["totals"],
        "internal_boundary_count": report["measure"]["internal_boundary_count"],
    }
    if "compare" in report:
        summary["verdicts"] = report["compare"]["verdicts"]
        summary["change_group_count"] = report["compare"]["change_group_count"]
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
