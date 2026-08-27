"""Map a chunk back to the canonical units it was built from.

Three chunkers with three different provenance conventions have to be compared
on one set of structural metrics and drawn on one parsed page, so the question
"which part of which unit is this chunk showing?" needs a single answer that
does not depend on which chunker produced the chunk.

The ladder below is ordered by how much it assumes, strongest first. A rung is
only tried when the one above it fails, and the rung that succeeded is recorded
on every segment, so a metric or a highlight can always be traced to the
evidence that produced it:

``offset``
    The chunk carries its own character range in a rendered document and the
    caller supplied each unit's range in the same document. The intersection is
    arithmetic -- no searching, no ambiguity.
``provenance``
    The chunk declares ``unit_ids`` and the unit's text is found verbatim in the
    chunk text, scanning forward from the previous match so repeated text maps
    to the occurrence that reading order implies.
``normalized_exact``
    Same, but comparing whitespace-normalised text; offsets are carried back to
    the raw string through an index table.
``sequential``
    The unit was split, so only part of it is here. Whole lines are matched
    first (a table fragment repeats its header row, so its content is not one
    contiguous slice of the unit); failing that, the longest prefix and the
    longest suffix of the unit that occur in the chunk are located. This is what
    makes a mid-word split visible.

Anything that survives all four is reported as ``unmapped`` and stays that way.
Guessing would put a colour on the wrong paragraph and quietly inflate every
structural metric derived from the mapping, which is worse than a gap the
viewer draws in grey and the report counts.

Nothing here is fuzzy: every rung is exact string equality over some
deterministic normalisation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

from .models import RawDocumentUnit, UnitType

MAP_OFFSET = "offset"
MAP_PROVENANCE = "provenance"
MAP_NORMALIZED = "normalized_exact"
MAP_SEQUENTIAL = "sequential"
UNMAPPED = "unmapped"

#: Rungs in the order they are attempted; also the order used in reports.
METHODS = (MAP_OFFSET, MAP_PROVENANCE, MAP_NORMALIZED, MAP_SEQUENTIAL)

#: A ``sequential`` match covering less than this share of the unit is still a
#: match, but a weak one, and is counted separately so a report can tell "the
#: unit was split" from "we found a few common lines and little else".
PARTIAL_LOW_COVERAGE = 0.9

_FRAGMENT_SUFFIX = re.compile(r"#f\d+$")


def base_unit_id(unit_id: str) -> str:
    """``t-00186#f2`` -> ``t-00186``; anything else is returned unchanged."""
    return _FRAGMENT_SUFFIX.sub("", str(unit_id))


@dataclass(frozen=True)
class Segment:
    """One contiguous piece of one unit, located inside one chunk."""

    unit_id: str
    unit_start: int
    unit_end: int
    chunk_start: int
    chunk_end: int
    method: str

    @property
    def length(self) -> int:
        return self.unit_end - self.unit_start

    def as_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "unit_start": self.unit_start,
            "unit_end": self.unit_end,
            "chunk_start": self.chunk_start,
            "chunk_end": self.chunk_end,
            "method": self.method,
        }


@dataclass(frozen=True)
class ChunkMapping:
    chunk_id: str
    segments: tuple[Segment, ...]
    unmapped_unit_ids: tuple[str, ...]
    #: unit_id -> share of the unit's characters this chunk carries.
    coverage: Mapping[str, float]

    def unit_ids(self) -> tuple[str, ...]:
        seen: list[str] = []
        for segment in self.segments:
            if segment.unit_id not in seen:
                seen.append(segment.unit_id)
        return tuple(seen)

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "segments": [segment.as_dict() for segment in self.segments],
            "unmapped_unit_ids": list(self.unmapped_unit_ids),
            "coverage": {
                key: round(value, 6) for key, value in sorted(self.coverage.items())
            },
        }


