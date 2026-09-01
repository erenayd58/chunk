"""Context assembly: from ranked chunks to what the answer model reads.

The retrieval unit and the generation context are different things. A hit
is one chunk; the passage a reader would want beside it is that chunk plus
the adjacent parts of the same section that a token budget cut away. The
expansion is :func:`amsc.chunk_relations.expand_context` -- it walks only
``TOKEN_BUDGET_CONTINUATION`` links, so a section change or a label seam is
a hard stop and nothing from another topic is pulled in on a size pretext.

Rules, in order:

1. Hits are taken in rank order; each is expanded within ``expansion_budget``.
2. Overlapping expansions are merged (they are contiguous by construction).
3. Groups are added to the context in the order of their best hit until
   ``max_context_tokens`` is spent; a group that does not fit falls back to
   its seed chunk alone, and a seed that does not fit is dropped and
   recorded, never silently truncated mid-chunk.
4. Every chunk appears once, with a stable source label ``S1..Sn`` in
   context order, so a citation in the answer maps back to exactly one
   chunk, one heading and one page list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .chunk_relations import derive_continuations, expand_context
from .rag_index import IndexedChunk
from .retrieval_pipeline import RetrievalHit
from .table_view import CONTEXT_HEADER

_counter: Any = None


def _count(text: str) -> int:
    """cl100k tokens -- the chunker's own counter; words if tiktoken is absent."""
    global _counter
    if _counter is None:
        try:
            from .tokenization import TiktokenTokenCounter

            _counter = TiktokenTokenCounter("cl100k_base")
        except Exception:  # pragma: no cover - tiktoken is a hard dependency
            _counter = False
    return int(_counter.count(text)) if _counter else max(1, len(text.split()))


def _context_tokens(chunk: IndexedChunk) -> int:
    """What one chunk costs the context budget.

    Its own tokens, plus the table reading when it carries one: the budget
    pays for what is actually rendered, so a reading cannot slip past the
    limit. A chunk with no reading -- every Markdown and Standard chunk, and
    every table Deep could not read with certainty -- costs exactly what it
    always did.
    """
    if not chunk.table_view:
        return chunk.token_count
    return chunk.token_count + _count(CONTEXT_HEADER + "\n" + chunk.table_view)


@dataclass(frozen=True)
class ContextSettings:
    max_context_tokens: int = 3200
    expansion_enabled: bool = True
    expansion_budget: int = 1126
    max_sources: int = 8

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any] | None) -> "ContextSettings":
        config = dict(config or {})
        expansion = dict(config.pop("expansion", {}) or {})
        known = {k: v for k, v in config.items() if k in cls.__dataclass_fields__}
        if "enabled" in expansion:
            known["expansion_enabled"] = bool(expansion["enabled"])
        if "max_total_tokens" in expansion:
            known["expansion_budget"] = int(expansion["max_total_tokens"])
        return cls(**known)


@dataclass
class ContextBlock:
    label: str
    chunk_id: str
    index: int
    text: str
    token_count: int
    heading: str | None
    section_path: tuple[str, ...]
    pages: tuple[int, ...]
    role: str  # hit | neighbour_before | neighbour_after
    seed_chunk_id: str
    rank: int | None
    dense_rank: int | None = None
    bm25_rank: int | None = None
    rrf_score: float | None = None
    #: The chunk's table reading, rendered beneath ``text`` and never into it.
    #: ``token_count`` above stays the chunk's own, which is what the source
    #: payload and every citation report; the reading's cost is counted in the
    #: context's ``total_tokens``.
    table_view: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "chunk_id": self.chunk_id,
            "index": self.index,
            "token_count": self.token_count,
            "heading": self.heading,
            "section_path": list(self.section_path),
            "pages": list(self.pages),
            "role": self.role,
            "seed_chunk_id": self.seed_chunk_id,
            "rank": self.rank,
            "dense_rank": self.dense_rank,
            "bm25_rank": self.bm25_rank,
            "rrf_score": self.rrf_score,
        }


