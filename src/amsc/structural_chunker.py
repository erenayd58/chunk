"""Structure-first chunker with format-aware splitting.

The V1-V4 line lets the semantic signal propose boundaries and the token-size
prior dispose of them, which on this corpus makes ~71% of boundaries pure
token-budget cuts and leaves 62% of chunks spanning more than one section.

This chunker inverts that: document structure decides, size constrains.

  * a chunk opens at every heading and at every ``section_path`` change
  * oversized sections are split at internal *structural* seams -- table row
    groups (header row repeated), list item boundaries, sentence boundaries --
    never by character-index bisection
  * undersized sections are merged forward while they stay under target
  * the configured hard cap is a hard invariant

No embeddings are used, so this runs at parser speed with zero model cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable, Sequence

from .models import RawDocumentUnit, UnitType
from .tokenization import TokenCounter

RENDER_SEPARATOR = "\n\n"

_TABLE_DIVIDER = re.compile(r"^\|(?:\s*:?-{2,}:?\s*\|)+$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?…])(?:\s+|\n+)|\n{2,}")


@dataclass
class Fragment:
    text: str
    strategy: str
    header_repeated: bool = False


def _table_fragments(text: str, max_tokens: int, counter: TokenCounter) -> list[Fragment]:
    lines = text.splitlines()
    divider = next((i for i, line in enumerate(lines) if _TABLE_DIVIDER.match(line.strip())), None)
    if divider is None or divider == 0:
        return []
    header = lines[: divider + 1]
    body = [line for line in lines[divider + 1 :] if line.strip()]
    if not body:
        return []
    head_text = "\n".join(header)
    out: list[Fragment] = []
    current: list[str] = []
    for row in body:
        candidate = "\n".join([head_text, *current, row])
        if current and counter.count(candidate) > max_tokens:
            out.append(Fragment("\n".join([head_text, *current]), "table_row_group", bool(out)))
            current = [row]
        else:
            current.append(row)
    if current:
        out.append(Fragment("\n".join([head_text, *current]), "table_row_group", bool(out)))
    return out


def _greedy_pack(pieces: Sequence[str], joiner: str, max_tokens: int,
                 counter: TokenCounter, strategy: str) -> list[Fragment]:
    out: list[Fragment] = []
    current: list[str] = []
    for piece in pieces:
        candidate = joiner.join([*current, piece])
        if current and counter.count(candidate) > max_tokens:
            out.append(Fragment(joiner.join(current), strategy))
            current = [piece]
        else:
            current.append(piece)
    if current:
        out.append(Fragment(joiner.join(current), strategy))
    return out


def split_unit_text(text: str, *, unit_type: UnitType, max_tokens: int,
                    counter: TokenCounter) -> list[Fragment]:
    """Split one oversized unit at the best available structural seam."""
    if counter.count(text) <= max_tokens:
        return [Fragment(text, "whole")]

    if unit_type == UnitType.TABLE:
        fragments = _table_fragments(text, max_tokens, counter)
        if fragments and all(counter.count(f.text) <= max_tokens for f in fragments):
            return fragments

    if unit_type == UnitType.LIST:
        items: list[str] = []
        for line in text.splitlines():
            if _LIST_ITEM.match(line) or not items:
                items.append(line)
            else:
                items[-1] += "\n" + line
        if len(items) > 1:
            fragments = _greedy_pack(items, "\n", max_tokens, counter, "list_items")
            if all(counter.count(f.text) <= max_tokens for f in fragments):
                return fragments

    sentences = [s for s in _SENTENCE_END.split(text) if s and s.strip()]
    if len(sentences) > 1:
        fragments = _greedy_pack(sentences, " ", max_tokens, counter, "sentences")
        if all(counter.count(f.text) <= max_tokens for f in fragments):
            return fragments

    words = text.split()
    if len(words) > 1:
        fragments = _greedy_pack(words, " ", max_tokens, counter, "words")
        if all(counter.count(f.text) <= max_tokens for f in fragments):
            return fragments

    return [Fragment(part, "character_fallback") for part in counter.split(text, max_tokens)]


@dataclass
class Piece:
    """One atomic renderable item: a whole unit or a fragment of one."""

    unit_id: str
    text: str
    tokens: int
    page: int | None
    section_path: tuple[str, ...]
    strategy: str


@dataclass
class Section:
    heading: str | None
    section_path: tuple[str, ...]
    pieces: list[Piece] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return sum(p.tokens for p in self.pieces)


def _sections(units: Sequence[RawDocumentUnit], counter: TokenCounter,
              hard_max: int) -> list[Section]:
    sections: list[Section] = []
    current: Section | None = None
    pending_heading: list[str] = []

    for unit in units:
        path = tuple(unit.section_path or ())
        if unit.type == UnitType.HEADING:
            pending_heading.append(unit.text)
            current = None
            continue
        if current is None or current.section_path != path:
            heading = RENDER_SEPARATOR.join(pending_heading) if pending_heading else None
            current = Section(heading=heading, section_path=path)
            sections.append(current)
            pending_heading = []

        budget = hard_max - (counter.count(current.heading) + 2 if current.heading else 0)
        budget = max(budget, 32)
        for index, fragment in enumerate(
            split_unit_text(unit.text, unit_type=unit.type, max_tokens=budget, counter=counter)
        ):
            unit_id = unit.unit_id if fragment.strategy == "whole" else f"{unit.unit_id}#f{index + 1}"
            current.pieces.append(
                Piece(
                    unit_id=unit_id,
                    text=fragment.text,
                    tokens=counter.count(fragment.text),
                    page=unit.source.page,
                    section_path=path,
                    strategy=fragment.strategy,
                )
            )
    return [s for s in sections if s.pieces]


def _render(heading: str | None, pieces: Iterable[Piece]) -> str:
    parts = ([heading] if heading else []) + [p.text for p in pieces]
    return RENDER_SEPARATOR.join(parts)


def chunk_units(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    min_tokens: int = 160,
    target_tokens: int = 700,
    soft_max_tokens: int = 900,
    hard_max_tokens: int = 1126,
) -> list[dict]:
    sections = _sections(units, counter, hard_max_tokens)

    # 1. split oversized sections at piece boundaries, aiming at target
    split_sections: list[Section] = []
    for section in sections:
        if section.tokens <= soft_max_tokens:
            split_sections.append(section)
            continue
        head_cost = counter.count(section.heading) + 2 if section.heading else 0
        current = Section(section.heading, section.section_path)
        for piece in section.pieces:
            projected = head_cost + current.tokens + piece.tokens
            if current.pieces and projected > target_tokens:
                split_sections.append(current)
                current = Section(section.heading, section.section_path)
            current.pieces.append(piece)
        if current.pieces:
            split_sections.append(current)

    # 2. merge undersized neighbours.
    #
    # The parser emits a flat, depth-1 section_path, so a document with 508
    # headings has ~508 "sections" of a few units each. Requiring merge
    # partners to share a section_path therefore never fires and leaves a
    # heavily fragmented corpus, which measurably costs retrieval. Undersized
    # blocks are allowed to merge across the section boundary; every block
    # keeps its own heading in the rendered text, so no heading is lost and the
    # chunk still states which sections it covers.
    Block = tuple[str | None, list[Piece], tuple[str, ...]]
    groups: list[list[Block]] = []
    sizes: list[int] = []
    for section in split_sections:
        block: Block = (section.heading, section.pieces, section.section_path)
        size = section.tokens + (counter.count(section.heading) + 2 if section.heading else 0)
        if groups and (sizes[-1] < min_tokens or size < min_tokens) and sizes[-1] + size <= target_tokens:
            groups[-1].append(block)
            sizes[-1] += size
            continue
        groups.append([block])
        sizes.append(size)

    document_id = units[0].document_id
    chunks: list[dict] = []
    for index, group in enumerate(groups, start=1):
        text = RENDER_SEPARATOR.join(
            _render(heading, pieces) for heading, pieces, _ in group
        )
        tokens = counter.count(text)
        assert tokens <= hard_max_tokens, f"chunk {index} exceeds hard cap: {tokens}"
        pieces = [p for _, block_pieces, _ in group for p in block_pieces]
        paths: list[list[str]] = []
        for _, _, path in group:
            if path and list(path) not in paths:
                paths.append(list(path))
        chunks.append(
            {
                "chunk_id": f"{document_id}:s-chunk-{index:04d}",
                "text": text,
                "unit_ids": [p.unit_id for p in pieces],
                "token_count": tokens,
                "pages": sorted({p.page for p in pieces if p.page is not None}),
                "section_paths": paths,
                "heading": group[0][0],
                "split_strategies": sorted({p.strategy for p in pieces}),
            }
        )
    return chunks
