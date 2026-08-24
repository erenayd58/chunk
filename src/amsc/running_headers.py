"""Detect running page furniture that the layout model reports as a heading.

A chapter banner repeated at the top of every page of a chapter is classified
by the layout model as ``section-header``, indistinguishable from a real
heading. Fed to the section state machine it opens a new section on every page,
which reassigns a paragraph that merely continues across the page break and
inserts a heading in the middle of a sentence.

The signal used here is positional and text-agnostic: a heading is running
furniture when the same text is the first block of a logical page on several
distinct physical pages. No document, heading text or layout is hard-coded.

This is opt-in. Callers that do not ask for it get the untouched block stream.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence, TypeVar

_Block = TypeVar("_Block")

DEFAULT_MIN_PAGES = 3


def _normalized(text: str) -> str:
    return " ".join(text.split()).strip().casefold()


def running_header_texts(
    blocks: Sequence[_Block],
    *,
    min_pages: int = DEFAULT_MIN_PAGES,
) -> set[str]:
    """Normalized texts that lead a logical page on ``min_pages`` or more pages."""
    if min_pages < 2:
        raise ValueError("min_pages must be at least 2")

    seen_logical_page: set[tuple[int, str]] = set()
    pages_by_text: defaultdict[str, set[int]] = defaultdict(set)

    for block in blocks:
        key = (block.page, block.logical_page_side)
        if key in seen_logical_page:
            continue
        seen_logical_page.add(key)
        if block.heading_level is None:
            # Only a heading-classified lead block can be mistaken for a
            # section start; a leading paragraph is ordinary body text.
            continue
        pages_by_text[_normalized(block.text)].add(block.page)

    return {
        text
        for text, pages in pages_by_text.items()
        if text and len(pages) >= min_pages
    }


def drop_running_headers(
    blocks: Sequence[_Block],
    *,
    min_pages: int = DEFAULT_MIN_PAGES,
) -> tuple[list[_Block], set[str]]:
    """Remove every occurrence of a detected running header.

    Returns the filtered blocks and the texts that were treated as furniture,
    so the decision stays auditable rather than silent.
    """
    furniture = running_header_texts(blocks, min_pages=min_pages)
    if not furniture:
        return list(blocks), furniture
    kept = [
        block
        for block in blocks
        if not (
            block.heading_level is not None
            and _normalized(block.text) in furniture
        )
    ]
    return kept, furniture
