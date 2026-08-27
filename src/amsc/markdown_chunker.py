"""Size-first recursive markdown chunker -- the baseline arm.

This is the splitter most RAG stacks actually ship: render the document to
markdown, then cut it into fixed-size pieces, preferring to cut at a markdown
separator but falling back to a blank line, a line, a word and finally a
character. It is *size*-first: a heading boundary is preferred, never
guaranteed, and a section is cut wherever the budget runs out.

It exists here to answer "does structure-aware chunking buy anything over the
ordinary thing?", so it deliberately does none of the structural work the
structure-first arm does: no table header repeated into continuation parts, no
sentence seam, no section awareness, no merging of undersized sections.

**The size numbers are not a claim about standard practice.** LangChain's own
default is character-based (1000/200) and its ``MarkdownTextSplitter`` carries
its heading separators as literal strings. ``CHUNK_SIZE_TOKENS`` is set to the
other arms' ``target_tokens`` so that the token budget is identical across the
benchmark and only the *rule* differs; the overlap is 20% of it. Both are frozen
benchmark configuration, marked ``poc_initial_not_optimized``, not a
reproduction of anyone's default.

Rendering records each unit's character range in the rendered document, so a
chunk's provenance is arithmetic rather than a text search: see
:func:`amsc.chunk_mapping.map_chunks`'s ``offset`` rung. The ``## `` markers this
module adds belong to no unit and are deliberately left outside every span --
they are rendering, not content.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .models import RawDocumentUnit, UnitType
from .tokenization import TokenCounter

RENDER_SEPARATOR = "\n\n"

#: Frozen benchmark configuration; see the module docstring.
CHUNK_SIZE_TOKENS = 700
CHUNK_OVERLAP_TOKENS = 140
TUNING_STATUS = "poc_initial_not_optimized"

#: Preference order. Each entry is (separator, characters kept on the left).
#: A markdown heading separator keeps only its newline on the left so the
#: ``## `` marker opens the next piece, the way a header splitter intends.
SEPARATORS: tuple[tuple[str, int], ...] = (
    ("\n## ", 1),
    ("\n### ", 1),
    ("\n\n", 2),
    ("\n", 1),
    (" ", 1),
)

_STRATEGY = {
    "\n## ": "markdown_heading",
    "\n### ": "markdown_heading",
    "\n\n": "blank_line",
    "\n": "line",
    " ": "word",
}


@dataclass(frozen=True)
class RenderedDocument:
    """The markdown rendering plus every unit's range inside it."""

    text: str
    spans: Mapping[str, tuple[int, int]]

    def units_in(self, start: int, end: int) -> list[str]:
        return [
            unit_id
            for unit_id, (unit_start, unit_end) in self.spans.items()
            if unit_start < end and unit_end > start
        ]


def render_markdown(
    units: Sequence[RawDocumentUnit], *, separator: str = RENDER_SEPARATOR
) -> RenderedDocument:
    """Render canonical units as one markdown document, recording their spans.

    The canonical stream is already markdown -- tables are pipe tables, lists are
    ``- `` items -- so only headings are decorated, with the ATX marker their
    ``heading_level`` implies.
    """
    parts: list[str] = []
    spans: dict[str, tuple[int, int]] = {}
    cursor = 0
    for unit in units:
        if parts:
            cursor += len(separator)
        if unit.type == UnitType.HEADING:
            marker = "#" * (unit.heading_level or 2) + " "
            parts.append(marker + unit.text)
            spans[unit.unit_id] = (cursor + len(marker), cursor + len(marker) + len(unit.text))
            cursor += len(marker) + len(unit.text)
        else:
            parts.append(unit.text)
            spans[unit.unit_id] = (cursor, cursor + len(unit.text))
            cursor += len(unit.text)
    return RenderedDocument(text=separator.join(parts), spans=spans)


def _split_points(text: str, start: int, end: int, separator: str, keep_left: int) -> list[int]:
    points: list[int] = []
    position = text.find(separator, start, end)
    while position != -1:
        cut = position + keep_left
        if start < cut < end:
            points.append(cut)
        position = text.find(separator, position + 1, end)
    return points


