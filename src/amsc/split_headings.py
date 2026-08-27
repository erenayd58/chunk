"""Rejoin a heading the layout model split away from part of itself.

Two disjoint splits are repaired here, and they are opposites geometrically:
:func:`rejoin_split_headings` merges fragments printed **side by side** on one
text line, :func:`rejoin_hyphenated_headings` merges fragments **stacked** on
two lines of one column. Neither can match the other's pairs.

## The split-off number

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

## The hyphenated wrap

A heading too long for its column wraps mid-word, and each printed line reaches
us as its own ``section-header`` box: ``Birim Nezdinde Takibi Yurutulen Devam
Eden Da-`` and, on the line below it, ``valar``. Downstream both are headings,
so the chunker is free to end one chunk on ``Da-`` and open the next on
``valar`` -- and the title a reader searches for exists in neither.

Here too the signal is narrow, and every part of it is needed. Two headings
stacked in one column are usually a title and its subtitle; what marks a wrap is
that the upper one **ends mid-word** and the lower one **continues it**:

  * the upper fragment ends in a hyphen with a letter before it -- a block that
    is only a dash, or that ends in one used as a range, is not a broken word
  * the lower fragment starts with a lowercase letter -- a capital or a number
    starts a new heading however the line above it ended
  * the two sit on consecutive lines of one column: same logical page,
    horizontally overlapping, and the lower box's top edge within
    ``MAX_LINE_GAP`` of the upper box's bottom edge

The hyphen is dropped when the fragments are joined, because that is what it is
there for. **This is the one guess in the rule**: a hard hyphen in a compound
that happens to break at its own hyphen (``limit-risk``) is indistinguishable
from a soft one without a lexicon, and would be joined into ``limitrisk``. On
both KKB corpora the rule fires twice and both are soft hyphens.

Both passes are opt-in. Callers that do not ask for one get the untouched block
stream.
"""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Sequence, TypeVar

_Block = TypeVar("_Block")

_EMPHASIS = re.compile(r"^[*_]+|[*_]+$")
_LEADING_EMPHASIS = re.compile(r"^[*_]+")
_TRAILING_EMPHASIS = re.compile(r"[*_]+$")
#: ``24.``, ``3)``, ``2.4.`` -- numbering and nothing else. The closing
#: terminator is required: it is what separates a section number from a bare
#: year, and a milestone timeline prints years as headings side by side.
_NUMBERING_ONLY = re.compile(r"^\d+(?:\.\d+)*[.)]$")

#: Two boxes belong to one printed line when the shorter one is more than half
#: covered by the taller one's vertical span.
MIN_LINE_OVERLAP = 0.5

#: The largest vertical gap, in points, between one printed line's bottom edge
#: and the next line's top edge. Consecutive lines of one heading are set solid
#: -- the two observed pairs sit at 0.0 and 3.0 -- while the next *paragraph*
#: below a heading clears it by a leading of its own.
MAX_LINE_GAP = 6.0

#: Hyphens a typesetter breaks a word on. A dash (en, em) is not one of them:
#: it separates, it does not continue.
_HYPHENS = "-­‐‑"  # hyphen-minus, soft, hyphen, non-breaking


def _bare(text: str) -> str:
    return _EMPHASIS.sub("", text.strip()).strip()


def _emphasis(text: str) -> tuple[str, str]:
    """The emphasis markers around a fragment, as ``(opening, closing)``.

    A wrapped heading is emphasised once around the whole printed title, so
    each fragment arrives carrying its own copy. Rejoining has to put one pair
    back around the joined text rather than leave a marker stranded inside it.
    """
    stripped = text.strip()
    opening = _LEADING_EMPHASIS.match(stripped)
    closing = _TRAILING_EMPHASIS.search(stripped)
    return (opening.group(0) if opening else "", closing.group(0) if closing else "")


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


def ends_mid_word(text: str) -> bool:
    """True when a fragment breaks off mid-word at a hyphen.

    The letter before the hyphen is what carries the claim: it is the tail of a
    word the line ran out of room for. ``-`` alone, ``2019-`` and ``KKB -`` all
    end in a hyphen and none of them is a broken word.
    """
    bare = _bare(text)
    if len(bare) < 2 or bare[-1] not in _HYPHENS:
        return False
    return bare[-2].isalpha()


def continues_mid_word(text: str) -> bool:
    """True when a fragment reads as the rest of a word, not a new heading.

    A wrapped word resumes in lower case. Anything else -- a capital, a number,
    a bullet -- starts something new, however the line above it ended.
    """
    bare = _bare(text)
    return bool(bare) and bare[0].isalpha() and bare[0].islower()


def _continues_below(upper, lower) -> bool:
    """True when ``lower`` is the next printed line under ``upper``."""
    if upper.page != lower.page:
        return False
    if upper.logical_page_side != lower.logical_page_side:
        return False
    one, two = upper.physical_bbox, lower.physical_bbox
    if one is None or two is None:
        return False
    # Stacked, not side by side: the lower box starts under the upper one.
    if not 0.0 <= two[1] - one[3] <= MAX_LINE_GAP:
        return False
    return _span_overlap(one[0], one[2], two[0], two[2]) > 0


def rejoin_hyphenated_headings(
    blocks: Sequence[_Block],
) -> tuple[list[_Block], set[str]]:
    """Merge every heading that wrapped mid-word with the line completing it.

    The hyphen is dropped, so ``Da-`` and ``valar`` become ``Davalar``. A
    heading that wrapped twice is merged repeatedly, so three fragments still
    come out as one heading.

    Returns the rewritten blocks and the merged texts, so the decision stays
    auditable rather than silent.
    """
    merged: set[str] = set()
    rewritten: list[_Block] = []
    index = 0
    while index < len(blocks):
        current = blocks[index]
        index += 1
        while index < len(blocks):
            following = blocks[index]
            if not (
                current.heading_level is not None
                and following.heading_level is not None
                and ends_mid_word(current.text)
                and continues_mid_word(following.text)
                and _continues_below(current, following)
            ):
                break
            opening, _ = _emphasis(current.text)
            _, closing = _emphasis(following.text)
            joined = opening + _bare(current.text)[:-1] + _bare(following.text) + closing
            current = replace(
                current,
                text=joined,
                physical_bbox=_union(current.physical_bbox, following.physical_bbox),
                logical_bbox=_union(current.logical_bbox, following.logical_bbox),
            )
            merged.add(joined)
            index += 1
        rewritten.append(current)
    return rewritten, merged


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