@dataclass(frozen=True)
class DocumentMapping:
    chunks: tuple[ChunkMapping, ...]
    health: Mapping[str, int]

    def segments_by_unit(self) -> dict[str, list[tuple[str, Segment]]]:
        """unit_id -> [(chunk_id, segment)], in chunk order."""
        grouped: dict[str, list[tuple[str, Segment]]] = {}
        for chunk in self.chunks:
            for segment in chunk.segments:
                grouped.setdefault(segment.unit_id, []).append(
                    (chunk.chunk_id, segment)
                )
        return grouped

    def as_dict(self) -> dict[str, Any]:
        return {
            "health": dict(sorted(self.health.items())),
            "chunks": [chunk.as_dict() for chunk in self.chunks],
        }


# ---------------------------------------------------------------------------
# rung 0 -- arithmetic
# ---------------------------------------------------------------------------


def _offset_segments(
    row: Mapping[str, Any],
    units: Sequence[RawDocumentUnit],
    unit_spans: Mapping[str, tuple[int, int]],
) -> list[Segment] | None:
    start, end = row.get("char_start"), row.get("char_end")
    if not isinstance(start, int) or not isinstance(end, int) or end <= start:
        return None
    segments: list[Segment] = []
    for unit in units:
        span = unit_spans.get(unit.unit_id)
        if span is None:
            continue
        unit_start, unit_end = span
        overlap_start = max(unit_start, start)
        overlap_end = min(unit_end, end)
        if overlap_end <= overlap_start:
            continue
        segments.append(
            Segment(
                unit_id=unit.unit_id,
                unit_start=overlap_start - unit_start,
                unit_end=overlap_end - unit_start,
                chunk_start=overlap_start - start,
                chunk_end=overlap_end - start,
                method=MAP_OFFSET,
            )
        )
    return segments or None


# ---------------------------------------------------------------------------
# rung 1/2 -- verbatim and whitespace-normalised search
# ---------------------------------------------------------------------------


