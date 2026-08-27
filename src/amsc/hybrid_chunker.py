"""Structure-first chunking with one decision handed to the semantic signal.

Structure decides where sections begin; size constrains them; semantics only
arbitrates where size has forced a choice and structure has nothing to say.

Concretely this is :mod:`amsc.structural_chunker` with **exactly one rule
changed**. When a section is too large for one chunk, the structure-first
chunker walks its pieces and cuts when the next one would push the block past
``target_tokens`` -- that is, it takes the *last* admissible cut. This chunker
considers the *same* admissible cuts and takes the one with the highest semantic
shift instead.

Three things follow from "the same admissible cuts", and each of them is a
deliberate refusal to change a second thing at once:

* The window stays ``[min_tokens, target_tokens]``, the greedy rule's own
  window. Widening it to ``soft_max_tokens`` would be a size-rule change
  independent of the semantic argmax; measured on the frozen 2024 corpus it also
  buys almost nothing, moving the number of sections that have a real choice
  from 29 to 31 out of 42.
* There is no absolute threshold, only a local argmax. A global threshold does
  not work on this corpus -- the semantic signal separates gold boundaries from
  the rest at ROC-AUC 0.656, and the V4 line's ``semantic_floor`` of 0.12 sat
  above the largest shift the document contains (0.0976) and never fired.
  Ranking a handful of candidates inside one section is the job the signal can
  actually do.
* When candidates tie, the later cut wins -- which is the cut structure-only
  would have made. Where semantics is indifferent, behave like the baseline.

Nine of the 42 oversized sections in the frozen corpus offer no cut inside the
window at all. There the arbitration is switched off and the structure-first
greedy rule runs verbatim; ``h1_fallback_section_count`` counts those, so a flat
result can be read as "the signal was never asked" rather than "the signal said
nothing".

``diagnostics`` also carries ``arbitration_changed_boundary_count``: how often
the semantic choice actually differed from the greedy one. If that is zero the
report says so, in the manner of Phase 3B/3C's ``genuine_semantic_rescue = 0``.
The chunker is not adjusted to make it non-zero.

Passing ``arbitrate=False`` reduces this module to structure-first chunking, and
a test asserts it is then byte-identical to
:func:`amsc.structural_chunker.chunk_units` on the frozen corpus. That is what
keeps the section assembly shared here honest without editing the frozen module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

import numpy as np

from .models import RawDocumentUnit
from .structural_chunker import RENDER_SEPARATOR, Piece, Section, _render, _sections
from .tokenization import TokenCounter

TUNING_STATUS = "poc_initial_not_optimized"


class BoundaryEmbedder(Protocol):
    def embed_units(self, texts: Sequence[str]) -> Any: ...


@dataclass(frozen=True)
class HybridResult:
    chunks: list[dict[str, Any]]
    diagnostics: dict[str, Any]


@dataclass
class _Plan:
    """One section's cut positions, and how they were reached."""

    cuts: list[int] = field(default_factory=list)
    arbitrated: int = 0
    changed: int = 0
    fallback: bool = False
    candidates: int = 0


def _shifts(
    pieces: Sequence[Piece], embedder: BoundaryEmbedder, cache: dict[str, np.ndarray]
) -> list[float]:
    """Semantic shift at every internal boundary of one section.

    ``shifts[j]`` is the shift between ``pieces[j - 1]`` and ``pieces[j]``, so it
    indexes the same way a cut does. Vectors are L2-normalised by the boundary
    embedder, so the cosine is a dot product.
    """
    missing = [piece.text for piece in pieces if piece.text not in cache]
    if missing:
        wanted = list(dict.fromkeys(missing))
        vectors = np.asarray(embedder.embed_units(wanted).vectors, dtype=np.float64)
        for text, vector in zip(wanted, vectors):
            cache[text] = vector

    shifts = [0.0] * len(pieces)
    for index in range(1, len(pieces)):
        left = cache[pieces[index - 1].text]
        right = cache[pieces[index].text]
        shifts[index] = 1.0 - float(np.dot(left, right))
    return shifts


def _plan_cuts(
    pieces: Sequence[Piece],
    head_cost: int,
    *,
    min_tokens: int,
    target_tokens: int,
    shifts: Sequence[float] | None,
) -> _Plan:
    """Where to cut one oversized section.

    With ``shifts`` this is the semantic argmax over the admissible cuts; without
    it, the structure-first greedy rule -- the last admissible cut -- which is
    also the fallback when no cut is admissible.
    """
    plan = _Plan()
    totals = [0]
    for piece in pieces:
        totals.append(totals[-1] + piece.tokens)

    def size(start: int, stop: int) -> int:
        return head_cost + totals[stop] - totals[start]

    start = 0
    while start < len(pieces):
        if size(start, len(pieces)) <= target_tokens:
            break
        fits = [
            stop
            for stop in range(start + 1, len(pieces))
            if size(start, stop) <= target_tokens
        ]
        admissible = [stop for stop in fits if size(start, stop) >= min_tokens]
        # Greedy always takes the last cut that fits, and takes one piece when
        # nothing fits because a single piece is already over budget.
        greedy = max(fits, default=start + 1)
        if shifts is None or not admissible:
            chosen = greedy
            if shifts is not None:
                plan.fallback = True
        else:
            plan.arbitrated += 1
            plan.candidates += len(admissible)
            chosen = max(admissible, key=lambda stop: (shifts[stop], stop))
            if chosen != greedy:
                plan.changed += 1
        plan.cuts.append(chosen)
        start = chosen
    return plan


