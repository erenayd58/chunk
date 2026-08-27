"""Structural quality of a chunk corpus, measured without knowing the chunker.

Every number here is derived from the canonical units, the chunk rows and the
:mod:`amsc.chunk_mapping` result -- never from a field only one chunker writes.
That is the whole point: a size-first splitter, a structure-first chunker and a
semantically arbitrated one have to be scored by the same ruler, and a metric
that reads ``end_boundary.reason`` or ``split_strategies`` would silently score
0 for the arms that do not emit it.

Two cautions the report has to carry, both measured rather than assumed:

* **Most of what** :func:`amsc.structural_qa.lint` **finds is a property of the
  parser, not the chunker.** Its unit-level rules read the canonical stream
  alone and return the same findings whatever the chunks are. So the baseline is
  computed once as ``lint(units, [])`` and subtracted; only the remainder can
  distinguish arms, and only the remainder is compared.
* **The remainder is schema-sensitive.** ``section_inconsistency``'s chunk rule
  is literally ``len(section_paths) > 1``, so an arm that omits the key scores
  zero for free rather than on merit. :func:`schema_health` counts which keys
  each corpus actually carries so a zero can be read correctly.

``duplicate_token_mass_ratio`` is the sum of chunk token counts over the sum of
unit token counts. Above 1.0 means content is stored more than once -- a
splitter's overlap, or a heading repeated by every part of a split section. It
is a property of the method, not a defect.
"""

from __future__ import annotations

from collections import Counter
import re
from typing import Any, Iterable, Mapping, Sequence

from .chunk_mapping import DocumentMapping, Segment
from .evaluation import _median, _nearest_rank
from .models import RawDocumentUnit, UnitType
from .structural_qa import Finding, lint
from .tokenization import TokenCounter

#: Sentence-final punctuation, used only to judge a cut inside a paragraph.
_SENTENCE_END = (".", "!", "?", "…")

#: Keys a chunk row must carry for the schema-sensitive rules to mean anything.
SCHEMA_KEYS = ("heading", "section_paths", "pages", "token_count", "unit_ids")


def _tokens(chunk: Mapping[str, Any], counter: TokenCounter) -> int:
    value = chunk.get("token_count")
    if isinstance(value, int):
        return value
    return counter.count(str(chunk.get("text") or ""))


def _cut_positions(segments: Sequence[Segment], length: int) -> list[int]:
    """Where a unit was cut, in the unit's own character offsets.

    Segment starts above zero and ends below the unit's length are cuts; the
    ends of a repeated header run coincide with the starts of the body run and
    collapse to the same position, so the set is taken.
    """
    positions = {segment.unit_start for segment in segments if segment.unit_start > 0}
    positions |= {segment.unit_end for segment in segments if segment.unit_end < length}
    return sorted(positions)


def split_defects(
    units: Sequence[RawDocumentUnit], mapping: DocumentMapping
) -> dict[str, Any]:
    """Cuts that landed inside a word, and inside a sentence.

    ``mid_sentence`` is judged for paragraphs only. A table is cut between rows
    and a list between items, and neither line ends in a full stop, so applying
    the sentence test to them would report every well-placed structural cut as a
    defect.
    """
    by_unit = mapping.segments_by_unit()
    units_by_id = {unit.unit_id: unit for unit in units}
    mid_word: list[dict[str, Any]] = []
    mid_sentence: list[dict[str, Any]] = []

    for unit_id, entries in sorted(by_unit.items()):
        unit = units_by_id.get(unit_id)
        if unit is None:
            continue
        text = unit.text
        for position in _cut_positions([segment for _, segment in entries], len(text)):
            if 0 < position < len(text) and text[position - 1].isalnum() and text[position].isalnum():
                mid_word.append(
                    {
                        "unit_id": unit_id,
                        "position": position,
                        "left": text[max(0, position - 24) : position],
                        "right": text[position : position + 24],
                    }
                )
            if unit.type != UnitType.PARAGRAPH:
                continue
            left = text[:position].rstrip()
            if left and not left.endswith(_SENTENCE_END):
                mid_sentence.append(
                    {"unit_id": unit_id, "position": position, "left": left[-40:]}
                )

    return {
        "mid_word_split_count": len(mid_word),
        "mid_sentence_split_count": len(mid_sentence),
        "mid_word_examples": mid_word[:10],
        "mid_sentence_examples": mid_sentence[:10],
    }


def _section_runs(units: Sequence[RawDocumentUnit]) -> list[tuple[int, tuple[str, ...], list[str]]]:
    """Maximal runs of consecutive units sharing one section path."""
    runs: list[tuple[int, tuple[str, ...], list[str]]] = []
    for unit in units:
        path = tuple(unit.section_path or ())
        if runs and runs[-1][1] == path:
            runs[-1][2].append(unit.unit_id)
            continue
        runs.append((len(runs), path, [unit.unit_id]))
    return runs


