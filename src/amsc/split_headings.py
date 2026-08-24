"""Rejoin a section number the layout model split away from its own title.

One printed heading line can reach us as two layout boxes: the section number
in one, the title in the other, side by side. Both are classified
``section-header``, so the stream ends up with a heading that is nothing but
``24.`` -- opening a section with no title -- and a second heading carrying the
title without its number. Column ordering can even emit them the wrong way
round, so the number arrives after the title it belongs to.

The signal is narrow on purpose. Two headings sharing a text line are usually
two *real* headings printed side by side -- board member names, a grid of
service names -- and merging those would be wrong. What marks this case is that
one fragment carries **no title text at all**: it is pure section numbering.
A heading cannot be only a number, so its title must be the fragment beside it.

Both must therefore hold:

  * one of the two blocks is section numbering with no alphabetic content
  * the two sit on the same text line of the same logical page, vertically
    overlapping and horizontally disjoint

The surviving heading carries both fragments in left-to-right order and the
union of their boxes. No document, number or title is matched by name.

This is opt-in. Callers that do not ask for it get the untouched block stream.
"""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Sequence, TypeVar

_Block = TypeVar("_Block")

_EMPHASIS = re.compile(r"^[*_]+|[*_]+$")
#: ``24.``, ``3)``, ``2.4.`` -- numbering and nothing else. The closing
#: terminator is required: it is what separates a section number from a bare
#: year, and a milestone timeline prints years as headings side by side.
_NUMBERING_ONLY = re.compile(r"^\d+(?:\.\d+)*[.)]$")

#: Two boxes belong to one printed line when the shorter one is more than half
#: covered by the taller one's vertical span.
MIN_LINE_OVERLAP = 0.5


def _bare(text: str) -> str:
    return _EMPHASIS.sub("", text.strip()).strip()


def is_numbering_only(text: str) -> bool:
    """True when a heading carries a section number but no title."""
    bare = _bare(text)
    if not bare or any(character.isalpha() for character in bare):
        return False
    return bool(_NUMBERING_ONLY.match(bare))


def _span_overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _shares_a_text_line(first, second) -> bool:
    if first.page != second.page:
        return False
    if first.logical_page_side != second.logical_page_side:
        return False
    one, two = first.physical_bbox, second.physical_bbox
    if one is None or two is None:
        return False
    vertical = _span_overlap(one[1], one[3], two[1], two[3])
    shorter = min(one[3] - one[1], two[3] - two[1])
    if shorter <= 0 or vertical / shorter <= MIN_LINE_OVERLAP:
        return False
    # Side by side, not stacked: a horizontal overlap means two lines.
    return _span_overlap(one[0], one[2], two[0], two[2]) <= 0


def _union(one, two):
    if one is None or two is None:
        return one or two
    return (
        min(one[0], two[0]),
        min(one[1], two[1]),
        max(one[2], two[2]),
        max(one[3], two[3]),
    )


def rejoin_split_headings(
    blocks: Sequence[_Block],
) -> tuple[list[_Block], set[str]]:
    """Merge every numbering-only heading with the title beside it.

    Returns the rewritten blocks and the merged texts, so the decision stays
    auditable rather than silent.
    """
    merged: set[str] = set()
    rewritten: list[_Block] = []
    index = 0
    while index < len(blocks):
        first = blocks[index]
        second = blocks[index + 1] if index + 1 < len(blocks) else None
        if (
            second is not None
            and first.heading_level is not None
            and second.heading_level is not None
            and (is_numbering_only(first.text) ^ is_numbering_only(second.text))
            and _shares_a_text_line(first, second)
        ):
            left, right = (
                (first, second)
                if first.physical_bbox[0] <= second.physical_bbox[0]
                else (second, first)
            )
            text = f"{left.text} {right.text}"
            merged.add(text)
            rewritten.append(
                replace(
                    first,
                    text=text,
                    physical_bbox=_union(first.physical_bbox, second.physical_bbox),
                    logical_bbox=_union(first.logical_bbox, second.logical_bbox),
                )
            )
            index += 2
            continue
        rewritten.append(first)
        index += 1
    return rewritten, merged
