"""Demote a table caption the layout model reported as a section header.

A period or column label printed directly above its table ("31 Aralik 2024")
is set apart typographically, so the layout model reports it as
``section-header``. The section state machine then opens a section named after
a table caption, and every unit that follows is filed under it -- including the
tables of a completely different note further down the page.

The signal used here is duplication, and it is text-agnostic: the layout model
emits such a caption **twice**, once as its own box and once as the leading
cell of the table it captions. So a heading is a caption when its text appears
verbatim as the only filled cell of a row in the table immediately before or
after it. Nothing about the caption's wording, and no date format, is matched.

The heading is demoted to body text rather than dropped: it stays in the stream
in its original position, and the section it wrongly opened simply never opens.

This is opt-in. Callers that do not ask for it get the untouched block stream.
"""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Sequence, TypeVar

from .models import UnitType

_Block = TypeVar("_Block")

_EMPHASIS = re.compile(r"^[*_]+|[*_]+$")
_TABLE_DIVIDER = re.compile(r"^\s*\|(?:\s*:?-{2,}:?\s*\|)+\s*$")


def _normalized(text: str) -> str:
    """Compare on content: emphasis and spacing are serialization."""
    return " ".join(_EMPHASIS.sub("", text.strip()).split()).casefold()


def caption_cells(table_text: str) -> set[str]:
    """Normalized text of every row that carries exactly one filled cell.

    A row with several populated cells is data. A row with one is a caption or
    a band label -- the shape a repeated table caption takes.
    """
    captions: set[str] = set()
    for line in table_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        if _TABLE_DIVIDER.match(stripped):
            continue
        filled = [cell.strip() for cell in stripped.strip("|").split("|") if cell.strip()]
        if len(filled) == 1:
            normalized = _normalized(filled[0])
            if normalized:
                captions.add(normalized)
    return captions


def demote_table_captions(
    blocks: Sequence[_Block],
) -> tuple[list[_Block], set[str]]:
    """Turn every heading that captions an adjacent table into body text.

    Returns the rewritten blocks and the texts that were demoted, so the
    decision stays auditable rather than silent.
    """
    captions_by_index: dict[int, set[str]] = {
        index: caption_cells(block.text)
        for index, block in enumerate(blocks)
        if block.unit_type == UnitType.TABLE
    }

    demoted: set[str] = set()
    rewritten: list[_Block] = []
    for index, block in enumerate(blocks):
        if block.heading_level is None:
            rewritten.append(block)
            continue
        text = _normalized(block.text)
        neighbours = (
            captions_by_index.get(index - 1, set())
            | captions_by_index.get(index + 1, set())
        )
        if text and text in neighbours:
            demoted.add(block.text)
            rewritten.append(
                replace(block, unit_type=UnitType.PARAGRAPH, heading_level=None)
            )
            continue
        rewritten.append(block)
    return rewritten, demoted