def chunk_units(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    boundary_embedder: BoundaryEmbedder | None = None,
    min_tokens: int = 160,
    target_tokens: int = 700,
    soft_max_tokens: int = 900,
    hard_max_tokens: int = 1126,
    arbitrate: bool = True,
    respect_semantic_roles: bool = False,
) -> HybridResult:
    if arbitrate and boundary_embedder is None:
        raise ValueError("Semantic arbitration needs a boundary embedder")

    sections = _sections(units, counter, hard_max_tokens, respect_semantic_roles)
    cache: dict[str, np.ndarray] = {}

    split_sections: list[Section] = []
    oversized = 0
    arbitrated_sections = 0
    arbitrated_boundaries = 0
    fallback_sections = 0
    changed = 0
    candidates = 0
    for section in sections:
        if section.tokens <= soft_max_tokens:
            split_sections.append(section)
            continue
        oversized += 1
        head_cost = counter.count(section.heading) + 2 if section.heading else 0
        shifts = (
            _shifts(section.pieces, boundary_embedder, cache)
            if arbitrate and boundary_embedder is not None
            else None
        )
        plan = _plan_cuts(
            section.pieces,
            head_cost,
            min_tokens=min_tokens,
            target_tokens=target_tokens,
            shifts=shifts,
        )
        if plan.arbitrated:
            arbitrated_sections += 1
            arbitrated_boundaries += plan.arbitrated
        if plan.fallback:
            fallback_sections += 1
        changed += plan.changed
        candidates += plan.candidates

        start = 0
        for stop in [*plan.cuts, len(section.pieces)]:
            if stop <= start:
                continue
            block = Section(section.heading, section.section_path)
            block.pieces.extend(section.pieces[start:stop])
            split_sections.append(block)
            start = stop

    # Undersized neighbours of the *same* section are rejoined. Only the blocks
    # a split produced may be rejoined: an explicit heading or a section_path
    # change starts a new section and its content is never pulled back into the
    # previous one. This mirrors structural_chunker exactly -- ``arbitrate=False``
    # is asserted byte-identical to it -- and on both KKB documents it fires zero
    # times, so nothing in the hybrid result depends on it.
    Block = tuple[str | None, list[Piece], tuple[str, ...]]
    groups: list[list[Block]] = []
    sizes: list[int] = []
    for section in split_sections:
        block: Block = (section.heading, section.pieces, section.section_path)
        size = section.tokens + (
            counter.count(section.heading) + 2 if section.heading else 0
        )
        same_section = bool(groups) and (
            groups[-1][-1][0] == section.heading
            and groups[-1][-1][2] == section.section_path
        )
        if (
            same_section
            and (sizes[-1] < min_tokens or size < min_tokens)
            and sizes[-1] + size <= target_tokens
        ):
            groups[-1].append(block)
            sizes[-1] += size
            continue
        groups.append([block])
        sizes.append(size)

    document_id = units[0].document_id
    chunks: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        text = RENDER_SEPARATOR.join(
            _render(heading, pieces) for heading, pieces, _ in group
        )
        tokens = counter.count(text)
        assert tokens <= hard_max_tokens, f"chunk {index} exceeds hard cap: {tokens}"
        pieces = [piece for _, block_pieces, _ in group for piece in block_pieces]
        paths: list[list[str]] = []
        for _, _, path in group:
            if path and list(path) not in paths:
                paths.append(list(path))
        chunks.append(
            {
                "chunk_id": f"{document_id}:h-chunk-{index:04d}",
                "text": text,
                "unit_ids": [piece.unit_id for piece in pieces],
                "token_count": tokens,
                "pages": sorted({p.page for p in pieces if p.page is not None}),
                "section_paths": paths,
                "heading": group[0][0],
                "split_strategies": sorted({piece.strategy for piece in pieces}),
            }
        )

    return HybridResult(
        chunks=chunks,
        diagnostics={
            "arbitration_enabled": arbitrate,
            "section_count": len(sections),
            "oversized_section_count": oversized,
            "arbitrated_section_count": arbitrated_sections,
            "h1_fallback_section_count": fallback_sections,
            "arbitrated_boundary_count": arbitrated_boundaries,
            "arbitration_changed_boundary_count": changed,
            "admissible_candidate_total": candidates,
            "embedded_piece_count": len(cache),
            "window": [min_tokens, target_tokens],
            "tuning_status": TUNING_STATUS,
        },
    )
