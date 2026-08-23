"""Small-to-big retrieval: index small chunks, return their parent context.

Segmentation is not touched. Parents are built deterministically from the
existing chunk sequence by grouping consecutive chunks up to a token budget,
so a hit on a small, lexically thin chunk comes back with the neighbouring
content a reader needs, and several small chunks from the same region collapse
into one result instead of competing for the top slots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Parent:
    parent_id: str
    chunk_ids: tuple[str, ...]
    unit_ids: tuple[str, ...]
    token_count: int
    pages: tuple[int, ...]


def build_parents(
    chunks: Sequence[Mapping],
    *,
    max_tokens: int = 1126,
) -> tuple[list[Parent], dict[str, str]]:
    """Group consecutive chunks into parents bounded by ``max_tokens``.

    Returns the parents and a ``chunk_id -> parent_id`` map. Grouping is purely
    positional, so it is deterministic and independent of any query.
    """
    parents: list[Parent] = []
    by_chunk: dict[str, str] = {}
    current: list[Mapping] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if not current:
            return
        parent_id = f"parent-{len(parents) + 1:04d}"
        unit_ids: list[str] = []
        pages: set[int] = set()
        for chunk in current:
            unit_ids.extend(chunk["unit_ids"])
            pages.update(chunk.get("pages") or [])
            by_chunk[str(chunk["chunk_id"])] = parent_id
        parents.append(
            Parent(
                parent_id=parent_id,
                chunk_ids=tuple(str(c["chunk_id"]) for c in current),
                unit_ids=tuple(unit_ids),
                token_count=current_tokens,
                pages=tuple(sorted(pages)),
            )
        )
        current = []
        current_tokens = 0

    for chunk in chunks:
        tokens = int(chunk["token_count"])
        if current and current_tokens + tokens > max_tokens:
            flush()
        current.append(chunk)
        current_tokens += tokens
    flush()
    return parents, by_chunk


def expand_hits(
    hits: Sequence,
    chunk_to_parent: Mapping[str, str],
    *,
    top_k: int,
) -> list[tuple[str, int]]:
    """Collapse ranked child hits into ranked parents, best child rank wins.

    Returns ``(parent_id, rank)`` pairs, rank starting at 1.
    """
    seen: list[str] = []
    for hit in hits:
        parent_id = chunk_to_parent.get(hit.chunk_id)
        if parent_id is not None and parent_id not in seen:
            seen.append(parent_id)
        if len(seen) >= top_k:
            break
    return [(parent_id, rank) for rank, parent_id in enumerate(seen, start=1)]
