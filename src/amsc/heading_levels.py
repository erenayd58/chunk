"""Give a heading the level its typography already implies.

``heading_level`` currently arrives as the number of ``#`` characters
PyMuPDF4LLM wrote, and its layout backend writes ``##`` for *every*
``section-header`` box whatever its size. So a chapter title, the year label
grouping the entries beneath it and the bold card title under that all reach
:class:`~amsc.checkpoint_adapter.SectionHierarchyBuilder` at the same level --
and that builder keeps only the headings *shallower* than the one it is
looking at. Same level means each heading evicts the one before it, so every
unit's ``section_path`` ends up one element long: the leaf, never its parents.
A note filed under ``2.4 Onemli muhasebe politikalari`` inside
``2. FINANSAL TABLOLARIN SUNUMUNA ILISKIN ESASLAR`` keeps neither.

The signal used here is relative and text-agnostic: **a heading set in larger
type than the heading before it cannot be its child.** Nothing is compared
against an absolute point size, so a document that mixes typographic systems --
a designed front section in one family, financial notes in another -- is still
ordered correctly inside each of them: what matters is only whether the nearest
enclosing heading was set larger.

Within one size, section numbering breaks the tie: ``2.`` encloses ``2.4``,
which encloses an unnumbered sub-title. That is the same shape-only rule
:mod:`amsc.numbered_headings` already uses -- a digit run closed by its own
terminator -- and it matches no document, title or number by name.

One further signal is not typography either. A heading the role pass called a
**key** (:class:`~amsc.models.SemanticRole.GROUP`) partitions the section it
sits in rather than titling anything of its own, and two keys of one partition
are siblings however each of them is printed. Without that, a timeline whose
year labels are set at four different sizes reads as four levels of nesting and
every entry loses the year it belongs to. Only a key's *own* prominence is
rewritten, and only while a run of keys is open.

Three properties keep this safe to switch on:

  * levels are assigned **relative to the document's own shallowest heading**,
    so a corpus whose headings really are all one tier keeps exactly the levels
    it had. On such a document the pass is byte-identical to not running at all.
  * a heading whose type size could not be measured inherits the prominence of
    the heading before it, becoming its sibling rather than inventing a tier.
  * the level never leaves the range the canonical schema allows: a document
    with more tiers than Markdown has merges everything below the sixth into
    it instead of failing validation, so what it gives up is the tail of the
    tree and never the chapter a paragraph sits under.

This is opt-in. Callers that do not ask for it get the untouched block stream.
"""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Sequence, TypeVar

from .models import SemanticRole

_Block = TypeVar("_Block")

_EMPHASIS = re.compile(r"^[*_]+|[*_]+$")
#: Section numbering opening a title. A single number must be closed by its own
#: terminator -- that is what separates ``9. MADDI DURAN VARLIKLAR`` from
#: ``2024 Findeks Verileri`` -- while a multi-part number needs none, because
#: ``2.4 Onemli politikalar`` is printed without a trailing dot in practice.
#: Every part after the first is capped at two digits so a Turkish thousands
#: separator (``1.300 potansiyel sorun``) is not read as a section number.
_NUMBERING = re.compile(r"^(?:(\d+(?:\.\d{1,2})+)\.?|(\d+)[.)])\s+\S")
#: A key printed as a dotted number, ``2.4`` inside ``2``. Components after the
#: first are capped at two digits for the same reason the numbering pattern
#: caps them: ``1.300`` is a thousands separator, not a nested key.
_NESTED_KEY = re.compile(r"^\d+(?:\.\d{1,2})+$")
#: Type sizes are compared at this resolution. Two headings whose measured size
#: differs by less than a rounding step are the same tier, not two tiers.
SIZE_RESOLUTION = 0.5

#: Prominence rank of an unnumbered heading, below every numbering depth. A
#: numbered title encloses the unnumbered sub-titles printed under it.
_UNNUMBERED = -99

#: ``RawDocumentUnit.heading_level`` is bounded by the six levels Markdown has.
#: A document with more typographic tiers than that must merge some of them,
#: and which ones it merges decides what survives in ``section_path``.
#:
#: Everything below the cap is merged into it, so the tiers nearest the root
#: each keep a level of their own and the tail becomes one bucket. That is the
#: right direction only because two other things already hold: display type is
#: not allowed to out-rank the chapter it sits under (see
#: :func:`_clamped_prominences`), and a heading that does not bear hierarchy
#: never reaches the stack at all. Without those, chapters sat *in* the tail and
#: merging there evicted them -- which is why an earlier version of this module
#: merged at the shallow end instead. Measured on KKB 2024 with both in place,
#: merging the tail keeps 63.6% of content units naming their chapter and
#: merging the head keeps 48.1%. On KKB 2022 the two are identical: no path
#: there is deep enough for the cap to bite.
MAX_HEADING_LEVEL = 6


def _numbering_rank(text: str) -> int:
    """``-depth`` for a numbered title, or the unnumbered floor."""
    inner = _EMPHASIS.sub("", text.strip()).strip()
    match = _NUMBERING.match(inner)
    if match is None:
        return _UNNUMBERED
    return -len((match.group(1) or match.group(2)).split("."))


def _key_depth(text: str) -> int:
    """How deep a key sits: ``2014`` is one part, ``2.4`` is two."""
    inner = _EMPHASIS.sub("", text.strip()).strip()
    if _NESTED_KEY.fullmatch(inner):
        return len(inner.split("."))
    return 1