def _split_range(
    document: str,
    start: int,
    end: int,
    *,
    counter: TokenCounter,
    max_tokens: int,
    separators: Sequence[tuple[str, int]] = SEPARATORS,
) -> list[tuple[int, int, str]]:
    """Cut ``[start, end)`` into pieces that each fit, preferring earlier separators.

    Pieces partition the range exactly, so a chunk assembled from them is a
    contiguous slice of the rendered document and its character offsets stay
    exact.
    """
    if counter.count(document[start:end]) <= max_tokens:
        return [(start, end, "whole")]

    for index, (separator, keep_left) in enumerate(separators):
        points = _split_points(document, start, end, separator, keep_left)
        if not points:
            continue
        pieces: list[tuple[int, int, str]] = []
        cursor = start
        for point in [*points, end]:
            if point <= cursor:
                continue
            if counter.count(document[cursor:point]) <= max_tokens:
                pieces.append((cursor, point, _STRATEGY[separator]))
            else:
                pieces.extend(
                    _split_range(
                        document,
                        cursor,
                        point,
                        counter=counter,
                        max_tokens=max_tokens,
                        separators=separators[index + 1 :],
                    )
                )
            cursor = point
        return pieces

    # Last resort: the frozen counter's own character split, which is lossless,
    # so the offsets still add up.
    pieces = []
    cursor = start
    for piece in counter.split(document[start:end], max_tokens):
        if not piece:
            continue
        pieces.append((cursor, cursor + len(piece), "character"))
        cursor += len(piece)
    return pieces


def _trim(document: str, start: int, end: int) -> tuple[int, int]:
    while start < end and document[start].isspace():
        start += 1
    while end > start and document[end - 1].isspace():
        end -= 1
    return start, end


def _leading_heading(
    document: str, start: int, end: int, heading_spans: Sequence[tuple[int, int]]
) -> str | None:
    """The run of heading lines this chunk opens with, verbatim.

    ``heading`` has to be a byte-exact leading substring of ``text`` for the
    shared chunk schema -- ``structural_qa.check_chunk_headings`` strips it as a
    literal prefix -- so it is taken from the document, markers included.
    """
    last = None
    for heading_start, heading_end in heading_spans:
        if heading_end <= start or heading_start >= end:
            continue
        marker = document.rfind("\n", start, heading_start) + 1
        marker = max(marker, start)
        if last is None and marker != start:
            return None
        if last is not None and document[last:marker].strip():
            break
        last = min(heading_end, end)
    return document[start:last] if last is not None else None


def chunk_units(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    chunk_size_tokens: int = CHUNK_SIZE_TOKENS,
    chunk_overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
    hard_max_tokens: int = 1126,
    separators: Sequence[tuple[str, int]] = SEPARATORS,
) -> list[dict[str, Any]]:
    """Chunk a canonical corpus the way an ordinary markdown splitter would."""
    if chunk_overlap_tokens >= chunk_size_tokens:
        raise ValueError("chunk_overlap_tokens must be smaller than chunk_size_tokens")
    if not units:
        return []

    document = render_markdown(units, separator=RENDER_SEPARATOR)
    text = document.text
    by_id = {unit.unit_id: unit for unit in units}
    heading_spans = sorted(
        span
        for unit_id, span in document.spans.items()
        if by_id[unit_id].type == UnitType.HEADING
    )

    pieces = _split_range(
        text,
        0,
        len(text),
        counter=counter,
        max_tokens=chunk_size_tokens,
        separators=separators,
    )

    groups: list[list[tuple[int, int, str]]] = []
    current: list[tuple[int, int, str]] = []
    for piece in pieces:
        if current and counter.count(text[current[0][0] : piece[1]]) > chunk_size_tokens:
            groups.append(current)
            tail: list[tuple[int, int, str]] = []
            carried = 0
            for previous in reversed(current):
                cost = counter.count(text[previous[0] : previous[1]])
                if carried + cost > chunk_overlap_tokens:
                    break
                tail.insert(0, previous)
                carried += cost
            current = [*tail, piece]
            continue
        current.append(piece)
    if current:
        groups.append(current)

    document_id = units[0].document_id
    chunks: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        start, end = _trim(text, group[0][0], group[-1][1])
        if start >= end:
            continue
        body = text[start:end]
        tokens = counter.count(body)
        assert tokens <= hard_max_tokens, f"chunk {index} exceeds hard cap: {tokens}"

        covered = document.units_in(start, end)
        content = [unit_id for unit_id in covered if by_id[unit_id].type != UnitType.HEADING]
        paths: list[list[str]] = []
        for unit_id in content:
            path = list(by_id[unit_id].section_path or ())
            if path and path not in paths:
                paths.append(path)
        pages = sorted(
            {
                by_id[unit_id].source.page
                for unit_id in content
                if by_id[unit_id].source.page is not None
            }
        )
        chunks.append(
            {
                "chunk_id": f"{document_id}:md-chunk-{index:04d}",
                "text": body,
                "unit_ids": content,
                "token_count": tokens,
                "pages": pages,
                "section_paths": paths,
                "heading": _leading_heading(text, start, end, heading_spans),
                "split_strategies": sorted({strategy for _, _, strategy in group}),
                "char_start": start,
                "char_end": end,
            }
        )
    return chunks
