"""Token-budget continuation links over frozen chunks, and local expansion.

A section larger than the token budget leaves the chunker as several adjacent
chunks that a reader would treat as one passage. This module records that fact
as a **derived relationship layer** over the frozen ``chunks.jsonl`` -- the
chunks themselves are never modified, re-merged or re-scored -- and offers a
post-retrieval **local context expander** that walks those links under a hard
token budget.

Adjacent same-section pairs (same heading, section paths joining seamlessly)
form the continuation family, and the relation type states what the boundary
between them observably is:

    TOKEN_BUDGET_CONTINUATION
        the boundary is a plain size cut (``budget_split``): the section ran
        past the target budget and was cut at an arbitrary piece. Only this
        type carries "the reader would not have stopped here", so only this
        type is walked by the automatic local expansion.

    SECTION_LABEL_CONTINUATION
        the same section continues, but the cut landed on a reader-visible
        label seam (``label_split``). Recorded, not auto-expanded.

    MARKDOWN_SPLIT_CONTINUATION
        the size-first markdown splitter's cut inside one section
        (``md_overlap`` / ``md_size`` / ``md_heading``). Recorded, not
        auto-expanded.

Nothing else is related. Non-adjacent chunks are never linked, no similarity
is estimated, and a boundary where the section actually changes is a hard stop
-- which is exactly what makes the expansion safe to run blindly after
retrieval: it can only re-assemble what one section's size split took apart.

One honesty note on the hybrid arm: its ``budget_split`` boundaries exist for
the same reason as structure-only's (the section exceeded the budget), but the
cut *position* may have been chosen by the semantic arbitration and the
artifacts do not record which. Each link therefore carries ``cut_position``:
``greedy`` for structure-first, ``not_recorded_greedy_or_arbitrated`` for the
hybrid arm. No link ever claims a boundary was semantically chosen.

Determinism: links depend only on the chunk rows, in their frozen order. The
expander is a pure function of (links, seed, budget) with a fixed
nearest-first, previous-before-next visiting order.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

TOKEN_BUDGET_CONTINUATION = "TOKEN_BUDGET_CONTINUATION"
SECTION_LABEL_CONTINUATION = "SECTION_LABEL_CONTINUATION"
MARKDOWN_SPLIT_CONTINUATION = "MARKDOWN_SPLIT_CONTINUATION"

#: boundary_reason -> relation type. The narrowing lives here: only a plain
#: budget cut earns TOKEN_BUDGET_CONTINUATION.
RELATION_TYPE_BY_REASON = {
    "budget_split": TOKEN_BUDGET_CONTINUATION,
    "label_split": SECTION_LABEL_CONTINUATION,
    "md_overlap": MARKDOWN_SPLIT_CONTINUATION,
    "md_size": MARKDOWN_SPLIT_CONTINUATION,
    "md_heading": MARKDOWN_SPLIT_CONTINUATION,
}


def _base(unit_id: str) -> str:
    return unit_id.split("#", 1)[0]


def _first_path(chunk: Mapping[str, Any]) -> list[str] | None:
    paths = chunk.get("section_paths") or []
    return paths[0] if paths else None


def _last_path(chunk: Mapping[str, Any]) -> list[str] | None:
    paths = chunk.get("section_paths") or []
    return paths[-1] if paths else None


def continuation_boundary_reason(
    kind: str, left: Mapping[str, Any], right: Mapping[str, Any]
) -> str:
    """The observable reason for the boundary between two linked chunks."""
    first = right["unit_ids"][0] if right["unit_ids"] else ""
    if kind == "markdown_recursive":
        overlap = {_base(u) for u in left["unit_ids"]} & {
            _base(u) for u in right["unit_ids"]
        }
        if overlap:
            return "md_overlap"
        return "md_heading" if _base(first).startswith("h-") else "md_size"
    return "label_split" if _base(first).startswith("h-") else "budget_split"


def derive_continuations(
    chunks: Sequence[Mapping[str, Any]],
    *,
    kind: str,
    document_id: str | None = None,
    canonical_sha256: str | None = None,
    chunks_sha256: str | None = None,
) -> list[dict[str, Any]]:
    """The TOKEN_BUDGET_CONTINUATION links of one arm's frozen chunks.

    One record per **adjacent** pair whose heading is byte-identical and whose
    section paths join (the left chunk's last path equals the right chunk's
    first path, non-empty). That is the exact grouping key the structure-first
    splitter uses when it cuts an oversized section, so a link asserts "these
    two are parts of one section" and nothing more. A pair that fails the test
    -- including the same chapter re-opened under a typographically different
    banner -- is not linked; strictness is the point.
    """
    links: list[dict[str, Any]] = []
    for index in range(1, len(chunks)):
        left, right = chunks[index - 1], chunks[index]
        joined = _last_path(left)
        if not joined or joined != _first_path(right):
            continue
        if left.get("heading") != right.get("heading"):
            continue
        reason = continuation_boundary_reason(kind, left, right)
        links.append(
            {
                "relation_type": RELATION_TYPE_BY_REASON[reason],
                "from_chunk": left["chunk_id"],
                "to_chunk": right["chunk_id"],
                "from_index": index - 1,
                "to_index": index,
                "same_section": True,
                "boundary_reason": reason,
                "section_path": list(joined),
                "heading": left.get("heading"),
                "pages": sorted(
                    set(left.get("pages") or []) | set(right.get("pages") or [])
                ),
                "span": {
                    "from_pages": list(left.get("pages") or []),
                    "to_pages": list(right.get("pages") or []),
                },
                "arm_kind": kind,
                "cut_position": (
                    "not_recorded_greedy_or_arbitrated"
                    if kind == "hybrid_h1" and reason == "budget_split"
                    else "greedy"
                ),
                **({"document_id": document_id} if document_id else {}),
                **({"canonical_sha256": canonical_sha256} if canonical_sha256 else {}),
                **({"chunks_sha256": chunks_sha256} if chunks_sha256 else {}),
            }
        )
    return links


def continuation_groups(
    chunk_count: int, links: Sequence[Mapping[str, Any]]
) -> list[int | None]:
    """Group id per chunk index: maximal runs joined by continuation links.

    A chunk in no link gets ``None`` -- it stands alone and expansion at it
    returns only itself.
    """
    groups: list[int | None] = [None] * chunk_count
    group = -1
    for link in links:
        left, right = link["from_index"], link["to_index"]
        if groups[left] is None:
            group += 1
            groups[left] = group
        groups[right] = groups[left]
    return groups


@dataclass(frozen=True)
class ExpansionResult:
    """A post-retrieval context candidate: the seed plus rejoined neighbours.

    ``chunk_ids`` is in document order and always contains the seed. The
    expander never re-ranks anything: it takes one retrieved chunk and answers
    "which adjacent parts of the same section still fit in the budget".
    """

    seed: str
    chunk_ids: list[str] = field(default_factory=list)
    added_before: list[str] = field(default_factory=list)
    added_after: list[str] = field(default_factory=list)
    total_tokens: int = 0
    budget: int | None = None
    stopped: dict[str, str] = field(default_factory=dict)


def expand_context(
    seed_chunk_id: str,
    *,
    chunks: Sequence[Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
    max_total_tokens: int,
    max_neighbors_each_side: int | None = None,
    enabled: bool = True,
) -> ExpansionResult:
    """Local context expansion around one retrieved chunk.

    Deterministic rules, applied in order:

    * ``enabled=False`` returns the seed untouched -- the layer is a switch,
      not a default.
    * **Only TOKEN_BUDGET_CONTINUATION links are walked.** A section change is
      a hard stop by construction; so is a same-section boundary of any other
      type (a label seam, a markdown cut) -- those stop with
      ``non_budget_boundary`` rather than being silently crossed.
    * Neighbours are considered nearest-first, previous before next, and a
      side stops at the first neighbour that does not fit -- the result is
      always contiguous, in document order, without duplicates.
    * ``max_total_tokens`` is a hard budget over ``token_count`` sums,
      including the seed. A seed already over budget is returned alone.
    """
    index_of = {chunk["chunk_id"]: i for i, chunk in enumerate(chunks)}
    if seed_chunk_id not in index_of:
        raise ValueError(f"unknown chunk id {seed_chunk_id!r}")
    seed_index = index_of[seed_chunk_id]
    seed_tokens = int(chunks[seed_index]["token_count"])

    if not enabled:
        return ExpansionResult(
            seed=seed_chunk_id,
            chunk_ids=[seed_chunk_id],
            total_tokens=seed_tokens,
            budget=max_total_tokens,
            stopped={"expansion": "disabled"},
        )

    budget_links = [
        link for link in links
        if link.get("relation_type") == TOKEN_BUDGET_CONTINUATION
    ]
    forward = {link["from_index"]: link["to_index"] for link in budget_links}
    backward = {link["to_index"]: link["from_index"] for link in budget_links}
    other_forward = {
        link["from_index"] for link in links
        if link.get("relation_type") != TOKEN_BUDGET_CONTINUATION
    }
    other_backward = {
        link["to_index"] for link in links
        if link.get("relation_type") != TOKEN_BUDGET_CONTINUATION
    }

    chosen = [seed_index]
    total = seed_tokens
    stopped: dict[str, str] = {}
    cursors = {"before": seed_index, "after": seed_index}
    steps = {"before": 0, "after": 0}

    def try_side(side: str) -> bool:
        nonlocal total
        if side in stopped:
            return False
        if max_neighbors_each_side is not None and steps[side] >= max_neighbors_each_side:
            stopped[side] = "neighbor_limit"
            return False
        neighbour = (
            backward.get(cursors[side]) if side == "before" else forward.get(cursors[side])
        )
        if neighbour is None:
            blocked_by_other = (
                cursors[side] in other_backward
                if side == "before"
                else cursors[side] in other_forward
            )
            stopped[side] = "non_budget_boundary" if blocked_by_other else "section_boundary"
            return False
        tokens = int(chunks[neighbour]["token_count"])
        if total + tokens > max_total_tokens:
            stopped[side] = "budget"
            return False
        chosen.append(neighbour)
        total += tokens
        cursors[side] = neighbour
        steps[side] += 1
        return True

    while len(stopped) < 2:
        progressed = try_side("before")
        progressed = try_side("after") or progressed
        if not progressed:
            break

    ordered = sorted(set(chosen))
    return ExpansionResult(
        seed=seed_chunk_id,
        chunk_ids=[chunks[i]["chunk_id"] for i in ordered],
        added_before=[chunks[i]["chunk_id"] for i in ordered if i < seed_index],
        added_after=[chunks[i]["chunk_id"] for i in ordered if i > seed_index],
        total_tokens=total,
        budget=max_total_tokens,
        stopped=stopped,
    )


# --------------------------------------------------------------------------
# sidecar derivation over a frozen benchmark tree
# --------------------------------------------------------------------------

ARMS = ("markdown", "hybrid", "structure-only")


def derive_tree(benchmark_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Write continuation sidecars for every arm of one frozen benchmark tree.

    Reads the tree strictly read-only; refuses to write into the tree itself
    or under ``evaluation/``. Returns a summary that is also written as JSON.
    """
    benchmark_dir, output_dir = Path(benchmark_dir), Path(output_dir)
    resolved = output_dir.resolve()
    if benchmark_dir.resolve() in (resolved, *resolved.parents):
        raise ValueError("refusing to write sidecars into the frozen benchmark tree")
    if "evaluation" in output_dir.parts:
        raise ValueError("refusing to write into evaluation/ (frozen)")

    config = json.loads(
        (benchmark_dir / "resolved-config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((benchmark_dir / "manifest.json").read_text(encoding="utf-8"))
    document_id = benchmark_dir.name

    summary: dict[str, Any] = {
        "document_id": document_id,
        "auto_expansion_walks": TOKEN_BUDGET_CONTINUATION,
        "canonical_sha256": manifest.get("canonical_sha256"),
        "arms": {},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for arm in ARMS:
        chunks = [
            json.loads(line)
            for line in (benchmark_dir / arm / "chunks.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        links = derive_continuations(
            chunks,
            kind=config["arms"][arm]["kind"],
            document_id=document_id,
            canonical_sha256=manifest.get("canonical_sha256"),
            chunks_sha256=(manifest.get("arm_chunk_sha256") or {}).get(arm),
        )
        sidecar = output_dir / f"{arm}.continuations.jsonl"
        sidecar.write_text(
            "".join(
                json.dumps(link, ensure_ascii=False, sort_keys=True) + "\n"
                for link in links
            ),
            encoding="utf-8",
            newline="\n",
        )
        groups = continuation_groups(len(chunks), links)
        group_sizes: dict[int, int] = {}
        for gid in groups:
            if gid is not None:
                group_sizes[gid] = group_sizes.get(gid, 0) + 1
        summary["arms"][arm] = {
            "chunk_count": len(chunks),
            "link_count": len(links),
            "relation_types": {
                relation: sum(1 for l in links if l["relation_type"] == relation)
                for relation in sorted({l["relation_type"] for l in links})
            },
            "chunks_in_groups": sum(1 for g in groups if g is not None),
            "group_count": len(group_sizes),
            "largest_group": max(group_sizes.values(), default=0),
            "boundary_reasons": {
                reason: sum(1 for l in links if l["boundary_reason"] == reason)
                for reason in sorted({l["boundary_reason"] for l in links})
            },
            "sidecar": sidecar.name,
        }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.chunk_relations",
        description=(
            "Derive TOKEN_BUDGET_CONTINUATION sidecars from a frozen "
            "chunk-benchmark tree (read-only)"
        ),
    )
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    summary = derive_tree(args.benchmark, args.output)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