def _prominence(block: _Block) -> tuple[float, int] | None:
    """How enclosing this heading is. Larger sorts first. ``None`` if unknown."""
    size = getattr(block, "font_size", None)
    if size is None:
        return None
    quantised = round(float(size) / SIZE_RESOLUTION) * SIZE_RESOLUTION
    return (quantised, _numbering_rank(block.text))


def _bears_hierarchy(block: _Block) -> bool:
    """Whether this heading may touch the section stack.

    ``None`` means the role pass never ran, and every heading opens a section
    exactly as it did before roles existed.
    """
    return getattr(block, "opens_section", None) is not False


def _clamped_prominences(blocks: Sequence[_Block]) -> dict[int, tuple[float, int]]:
    """Prominence per heading, with unnumbered type held under its chapter.

    A standfirst is routinely set larger than the chapter title it sits under.
    Read literally that makes the chapter its child, and the chapter then falls
    out of every ``section_path`` below. Numbering is the document's own
    statement of structure, so an unnumbered heading is never allowed to
    out-rank the numbered heading enclosing it -- it is placed one step below
    instead. Without it the chapter falls out of the path of every unit under
    a standfirst, which on KKB 2024 is most of the designed front section.

    One more thing is not typography: a **key partitions the section it sits
    in**, so two keys of one partition are siblings however each is printed. A
    timeline sets its year labels at whatever size the layout wanted, and read
    as sizes alone ``2009`` becomes a child of ``1995`` and every entry under
    it loses the year it belongs to. The run is closed by the next heading that
    is not a key, and a key printed deeper than the one that opened the run --
    ``2.4`` under ``2`` -- keeps its own tier, because that is the document
    stating the nesting rather than the layout implying it.
    """
    out: dict[int, tuple[float, int]] = {}
    ceiling: float | None = None
    ceiling_rank: int | None = None
    previous: tuple[float, int] | None = None
    # The key that opened the run of keys currently partitioning a section, and
    # how deep that key is printed.
    key_run: tuple[float, int] | None = None
    key_run_depth: int | None = None
    for block in blocks:
        if block.heading_level is None or not _bears_hierarchy(block):
            continue
        prominence = _prominence(block)
        if prominence is None:
            prominence = previous if previous is not None else (0.0, _UNNUMBERED)
        size, rank = prominence
        if rank == _UNNUMBERED:
            if ceiling is not None and size >= ceiling:
                size = ceiling - SIZE_RESOLUTION
        else:
            # Two numbered headings at the same numbering depth are siblings
            # whatever size they are printed at. ``29.`` reaches this corpus
            # merged with its standfirst and set at 40pt while ``30.`` is set at
            # 20pt; read as sizes that makes chapter 30 a child of chapter 29.
            if ceiling is not None and ceiling_rank is not None and rank >= ceiling_rank:
                size = ceiling
            ceiling, ceiling_rank = size, rank
        prominence = (size, rank)
        if getattr(block, "semantic_role", None) == SemanticRole.GROUP:
            depth = _key_depth(block.text)
            if key_run is not None and depth <= key_run_depth:
                prominence = key_run
            else:
                key_run, key_run_depth = prominence, depth
        else:
            key_run, key_run_depth = None, None
        out[id(block)] = prominence
        previous = prominence
    return out


def assign_heading_levels(
    blocks: Sequence[_Block],
) -> tuple[list[_Block], dict[int, int]]:
    """Rewrite every heading's level from the prominence of its neighbours.

    Returns the rewritten blocks and a ``{level: count}`` census, so the
    decision stays auditable rather than silent.
    """

    levels = [
        block.heading_level
        for block in blocks
        if block.heading_level is not None
    ]
    if not levels:
        return list(blocks), {}
    # Levels are relative to the tier the document already uses for its
    # shallowest heading. Keeping that origin is what makes a genuinely flat
    # document come out unchanged.
    base_level = min(levels)

    depths = _nesting_depths(blocks)
    measured = [depth for depth in depths if depth is not None]
    if not measured:
        return list(blocks), {}

    rewritten: list[_Block] = []
    census: dict[int, int] = {}
    depth_iterator = iter(depths)
    for block in blocks:
        depth = next(depth_iterator)
        if depth is None:
            rewritten.append(block)
            continue
        level = min(base_level + depth, MAX_HEADING_LEVEL)
        census[level] = census.get(level, 0) + 1
        rewritten.append(replace(block, heading_level=level))

    return rewritten, census


def _nesting_depths(blocks: Sequence[_Block]) -> list[int | None]:
    """How many headings enclose each one, or ``None`` for a non-heading.

    Only a heading that bears hierarchy is allowed on the stack. One that does
    not still needs a level, because the canonical schema requires one of every
    heading; it is given the depth of the section it sits in plus one, and
    never affects where anything else lands.
    """
    prominences = _clamped_prominences(blocks)
    # Prominences of the headings currently enclosing the one being read,
    # strictly decreasing from the outermost.
    stack: list[tuple[float, int]] = []
    depths: list[int | None] = []
    open_depth = 0

    for block in blocks:
        if block.heading_level is None:
            depths.append(None)
            continue
        if not _bears_hierarchy(block):
            depths.append(open_depth)
            continue
        prominence = prominences[id(block)]
        while stack and stack[-1] <= prominence:
            stack.pop()
        depths.append(len(stack))
        stack.append(prominence)
        open_depth = len(stack)

    return depths
