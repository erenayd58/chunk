"""Separate looking like a heading from bearing hierarchy.

The layout model answers one question -- *is this box set apart as a heading?*
-- and the canonical model has been treating that answer as if it were the
answer to a different one: *does this heading open a section?* On a page of
prose the two coincide. On a card grid they do not, and KKB 2024 page 12 shows
what that costs: a chapter title, a decorative phrase, eight year labels and
twenty-one award names all arrive as ``section-header`` boxes, so twenty-nine
sections open where a reader sees one, and each new "section" evicts the
chapter from every ``section_path`` below it.

This module assigns each heading a **semantic role** and derives from it the
one fact the hierarchy actually needs, ``opens_section``. A heading keeps its
type, its text and its position either way -- nothing is dropped, and a heading
that does not open a section is still a heading a reader can see.

===========  =============================================================
``section``  a title that owns the content under it
``group``    a key that partitions the section it sits in -- a year, an
             ordinal -- rather than titling anything of its own
``item``     one of a repeated run of labels, each naming a single entry in
             a list: an award, a committee, a board member
``display``  type set for the page rather than for the structure: a
             standfirst under its own chapter title, a decorative phrase,
             a banner repeated as page furniture
===========  =============================================================

``section`` and ``group`` open a section. ``item`` and ``display`` do not.

Four rules decide it, in order. Each is a single claim about layout or
orthography; none matches a document, a page or a wording:

1. **display** -- a heading repeated at the top of several pages is furniture;
   and a heading set larger than the heading directly above it on the same page
   is display type, provided its whole size tier on that page labels nothing,
   or it is the only heading of its size there. A tier used repeatedly on one
   page *to label content* is that page's subheading tier however large it is
   set, so ``Vizyon`` / ``Misyon`` / ``Temel Stratejiler`` stay sections.
2. **group** -- a heading whose whole text is a bare number. A number names a
   period or an ordinal position; it is a key, never a title. With no heading
   enclosing it there is nothing for it to be a key *of*, and it is display.
3. **item** -- a heading set no larger than the body text around it, with at
   least two siblings of the same size inside the same enclosing heading. Type
   no bigger than the page's own prose is a label on that prose, and a size
   used repeatedly inside one scope is a list.
4. **section** -- everything else.

Section numbering overrides every layout signal: a heading that opens with
``7.`` or ``2.4`` is the document's own statement of its structure, and rules 1
and 3 never demote one.

This is opt-in. Callers that do not ask for it get the untouched block stream,
and a corpus carrying no measured type size is returned unchanged.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
import re
import statistics
from typing import Sequence, TypeVar

from .models import ROLE_OPENS_SECTION, SemanticRole, UnitType

_Block = TypeVar("_Block")

_EMPHASIS = re.compile(r"^[*_]+|[*_]+$")
#: The whole text is a number and nothing else: ``2014``, ``10``, ``2.4``. A
#: percentage is deliberately excluded -- ``%18,18`` is a value read off a
#: chart, and a value keys nothing.
_BARE_NUMBER = re.compile(r"^[\d.,]+$")
#: Section numbering opening a title -- the same shape
#: :mod:`amsc.heading_levels` uses, so the two agree on what "numbered" means.
_NUMBERED = re.compile(r"^(?:(\d+(?:\.\d{1,2})+)\.?|(\d+)[.)])\s+\S")

#: Type sizes are compared at this resolution, matching the level pass.
SIZE_RESOLUTION = 0.5
#: A heading within this many points of the page's body text is body-sized.
#: Not a tuned parameter: it absorbs the rounding in a reported glyph size.
BODY_SIZE_TOLERANCE = 0.4
#: A size used this many times inside one scope is a list, not a set of
#: sections. Two labels are a coincidence; three are a pattern.
MIN_ITEM_RUN = 3
#: A heading leading this many distinct physical pages is page furniture.
#: Same threshold, and the same signal, as :mod:`amsc.running_headers`.
FURNITURE_MIN_PAGES = 3


def strip_emphasis(text: str) -> str:
    return _EMPHASIS.sub("", text.strip()).strip()


def _normalised(text: str) -> str:
    return " ".join(strip_emphasis(text).split()).casefold()


def is_numbered(text: str) -> bool:
    """True when the text opens with the document's own section numbering."""
    return _NUMBERED.match(strip_emphasis(text)) is not None


def _quantise(size: float | None) -> float | None:
    if size is None:
        return None
    return round(float(size) / SIZE_RESOLUTION) * SIZE_RESOLUTION


def _is_heading(block: _Block) -> bool:
    return getattr(block, "unit_type", None) == UnitType.HEADING


