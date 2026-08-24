"""Demote a lead-in sentence the layout model classified as a section header.

A line that introduces the bullets under it -- "Uygulamayla;", "Bunlarin
yaninda;" -- is set apart typographically, so the layout model reports it as
``section-header`` exactly like a real title. Fed to the section state machine
it opens a section of its own, which detaches the bullets from the section they
belong to and gives them a section path named after a sentence fragment.

The signal used here is orthographic and text-agnostic: **a heading whose text
ends in a semicolon is not a title.** A semicolon leaves the clause open, so
what follows completes it; a section title is a noun phrase that stands on its
own. No document, heading text or page number is matched.

A trailing colon is deliberately *not* treated the same way. It is the ordinary
punctuation of a labelled sub-heading ("b) Likidite riski:", "1. Guclu Finansal
Yonetim:"), and those genuinely do open subsections -- demoting them would
merge the financial-note subsections and lose attribution that is correct
today.

Demoted blocks stay in the stream in their original position, as body text
under the section they were already in. Nothing is dropped.

This is opt-in. Callers that do not ask for it get the untouched block stream.
"""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Sequence, TypeVar

from .models import UnitType

_Block = TypeVar("_Block")

#: Trailing Markdown emphasis is serialization, not punctuation: the clause of
#: ``_Risk Merkezi Uye ve Urun Yonetimi Ekibi;_`` still ends in a semicolon.
_TRAILING_EMPHASIS = re.compile(r"[*_\s]+$")

#: A clause left open by this mark continues into the block that follows.
LEAD_IN_TERMINATORS = (";",)


def is_lead_in(text: str) -> bool:
    """True when this heading text is an unfinished clause, not a title."""
    return _TRAILING_EMPHASIS.sub("", text).endswith(LEAD_IN_TERMINATORS)


def demote_lead_ins(
    blocks: Sequence[_Block],
) -> tuple[list[_Block], set[str]]:
    """Turn every lead-in heading into an ordinary paragraph block.

    Returns the rewritten blocks and the texts that were demoted, so the
    decision stays auditable rather than silent.
    """
    demoted: set[str] = set()
    rewritten: list[_Block] = []
    for block in blocks:
        if block.heading_level is not None and is_lead_in(block.text):
            demoted.add(block.text)
            rewritten.append(
                replace(block, unit_type=UnitType.PARAGRAPH, heading_level=None)
            )
            continue
        rewritten.append(block)
    return rewritten, demoted