def schema_health(chunks: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """How many chunk rows actually carry each schema key.

    A rule that reads a missing key does not fail -- it scores perfectly. This
    is what makes that visible.
    """
    present: Counter[str] = Counter()
    for chunk in chunks:
        for key in SCHEMA_KEYS:
            if chunk.get(key) is not None:
                present[key] += 1
    return {key: present[key] for key in SCHEMA_KEYS}


_ATX_MARKER = re.compile(r"^#{1,6} ", flags=re.MULTILINE)


def qa_view(chunks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The chunk rows as the linter should see them, one shape for every arm.

    ``structural_qa`` predates markdown rendering: ``strip_emphasis`` removes
    ``*`` and ``_`` but not ``#``, so a line reading ``## FINDEKS`` is classified
    as a title whose normalised text is ``## findeks``, which then matches
    neither the chunk's heading nor any section path -- a mismatch reported
    against an arm for writing valid markdown.

    Removing the ATX marker from ``heading`` and from the start of every line of
    ``text`` is symmetric (it is a no-op for arms that emit none) and preserves
    the literal-prefix relation ``check_chunk_headings`` relies on. The stored
    chunk text is untouched; this view exists only for linting.
    """
    view: list[dict[str, Any]] = []
    for chunk in chunks:
        row = dict(chunk)
        row["text"] = _ATX_MARKER.sub("", str(chunk.get("text") or ""))
        heading = chunk.get("heading")
        if heading:
            row["heading"] = _ATX_MARKER.sub("", str(heading))
        view.append(row)
    return view


def parser_baseline(units: Sequence[RawDocumentUnit]) -> list[Finding]:
    """Findings that depend on the canonical stream alone, chunks aside."""
    return list(lint(_as_rows(units), []).findings)


def _as_rows(units: Sequence[RawDocumentUnit]) -> list[dict[str, Any]]:
    return [unit.model_dump(mode="json") for unit in units]


def _finding_counts(findings: Iterable[Finding]) -> dict[str, dict[str, int]]:
    grouped: dict[str, Counter[str]] = {}
    for finding in findings:
        grouped.setdefault(finding.rule, Counter())[finding.confidence] += 1
    return {
        rule: {level: counts[level] for level in ("HIGH", "MEDIUM", "LOW")}
        for rule, counts in sorted(grouped.items())
    }


def measure(
    units: Sequence[RawDocumentUnit],
    chunks: Sequence[Mapping[str, Any]],
    mapping: DocumentMapping,
    *,
    counter: TokenCounter,
    min_tokens: int = 160,
    soft_max_tokens: int = 900,
    hard_max_tokens: int = 1126,
    baseline: Sequence[Finding] | None = None,
) -> dict[str, Any]:
    """Score one chunk corpus. ``baseline`` is reused across arms when supplied."""
    units_by_id = {unit.unit_id: unit for unit in units}
    token_counts = sorted(_tokens(chunk, counter) for chunk in chunks)
    total = len(chunks)

    def ratio(count: int) -> float:
        return round(count / total, 6) if total else 0.0

    multi_section = 0
    multi_heading_path = 0
    heading_led = 0
    without_heading = 0
    furniture = 0
    for chunk, row in zip(mapping.chunks, chunks):
        # Section membership is read from content units only. A heading's own
        # ``section_path`` names the section it *opens*, so a chunk that carries
        # two accumulated headings ("1. KKB HAKKINDA" above "Finans sektörünün
        # öncü kuruluşu") would otherwise be reported as spanning two sections
        # when every line of its content belongs to one. Measured on the frozen
        # corpus: all 136 such chunks differ on heading paths alone, none on
        # content paths.
        paths: list[tuple[str, ...]] = []
        heading_paths: list[tuple[str, ...]] = []
        heading_ids: list[str] = []
        for segment in chunk.segments:
            unit = units_by_id.get(segment.unit_id)
            if unit is None:
                continue
            path = tuple(unit.section_path or ())
            if unit.type == UnitType.HEADING:
                heading_ids.append(unit.unit_id)
                if path and path not in heading_paths:
                    heading_paths.append(path)
            elif path and path not in paths:
                paths.append(path)
        if len(paths) > 1:
            multi_section += 1
        if len(heading_paths) > 1:
            multi_heading_path += 1
        if not heading_ids:
            without_heading += 1
        elif chunk.segments and units_by_id[chunk.segments[0].unit_id].type == UnitType.HEADING:
            heading_led += 1
        content = [
            segment
            for segment in chunk.segments
            if units_by_id.get(segment.unit_id)
            and units_by_id[segment.unit_id].type != UnitType.HEADING
        ]
        if heading_ids and not content and _tokens(row, counter) < min_tokens:
            furniture += 1

    by_unit = mapping.segments_by_unit()
    in_many_all = {
        unit_id
        for unit_id, entries in by_unit.items()
        if len({chunk_id for chunk_id, _ in entries}) > 1
    }
    # A heading appearing in several chunks is a split section repeating its own
    # title, which is intended; a content unit appearing in several chunks is
    # fragmentation. Counting them together would read as duplication.
    in_many = {
        unit_id
        for unit_id in in_many_all
        if units_by_id.get(unit_id) and units_by_id[unit_id].type != UnitType.HEADING
    }
    repeated_headings = len(in_many_all) - len(in_many)
    fragmented = {
        unit_type: sum(
            1
            for unit_id in in_many
            if units_by_id.get(unit_id) and units_by_id[unit_id].type == unit_type
        )
        for unit_type in (UnitType.TABLE, UnitType.LIST, UnitType.PARAGRAPH)
    }

    chunk_ids_by_run = []
    for _, _, member_ids in _section_runs(units):
        touched = {
            chunk_id
            for unit_id in member_ids
            for chunk_id, _ in by_unit.get(unit_id, ())
        }
        chunk_ids_by_run.append(len(touched))
    split_runs = sum(1 for count in chunk_ids_by_run if count > 1)

    unit_tokens = sum(counter.count(unit.text) for unit in units)
    chunk_tokens = sum(token_counts)
    text_counts = Counter(str(chunk.get("text") or "") for chunk in chunks)
    duplicate_texts = sum(count for count in text_counts.values() if count > 1)

    baseline_findings = list(baseline) if baseline is not None else parser_baseline(units)
    full = lint(_as_rows(units), qa_view(chunks))
    baseline_set = set(baseline_findings)
    chunk_derived = [finding for finding in full.findings if finding not in baseline_set]

    content_units = [unit for unit in units if unit.type != UnitType.HEADING]
    mapped_ids = set(by_unit)
    unmapped_content = [
        unit.unit_id for unit in content_units if unit.unit_id not in mapped_ids
    ]

    return {
        "chunk_count": total,
        "token_count": {
            "min": token_counts[0] if token_counts else None,
            "median": _median(token_counts),
            "p90_nearest_rank": _nearest_rank(token_counts, 0.90),
            "max": token_counts[-1] if token_counts else None,
            "sum": chunk_tokens,
        },
        "size_bands": {
            "below_min_count": sum(count < min_tokens for count in token_counts),
            "below_min_ratio": ratio(sum(count < min_tokens for count in token_counts)),
            "above_soft_max_count": sum(count > soft_max_tokens for count in token_counts),
            "above_soft_max_ratio": ratio(
                sum(count > soft_max_tokens for count in token_counts)
            ),
            "at_hard_cap_count": sum(count == hard_max_tokens for count in token_counts),
            "over_hard_cap_count": sum(count > hard_max_tokens for count in token_counts),
        },
        "structure": {
            "multi_section_count": multi_section,
            "multi_section_ratio": ratio(multi_section),
            "multi_heading_path_count": multi_heading_path,
            "heading_led_count": heading_led,
            "heading_led_ratio": ratio(heading_led),
            "without_heading_count": without_heading,
            "furniture_chunk_count": furniture,
            "section_run_split_count": split_runs,
            "section_run_count": len(chunk_ids_by_run),
        },
        "fragmentation": {
            "content_units_in_multiple_chunks": len(in_many),
            "headings_repeated_across_chunks": repeated_headings,
            "table_units_fragmented": fragmented[UnitType.TABLE],
            "list_units_fragmented": fragmented[UnitType.LIST],
            "paragraph_units_fragmented": fragmented[UnitType.PARAGRAPH],
            **split_defects(units, mapping),
        },
        "duplication": {
            "duplicate_token_mass_ratio": (
                round(chunk_tokens / unit_tokens, 6) if unit_tokens else 0.0
            ),
            "duplicate_chunk_text_count": duplicate_texts,
            "distinct_chunk_text_count": len(text_counts),
        },
        "coverage": {
            "canonical_unit_count": len(units),
            "content_unit_count": len(content_units),
            "content_units_never_mapped": len(unmapped_content),
            "content_unit_coverage": (
                round(
                    (len(content_units) - len(unmapped_content)) / len(content_units), 6
                )
                if content_units
                else 0.0
            ),
            "never_mapped_examples": sorted(unmapped_content)[:10],
        },
        "mapping_health": dict(sorted(mapping.health.items())),
        "schema_health": schema_health(chunks),
        "structural_qa": {
            "parser_baseline_finding_count": len(baseline_findings),
            "chunk_derived_finding_count": len(chunk_derived),
            "chunk_derived_per_chunk": (
                round(len(chunk_derived) / total, 6) if total else 0.0
            ),
            "chunk_derived_by_rule": _finding_counts(chunk_derived),
        },
    }
