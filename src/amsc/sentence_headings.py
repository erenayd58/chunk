"""Demote a standfirst sentence the layout model reported as a section header.

A chapter's opening sentence is often set in display type directly under the
chapter title. The layout model reads that size and reports it as
``section-header``, so a whole sentence opens a section and every unit below it
is filed under a section path that is a sentence.

The signal is orthographic and text-agnostic: **a heading that closes with a
full stop is a sentence, not a title.** A section title is a noun phrase; it
does not end its own clause.

Two exclusions keep the rule safe:

  * an abbreviation ends in a full stop without ending a sentence
    (``T. Garanti Bankasi A.S.``), recognised by the internal dot in its last
    token
  * numbering-only text (``24.``) is a broken heading, not a sentence, and is
    someone else's problem

A minimum word count keeps single-token oddities out. Nothing is dropped: the
sentence stays in the stream as body text, under the section it was already in.

This is opt-in. Callers that do not ask for it get the untouched block stream.
"""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Sequence, TypeVar

from .models import UnitType

_Block = TypeVar("_Block")

_EMPHASIS = re.compile(r"^[*_]+|[*_]+$")

#: Below this a full stop is more likely punctuation on a label than a
#: sentence. Conservative gate, not a tuned parameter.
MIN_SENTENCE_WORDS = 3


def _bare(text: str) -> str:
    return _EMPHASIS.sub("", text.strip()).strip()


def ends_in_abbreviation(text: str) -> bool:
    """``A.S.`` closes with a full stop without closing a sentence."""
    tokens = text.split()
    if not tokens:
        return False
    return "." in tokens[-1][:-1]


def is_sentence(text: str) -> bool:
    """True when this heading text reads as a complete sentence."""
    bare = _bare(text)
    if not bare.endswith("."):
        return False
    if not any(character.isalpha() for character in bare):
        return False
    if ends_in_abbreviation(bare):
        return False
    return len(bare.split()) >= MIN_SENTENCE_WORDS


def demote_sentence_headings(
    blocks: Sequence[_Block],
) -> tuple[list[_Block], set[str]]:
    """Turn every sentence-shaped heading into an ordinary paragraph block.

    Returns the rewritten blocks and the texts that were demoted, so the
    decision stays auditable rather than silent.
    """
    demoted: set[str] = set()
    rewritten: list[_Block] = []
    for block in blocks:
        if block.heading_level is not None and is_sentence(block.text):
            demoted.add(block.text)
            rewritten.append(
                replace(block, unit_type=UnitType.PARAGRAPH, heading_level=None)
            )
            continue
        rewritten.append(block)
    return rewritten, demoted