@dataclass
class AssembledContext:
    blocks: list[ContextBlock]
    total_tokens: int
    budget: int
    groups: list[list[str]] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    expansion_stops: dict[str, dict[str, str]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "budget": self.budget,
            "block_count": len(self.blocks),
            "groups": self.groups,
            "dropped": self.dropped,
            "expansion_stops": self.expansion_stops,
        }

    def render(self) -> str:
        """The text the answer model reads: labelled blocks in context order."""
        parts: list[str] = []
        for block in self.blocks:
            where = []
            if block.section_path:
                where.append(" › ".join(block.section_path))
            if block.pages:
                where.append("sayfa " + ", ".join(str(p) for p in block.pages))
            header = f"[{block.label}]" + (f" ({'; '.join(where)})" if where else "")
            body = block.text.strip()
            if block.table_view:
                # Beneath the document's own table, and saying what it is.
                body += "\n\n" + CONTEXT_HEADER + "\n" + block.table_view
            parts.append(f"{header}\n{body}")
        return "\n\n".join(parts)


def assemble_context(
    hits: Sequence[RetrievalHit],
    chunks: Sequence[IndexedChunk],
    *,
    kind: str,
    settings: ContextSettings = ContextSettings(),
) -> AssembledContext:
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    rows = [
        {
            "chunk_id": chunk.chunk_id,
            "unit_ids": list(chunk.unit_ids),
            "token_count": chunk.token_count,
            "heading": chunk.heading,
            "section_paths": [list(chunk.section_path)] if chunk.section_path else [],
            "pages": list(chunk.pages),
        }
        for chunk in chunks
    ]
    links = derive_continuations(rows, kind=kind) if settings.expansion_enabled else []

    # 1-2. expand each hit, merge overlapping expansions
    groups: list[dict[str, Any]] = []
    stops: dict[str, dict[str, str]] = {}
    for hit in hits[: settings.max_sources]:
        expansion = expand_context(
            hit.chunk_id,
            chunks=rows,
            links=links,
            max_total_tokens=settings.expansion_budget,
            enabled=settings.expansion_enabled,
        )
        stops[hit.chunk_id] = dict(expansion.stopped)
        members = [by_id[c].index for c in expansion.chunk_ids]
        merged = False
        for group in groups:
            if set(group["members"]) & set(members):
                group["members"] = sorted(set(group["members"]) | set(members))
                group["hits"].append(hit)
                merged = True
                break
        if not merged:
            groups.append({"members": sorted(members), "hits": [hit], "seed": hit.chunk_id})

    # 3. spend the budget in rank order
    blocks: list[ContextBlock] = []
    dropped: list[dict[str, Any]] = []
    total = 0
    kept_groups: list[list[str]] = []
    for group in groups:
        seed_hit = group["hits"][0]
        members = group["members"]
        cost = sum(_context_tokens(chunks[i]) for i in members)
        if total + cost > settings.max_context_tokens:
            seed_index = by_id[seed_hit.chunk_id].index
            seed_cost = _context_tokens(chunks[seed_index])
            if total + seed_cost > settings.max_context_tokens:
                dropped.append({"chunk_id": seed_hit.chunk_id, "rank": seed_hit.rank, "reason": "budget"})
                continue
            dropped.extend(
                {"chunk_id": chunks[i].chunk_id, "rank": None, "reason": "expansion_budget"}
                for i in members
                if i != seed_index
            )
            members = [seed_index]
            cost = seed_cost
        total += cost
        hit_by_id = {hit.chunk_id: hit for hit in group["hits"]}
        seed_index = by_id[seed_hit.chunk_id].index
        group_ids: list[str] = []
        for index in members:
            chunk = chunks[index]
            hit = hit_by_id.get(chunk.chunk_id)
            role = "hit" if hit else ("neighbour_before" if index < seed_index else "neighbour_after")
            blocks.append(
                ContextBlock(
                    label="",
                    chunk_id=chunk.chunk_id,
                    index=chunk.index,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    heading=chunk.heading,
                    section_path=chunk.section_path,
                    pages=chunk.pages,
                    role=role,
                    seed_chunk_id=seed_hit.chunk_id,
                    table_view=chunk.table_view,
                    rank=hit.rank if hit else None,
                    dense_rank=hit.dense_rank if hit else None,
                    bm25_rank=hit.bm25_rank if hit else None,
                    rrf_score=round(hit.rrf_score, 6) if hit else None,
                )
            )
            group_ids.append(chunk.chunk_id)
        kept_groups.append(group_ids)

    # 4. stable labels in context order
    for number, block in enumerate(blocks, start=1):
        block.label = f"S{number}"
    return AssembledContext(
        blocks=blocks,
        total_tokens=total,
        budget=settings.max_context_tokens,
        groups=kept_groups,
        dropped=dropped,
        expansion_stops=stops,
    )