def _normalize(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace, keeping a map from normalised index to raw index."""
    out: list[str] = []
    index: list[int] = []
    previous_space = True
    for position, character in enumerate(text):
        if character.isspace():
            if previous_space:
                continue
            out.append(" ")
            index.append(position)
            previous_space = True
            continue
        out.append(character)
        index.append(position)
        previous_space = False
    while out and out[-1] == " ":
        out.pop()
        index.pop()
    index.append(len(text))
    return "".join(out), index


def _find_verbatim(chunk_text: str, unit_text: str, cursor: int) -> int:
    position = chunk_text.find(unit_text, cursor)
    return position if position >= 0 else chunk_text.find(unit_text)


def _find_normalized(
    chunk_text: str,
    chunk_norm: str,
    chunk_index: list[int],
    unit_text: str,
    cursor: int,
) -> tuple[int, int] | None:
    needle, _ = _normalize(unit_text)
    if not needle:
        return None
    normalized_cursor = len(chunk_norm)
    for normalized_position, raw_position in enumerate(chunk_index[:-1]):
        if raw_position >= cursor:
            normalized_cursor = normalized_position
            break
    position = chunk_norm.find(needle, normalized_cursor)
    if position < 0:
        position = chunk_norm.find(needle)
    if position < 0:
        return None
    return chunk_index[position], chunk_index[position + len(needle)]


# ---------------------------------------------------------------------------
# rung 3 -- the unit was split; find the parts that are here
# ---------------------------------------------------------------------------


def _line_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    position = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            offset = line.index(stripped)
            spans.append((position + offset, position + offset + len(stripped)))
        position += len(line) + 1
    return spans


def _sequential_by_lines(
    chunk_text: str, unit_text: str
) -> list[tuple[int, int, int, int]]:
    """Match whole lines of the unit inside the chunk, in order.

    Returns ``(unit_start, unit_end, chunk_start, chunk_end)`` runs, merging
    lines that are adjacent in both texts so a table fragment comes back as one
    header run plus one body run rather than one run per row.
    """
    matches: list[tuple[int, int, int, int]] = []
    cursor = 0
    for unit_start, unit_end in _line_spans(unit_text):
        line = unit_text[unit_start:unit_end]
        position = chunk_text.find(line, cursor)
        if position < 0:
            continue
        cursor = position + len(line)
        matches.append((unit_start, unit_end, position, position + len(line)))

    runs: list[tuple[int, int, int, int]] = []
    for match in matches:
        if runs:
            previous = runs[-1]
            gap_unit = unit_text[previous[1] : match[0]]
            gap_chunk = chunk_text[previous[3] : match[2]]
            if not gap_unit.strip() and not gap_chunk.strip():
                runs[-1] = (previous[0], match[1], previous[2], match[3])
                continue
        runs.append(match)
    return runs


def _longest_affix(
    chunk_text: str, unit_text: str, frontier: int
) -> tuple[int, int, int, int] | None:
    """Longest prefix or suffix of the unit that the chunk boundary cut.

    This is the mid-word split: one chunk ends with the unit's opening
    characters, the next begins with its closing ones. Both halves are required
    to be *adjacent to a boundary* -- the prefix must run to the end of the
    chunk, the suffix must start where the already-mapped content stopped --
    because a match that stops in the middle of the chunk stopped for the wrong
    reason: the characters differed, so nothing was cut here.
    """
    best: tuple[int, int, int, int] | None = None
    best_length = 0
    tail = len(chunk_text.rstrip())

    low, high = 1, len(unit_text)
    while low <= high:
        middle = (low + high) // 2
        position = chunk_text.find(unit_text[:middle], frontier)
        if position >= 0:
            if middle > best_length and position + middle >= tail:
                best_length = middle
                best = (0, middle, position, position + middle)
            low = middle + 1
        else:
            high = middle - 1

    low, high = 1, len(unit_text)
    while low <= high:
        middle = (low + high) // 2
        candidate = unit_text[len(unit_text) - middle :]
        position = chunk_text.find(candidate, frontier)
        if position >= 0:
            if middle > best_length and not chunk_text[frontier:position].strip():
                best_length = middle
                best = (
                    len(unit_text) - middle,
                    len(unit_text),
                    position,
                    position + middle,
                )
            low = middle + 1
        else:
            high = middle - 1

    return best


def _cut_by_a_boundary(
    chunk_text: str, runs: Sequence[tuple[int, int, int, int]], frontier: int
) -> bool:
    """Did the chunk boundary cause this partial match, or did the text differ?

    A unit is only partly present because a boundary cut it, so the part that is
    here has to sit against one: it either continues from where the previous
    unit stopped, or it runs to the end of the chunk. A match that begins and
    ends in open water matched by coincidence -- one shared table divider, one
    shared word -- and is not evidence that this chunk carries the unit.
    """
    if not runs:
        return False
    return (
        not chunk_text[frontier : runs[0][2]].strip()
        or runs[-1][3] >= len(chunk_text.rstrip())
    )


def _normalized_offset(index: Sequence[int], raw: int) -> int:
    for position, value in enumerate(index[:-1]):
        if value >= raw:
            return position
    return max(len(index) - 1, 0)


def _sequential_segments(
    chunk_text: str,
    unit: RawDocumentUnit,
    frontier: int,
    *,
    chunk_norm: str = "",
    chunk_index: Sequence[int] = (),
) -> list[Segment]:
    """Locate the part of a split unit this chunk carries.

    Whole lines first, which is what a table or list fragment preserves; then
    the longest boundary-adjacent affix, which is what a prose fragment leaves.

    The affix is retried against whitespace-normalised text because a fragment
    is not always a byte-exact slice of its unit: the structure-first splitter
    rejoins sentences with a single space, so a paragraph that contained a
    double space stops matching a few hundred characters in. Offsets are carried
    back through the index tables, so the segment still addresses the raw text.
    """
    runs = _sequential_by_lines(chunk_text, unit.text)
    if not _cut_by_a_boundary(chunk_text, runs, frontier):
        affix = _longest_affix(chunk_text, unit.text, frontier)
        runs = [affix] if affix is not None else []

    if not runs and chunk_norm:
        unit_norm, unit_index = _normalize(unit.text)
        affix = _longest_affix(
            chunk_norm, unit_norm, _normalized_offset(chunk_index, frontier)
        )
        if affix is not None:
            unit_start, unit_end, chunk_start, chunk_end = affix
            return [
                Segment(
                    unit_id=unit.unit_id,
                    unit_start=unit_index[unit_start],
                    unit_end=unit_index[unit_end],
                    chunk_start=chunk_index[chunk_start],
                    chunk_end=chunk_index[chunk_end],
                    method=MAP_SEQUENTIAL,
                )
            ]

    return [
        Segment(
            unit_id=unit.unit_id,
            unit_start=unit_start,
            unit_end=unit_end,
            chunk_start=chunk_start,
            chunk_end=chunk_end,
            method=MAP_SEQUENTIAL,
        )
        for unit_start, unit_end, chunk_start, chunk_end in runs
    ]


# ---------------------------------------------------------------------------
# headings
# ---------------------------------------------------------------------------


def _heading_runs(
    units: Sequence[RawDocumentUnit], separator: str
) -> list[tuple[str, tuple[str, ...], int]]:
    """Every suffix of every run of consecutive heading units.

    A chunker may render one heading or several accumulated ones, so each
    trailing sub-run is offered as a candidate; the caller matches on exact
    text.
    """
    runs: list[tuple[str, tuple[str, ...], int]] = []
    current: list[RawDocumentUnit] = []

    def flush() -> None:
        for start in range(len(current)):
            group = current[start:]
            runs.append(
                (
                    separator.join(item.text for item in group),
                    tuple(item.unit_id for item in group),
                    group[0].order,
                )
            )
        current.clear()

    for unit in units:
        if unit.type == UnitType.HEADING:
            current.append(unit)
        else:
            flush()
    flush()
    return runs


def _heading_segments(
    heading: str,
    chunk_text: str,
    first_content_order: int | None,
    runs: Sequence[tuple[str, tuple[str, ...], int]],
    units_by_id: Mapping[str, RawDocumentUnit],
    separator: str,
) -> tuple[list[Segment], bool]:
    """Attribute a chunk's rendered heading to the heading units it came from.

    A chunk that continues a split section repeats its section's heading, so the
    run is looked up by exact text across the document and the latest one at or
    before the chunk's first content unit wins. Exact equality only: an
    approximate heading match would reattribute a section.
    """
    if not heading or not chunk_text.startswith(heading):
        return [], bool(heading)

    limit = first_content_order if first_content_order is not None else 10**9
    candidates = [run for run in runs if run[0] == heading and run[2] <= limit]
    if not candidates:
        candidates = [run for run in runs if run[0] == heading]
    if not candidates:
        return [], True

    _, unit_ids, _ = max(candidates, key=lambda run: run[2])
    segments: list[Segment] = []
    cursor = 0
    for unit_id in unit_ids:
        text = units_by_id[unit_id].text
        position = chunk_text.find(text, cursor)
        if position < 0 or position + len(text) > len(heading):
            return segments, True
        segments.append(
            Segment(
                unit_id=unit_id,
                unit_start=0,
                unit_end=len(text),
                chunk_start=position,
                chunk_end=position + len(text),
                method=MAP_PROVENANCE,
            )
        )
        cursor = position + len(text) + len(separator)
    return segments, False


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------


def _declared_unit_ids(row: Mapping[str, Any]) -> list[str]:
    """Chunk-declared provenance, fragment ids preferred when both are present.

    ``fragment_unit_ids`` is written by the benchmark's retrieval
    normalisation, which reduces ``unit_ids`` to canonical ids so the frozen
    evaluator can read them. The fragment-qualified list is the richer one and
    is what the mapping wants back.
    """
    for key in ("fragment_unit_ids", "unit_ids", "content_unit_ids"):
        value = row.get(key)
        if isinstance(value, (list, tuple)) and value:
            return [str(item) for item in value]
    return []


def map_chunks(
    units: Sequence[RawDocumentUnit],
    chunks: Sequence[Mapping[str, Any]],
    *,
    unit_spans: Mapping[str, tuple[int, int]] | None = None,
    heading_separator: str = "\n\n",
) -> DocumentMapping:
    """Locate every chunk's content inside the canonical units.

    ``unit_spans`` maps each unit to its character range in a rendered document;
    supply it together with ``char_start``/``char_end`` on the chunk rows to get
    exact arithmetic mapping (the markdown arm records both by construction).
    """
    units_by_id = {unit.unit_id: unit for unit in units}
    runs = _heading_runs(units, heading_separator)
    spans = unit_spans or {}

    mapped: list[ChunkMapping] = []
    health: Counter[str] = Counter()

    for row in chunks:
        chunk_id = str(row.get("chunk_id") or "")
        chunk_text = str(row.get("text") or "")
        declared = _declared_unit_ids(row)
        wanted: list[RawDocumentUnit] = []
        unmapped: list[str] = []
        for unit_id in declared:
            unit = units_by_id.get(base_unit_id(unit_id))
            if unit is None:
                unmapped.append(unit_id)
                health[f"{UNMAPPED}:unknown_unit_id"] += 1
                continue
            if unit not in wanted:
                wanted.append(unit)

        segments: list[Segment] = []
        offset_segments = _offset_segments(row, units, spans) if spans else None
        if offset_segments is not None:
            segments = offset_segments
            health[MAP_OFFSET] += len(segments)
        else:
            heading = str(row.get("heading") or "")
            first_content_order = wanted[0].order if wanted else None
            heading_segments, heading_unmapped = _heading_segments(
                heading,
                chunk_text,
                first_content_order,
                runs,
                units_by_id,
                heading_separator,
            )
            segments.extend(heading_segments)
            health[MAP_PROVENANCE] += len(heading_segments)
            if heading_unmapped:
                unmapped.append(f"{chunk_id}:heading")
                health[f"{UNMAPPED}:heading"] += 1

            chunk_norm, chunk_index = _normalize(chunk_text)
            cursor = max((segment.chunk_end for segment in segments), default=0)
            for unit in wanted:
                position = _find_verbatim(chunk_text, unit.text, cursor)
                if position >= 0:
                    segments.append(
                        Segment(
                            unit_id=unit.unit_id,
                            unit_start=0,
                            unit_end=len(unit.text),
                            chunk_start=position,
                            chunk_end=position + len(unit.text),
                            method=MAP_PROVENANCE,
                        )
                    )
                    cursor = position + len(unit.text)
                    health[MAP_PROVENANCE] += 1
                    continue

                normalized = _find_normalized(
                    chunk_text, chunk_norm, chunk_index, unit.text, cursor
                )
                if normalized is not None:
                    start, end = normalized
                    segments.append(
                        Segment(
                            unit_id=unit.unit_id,
                            unit_start=0,
                            unit_end=len(unit.text),
                            chunk_start=start,
                            chunk_end=end,
                            method=MAP_NORMALIZED,
                        )
                    )
                    cursor = end
                    health[MAP_NORMALIZED] += 1
                    continue

                partial = _sequential_segments(
                    chunk_text,
                    unit,
                    cursor,
                    chunk_norm=chunk_norm,
                    chunk_index=chunk_index,
                )
                if partial:
                    segments.extend(partial)
                    cursor = max(segment.chunk_end for segment in partial)
                    health[MAP_SEQUENTIAL] += 1
                    continue

                unmapped.append(unit.unit_id)
                health[f"{UNMAPPED}:not_found"] += 1

        segments.sort(key=lambda segment: (segment.chunk_start, segment.unit_id))
        coverage: dict[str, float] = {}
        for segment in segments:
            unit = units_by_id.get(segment.unit_id)
            if unit is None or not unit.text:
                continue
            coverage[segment.unit_id] = coverage.get(segment.unit_id, 0.0) + (
                segment.length / len(unit.text)
            )
        for value in coverage.values():
            if value >= 1.0:
                health["coverage:whole"] += 1
            elif value >= PARTIAL_LOW_COVERAGE:
                health["coverage:partial"] += 1
            else:
                health["coverage:partial_low"] += 1

        mapped.append(
            ChunkMapping(
                chunk_id=chunk_id,
                segments=tuple(segments),
                unmapped_unit_ids=tuple(unmapped),
                coverage=coverage,
            )
        )

    health["chunks"] = len(mapped)
    health["units"] = len(units)
    referenced = {segment.unit_id for chunk in mapped for segment in chunk.segments}
    health["units_mapped"] = len(referenced)
    health["units_never_mapped"] = len(units_by_id) - len(referenced)
    return DocumentMapping(chunks=tuple(mapped), health=dict(health))
