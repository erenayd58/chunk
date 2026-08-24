"""Recover a numbered section heading the layout model reported as body text.

The layout model classifies most numbered section titles as ``section-header``,
and PyMuPDF4LLM then writes them as Markdown headings. On a handful of pages it
classifies the very same construct as ``text`` or ``list-item`` instead, so the
title arrives as an ordinary bold paragraph. The section state machine never
sees a heading, the new section never opens, and every table and paragraph that
belongs to it keeps the previous section's path -- one numbered note is filed
under the note before it.

The signal used here is structural and text-agnostic: a block is a missed
heading when **its whole text is a single line, that line is entirely wrapped
in bold emphasis, and it opens with a section-number prefix**. All three must
hold. An emphasised sentence fails the numbering test, a numbered list item
fails the whole-line-bold test, and a paragraph fails the single-line test. No
document, title or number is matched by name.

The promoted heading takes its level from the numbering depth relative to the
shallowest heading already in the stream, so ``7.`` becomes a sibling of the
existing top-level notes and ``2.4.`` nests one level under them.

This is opt-in. Callers that do not ask for it get the untouched block stream.
"""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Sequence, TypeVar

from .models import UnitType

_Block = TypeVar("_Block")

#: The whole line is emphasised -- not a sentence with an emphasised opening.
_FULLY_BOLD = re.compile(r"^\*\*(?!\s)(.+?)\*\*$", re.DOTALL)
#: ``7.``, ``19.``, ``2.4.`` -- section numbering closed by its own
#: terminator, followed by a real title. The terminator is required: it is
#: what separates ``9. MADDI DURAN VARLIKLAR`` from ``2024 Findeks Verileri``.
_NUMBERING = re.compile(r"^(\d+(?:\.\d+)*)[.)]\s+(\S.*)$")

#: A numbered line longer than this is prose that happens to start with a
#: figure, not a section title. Conservative gate, not a tuned parameter.
MAX_TITLE_WORDS = 15
MAX_TITLE_CHARS = 120
_SENTENCE_END = (".", "!", "?")


def numbering_depth(text: str) -> int | None:
    """Depth of the section number opening this block, or ``None``.

    ``7. ILISKILI TARAFLAR`` is depth 1, ``2.4. Onemli politikalar`` is depth 2.
    """
    stripped = text.strip()
    if len(stripped.splitlines()) != 1:
        return None
    emphasised = _FULLY_BOLD.match(stripped)
    if emphasised is None:
        return None
    inner = emphasised.group(1).strip()
    if not inner or len(inner) > MAX_TITLE_CHARS:
        return None
    numbering = _NUMBERING.match(inner)
    if numbering is None:
        return None
    title = numbering.group(2).strip()
    if not title or title.endswith(_SENTENCE_END):
        return None
    if len(inner.split()) > MAX_TITLE_WORDS:
        return None
    return len(numbering.group(1).split("."))


def is_missed_heading(text: str) -> bool:
    """True when a non-heading block is really a numbered section title."""
    return numbering_depth(text) is not None


def promote_numbered_headings(
    blocks: Sequence[_Block],
) -> tuple[list[_Block], set[str]]:
    """Turn every missed numbered title into a heading block.

    Returns the rewritten blocks and the texts that were promoted, so the
    decision stays auditable rather than silent.
    """
    levels = [
        block.heading_level
        for block in blocks
        if block.heading_level is not None
    ]
    # A recovered top-level note belongs on the document's shallowest heading
    # tier; without any heading to compare against, level 1 is the only
    # defensible choice.
    base_level = min(levels) if levels else 1

    promoted: set[str] = set()
    rewritten: list[_Block] = []
    for block in blocks:
        if block.heading_level is not None:
            rewritten.append(block)
            continue
        depth = numbering_depth(block.text)
        if depth is None:
            rewritten.append(block)
            continue
        promoted.add(block.text)
        rewritten.append(
            replace(
                block,
                unit_type=UnitType.HEADING,
                heading_level=base_level + depth - 1,
            )
        )
    return rewritten, promoted