def assign_semantic_roles(
    blocks: Sequence[_Block],
) -> tuple[list[_Block], dict[str, int]]:
    """Give every heading a semantic role and the ``opens_section`` it implies.

    Returns the rewritten blocks and a ``{role: count}`` census, so the decision
    stays auditable rather than silent.
    """
    headings = [block for block in blocks if _is_heading(block)]
    if not headings:
        return list(blocks), {}
    if all(getattr(block, "font_size", None) is None for block in headings):
        # Nothing to measure: every rule below is about relative type size, so
        # the honest answer is to leave the stream alone.
        return list(blocks), {}

    tier = {id(block): _quantise(getattr(block, "font_size", None)) for block in headings}
    governs = _governed_block_counts(blocks)
    gap_before, previous_heading = _heading_neighbours(blocks)
    scope = _enclosing_scope(headings, tier)
    body = _body_size_by_page(blocks)
    furniture, furniture_pages = _page_furniture(blocks)

    roles: dict[int, SemanticRole] = {}
    reasons: dict[int, str] = {}

    def assign(block, role, reason):
        roles[id(block)] = role
        reasons[id(block)] = reason

    # -- 1. display --------------------------------------------------------
    for block in headings:
        if is_numbered(block.text):
            continue
        key = _normalised(block.text)
        if key in furniture:
            assign(
                block,
                SemanticRole.DISPLAY,
                "leads %d distinct pages: page furniture" % len(furniture_pages[key]),
            )
            continue
        size = tier[id(block)]
        prior = previous_heading.get(id(block))
        if size is None or prior is None:
            continue
        prior_size = tier.get(id(prior))
        if prior_size is None or size <= prior_size:
            continue
        if getattr(prior, "page", None) != getattr(block, "page", None):
            continue
        peers = [
            other
            for other in headings
            if other is not block
            and getattr(other, "page", None) == getattr(block, "page", None)
            and tier[id(other)] == size
        ]
        if not peers:
            assign(block, SemanticRole.DISPLAY, "the only heading of its size on the page")
        elif governs[id(block)] == 0 and all(governs[id(p)] == 0 for p in peers):
            assign(block, SemanticRole.DISPLAY, "its whole size tier labels nothing here")

    # -- 2. group ----------------------------------------------------------
    for block in headings:
        if id(block) in roles:
            continue
        if not _BARE_NUMBER.fullmatch(strip_emphasis(block.text)):
            continue
        if scope.get(id(block)) is None:
            assign(block, SemanticRole.DISPLAY, "a bare number with nothing to be a key of")
        else:
            assign(block, SemanticRole.GROUP, "a bare number: a period or ordinal key")

    # -- 3. item -----------------------------------------------------------
    buckets: dict[tuple[int | None, float | None], list] = defaultdict(list)
    for block in headings:
        if id(block) in roles or is_numbered(block.text):
            continue
        size = getattr(block, "font_size", None)
        page_body = body.get(getattr(block, "page", None))
        if size is None or page_body is None or size > page_body + BODY_SIZE_TOLERANCE:
            continue
        buckets[(scope.get(id(block)), tier[id(block)])].append(block)
    for members in buckets.values():
        if len(members) < MIN_ITEM_RUN:
            continue
        for member in members:
            assign(
                member,
                SemanticRole.ITEM,
                "one of %d body-sized labels inside one scope" % len(members),
            )

    # -- 4. section --------------------------------------------------------
    rewritten: list[_Block] = []
    census: dict[str, int] = {}
    for block in blocks:
        if not _is_heading(block):
            rewritten.append(block)
            continue
        role = roles.get(id(block), SemanticRole.SECTION)
        census[role.value] = census.get(role.value, 0) + 1
        rewritten.append(
            replace(
                block,
                semantic_role=role,
                opens_section=ROLE_OPENS_SECTION[role],
                role_reason=reasons.get(id(block), "no rule demoted it"),
            )
        )
    return rewritten, census


# ---------------------------------------------------------------------------
# features
# ---------------------------------------------------------------------------


def _governed_block_counts(blocks: Sequence[_Block]) -> dict[int, int]:
    """How many content blocks follow each heading before the next one."""
    counts: dict[int, int] = {}
    pending: list[_Block] = []
    for block in blocks:
        if _is_heading(block):
            counts[id(block)] = 0
            pending = [block]
            continue
        for heading in pending:
            counts[id(heading)] += 1
    return counts


def _heading_neighbours(
    blocks: Sequence[_Block],
) -> tuple[dict[int, int], dict[int, _Block]]:
    """Content blocks before each heading, and the heading before it."""
    gap: dict[int, int] = {}
    previous: dict[int, _Block] = {}
    last: _Block | None = None
    since = 0
    for block in blocks:
        if not _is_heading(block):
            since += 1
            continue
        gap[id(block)] = since
        if last is not None:
            previous[id(block)] = last
        last, since = block, 0
    return gap, previous


def _enclosing_scope(
    headings: Sequence[_Block], tier: dict[int, float | None]
) -> dict[int, int | None]:
    """The nearest preceding heading set in strictly larger type."""
    scope: dict[int, int | None] = {}
    stack: list[tuple[float, int]] = []
    for block in headings:
        size = tier[id(block)]
        if size is None:
            scope[id(block)] = stack[-1][1] if stack else None
            continue
        while stack and stack[-1][0] <= size:
            stack.pop()
        scope[id(block)] = stack[-1][1] if stack else None
        stack.append((size, id(block)))
    return scope


def _body_size_by_page(blocks: Sequence[_Block]) -> dict[int | None, float | None]:
    """Median type size of the prose on each page."""
    sizes: dict[int | None, list[float]] = defaultdict(list)
    for block in blocks:
        size = getattr(block, "font_size", None)
        if size is None or _is_heading(block):
            continue
        if getattr(block, "unit_type", None) in (UnitType.PARAGRAPH, UnitType.LIST):
            sizes[getattr(block, "page", None)].append(float(size))
    return {page: statistics.median(values) for page, values in sizes.items()}


def _page_furniture(
    blocks: Sequence[_Block],
) -> tuple[set[str], dict[str, set[int]]]:
    """Heading texts that lead a logical page on several distinct pages."""
    pages: dict[str, set[int]] = defaultdict(set)
    seen: set[tuple[int | None, str | None]] = set()
    for block in blocks:
        key = (getattr(block, "page", None), getattr(block, "logical_page_side", None))
        if key in seen:
            continue
        seen.add(key)
        if _is_heading(block):
            pages[_normalised(block.text)].add(getattr(block, "page", None))
    furniture = {
        text
        for text, seen_pages in pages.items()
        if text and len(seen_pages) >= FURNITURE_MIN_PAGES
    }
    return furniture, pages
