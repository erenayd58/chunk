"""Viewer v2 -- a presentation-grade, self-contained HTML over frozen benchmark output.

Reads one or more completed ``amsc.chunk_benchmark`` output trees (the frozen
``artifacts/chunk-benchmark-v5`` generation) plus the pinned canonical each tree
names, and emits a single offline HTML file with four modes:

* **Sunum** (default) -- the document rendered for a non-technical reader, with
  chunk boundaries and a human-language reason at each boundary.
* **Sorgu** -- one gold query across the three arms: rank, hit status, the
  retrieved chunk with the gold evidence highlighted.
* **Debug** -- the full technical surface: unit ids, roles, section paths,
  mapping segments and methods, fragment ids.
* **Benchmark** -- the final retrieval / structural / timing numbers, read from
  the artifacts rather than restated.

Nothing is recomputed and nothing upstream is touched: the module is a pure
reader. Chunk text is not embedded; it is reconstructed from the canonical unit
texts through the mapping segments, so the file stays small and cannot drift
from the canonical.

Every derived value is deterministic. **Boundary reasons** are restricted to
what the artifacts actually record: a section change, a label seam, a size
split, a markdown overlap. Per-boundary semantic-arbitration attribution is
*not* recorded by the benchmark, so hybrid boundaries are never labelled as
semantically chosen; the aggregate arbitration counts are shown at arm level
instead. **The differences filter** is defined over consecutive content units
(headings excluded, because two arms leave them out of ``unit_ids``): a pair is
a difference point when the three arms disagree on whether a chunk boundary
falls between the two units, membership being the first chunk that contains the
unit. Pairs where any arm has no membership for either unit are skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .chunk_relations import continuation_groups, derive_continuations

ARM_ORDER = ("markdown", "hybrid", "structure-only")

ARM_LABELS = {
    "markdown": "Markdown",
    "hybrid": "Hybrid",
    "structure-only": "Structure-only",
}

DOC_LABELS = {"kkb-2024": "KKB 2024", "kkb-2022": "KKB 2022"}

#: Files a benchmark tree must hold for the viewer to be buildable.
REQUIRED_TREE_FILES = (
    "resolved-config.json",
    "manifest.json",
    "benchmark-summary.json",
)
REQUIRED_ARM_FILES = (
    "chunks.jsonl",
    "mapping.json",
    "query-results.jsonl",
    "retrieval.json",
    "structural_quality.json",
    "timing.json",
)

_EMPHASIS_SPAN = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_SPAN = re.compile(r"(?<![\w*])_([^_\n]+)_(?![\w*])")
_HEADING_PREFIX = re.compile(r"^#{1,6}\s+")
_EMPHASIS_EDGES = re.compile(r"^[*_]+|[*_]+$")
_CHUNK_NUMBER = re.compile(r"(\d+)$")


# --------------------------------------------------------------------------
# display rendering (Python-side, so tests can pin what a viewer never shows)
# --------------------------------------------------------------------------


def _inline(text: str) -> str:
    """Escape, then turn the two markdown emphases into real markup."""
    escaped = html.escape(text, quote=False)
    escaped = _EMPHASIS_SPAN.sub(r"<strong>\1</strong>", escaped)
    escaped = _ITALIC_SPAN.sub(r"<em>\1</em>", escaped)
    return escaped


def _table_html(text: str) -> str:
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    body: list[str] = []
    header_done = False
    for row in rows:
        if not row.startswith("|"):
            body.append(f"<p>{_inline(row)}</p>")
            continue
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{2,}:?", cell or "-") for cell in cells):
            header_done = True
            continue
        tag = "td" if header_done or body else "th"
        if tag == "th":
            header_done = True
        rendered = "".join(f"<{tag}>{_inline(cell)}</{tag}>" for cell in cells)
        body.append(f"<tr>{rendered}</tr>")
    return '<div class="tblwrap"><table>' + "".join(body) + "</table></div>"


def _list_html(text: str) -> str:
    items = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^[-*•]\s*", "", stripped)
        items.append(f"<li>{_inline(stripped)}</li>")
    return "<ul>" + "".join(items) + "</ul>"


def heading_plain(text: str) -> str:
    """A heading with every markdown marker removed -- never shown raw."""
    bare = _HEADING_PREFIX.sub("", text.strip())
    bare = _EMPHASIS_EDGES.sub("", bare).strip()
    bare = bare.replace("**", "").replace("__", "")
    return bare


def display_html(text: str, unit_type: str) -> str:
    """The presentation rendering of one canonical unit.

    The guarantee tests pin: the result never contains a literal ``**`` or a
    leading ``#`` marker -- a reader sees typography, not markup.
    """
    if unit_type == "heading":
        return html.escape(heading_plain(text), quote=False)
    if unit_type == "table":
        return _table_html(text)
    if unit_type == "list":
        return _list_html(text)
    paragraphs = [p for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(paragraphs) <= 1:
        return _inline(text)
    return "".join(f"<p>{_inline(p)}</p>" for p in paragraphs)


def _clean_path(section_path: Sequence[str]) -> list[str]:
    return [heading_plain(part) for part in section_path]


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------


def _require(path: Path) -> Path:
    if not path.is_file():
        raise ValueError(
            f"{path} is missing -- the viewer reads a completed "
            "amsc.chunk_benchmark output tree and cannot invent the data"
        )
    return path


def _load_json(path: Path) -> Any:
    return json.loads(_require(path).read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in _require(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _base(unit_id: str) -> str:
    return unit_id.split("#", 1)[0]


def _chunk_number(chunk_id: str) -> int:
    match = _CHUNK_NUMBER.search(chunk_id)
    return int(match.group(1)) if match else 0


def _membership(chunks: Sequence[dict]) -> dict[str, int]:
    """Base unit id -> index of the first chunk containing it (deterministic)."""
    owner: dict[str, int] = {}
    for index, chunk in enumerate(chunks):
        for unit_id in chunk["unit_ids"]:
            owner.setdefault(_base(unit_id), index)
    return owner


def _boundary_reason(
    kind: str,
    chunks: Sequence[dict],
    index: int,
    units_by_id: Mapping[str, dict],
    segments: Mapping[str, list],
) -> str:
    """Why chunk ``index`` starts where it does -- observed data only.

    ``md_*`` codes describe the size-first splitter; the others describe the
    structure-first family. Hybrid same-section splits are deliberately given
    the same mechanism-neutral code as structure-only: the artifacts do not
    record which boundaries the semantic arbitration chose, and the viewer
    must not pretend they do.
    """
    if index == 0:
        return "doc_start"
    current, previous = chunks[index], chunks[index - 1]
    first = units_by_id.get(_base(current["u"][0])) if current["u"] else None

    if kind == "markdown_recursive":
        overlap = {_base(u) for u in current["u"]} & {_base(u) for u in previous["u"]}
        if overlap:
            return "md_overlap"
        if first is not None and first["t"] == "heading":
            for row in segments.get(first["i"], ()):
                if row[0] == index and row[1] == 0:
                    return "md_heading"
        return "md_size"

    current_path = (current.get("sp") or [[]])[0]
    previous_path = (previous.get("sp") or [[]])[-1]
    if current_path != previous_path:
        return "new_section"
    if first is not None and first["t"] == "heading":
        return "label_split"
    return "budget_split"


def _load_agentic_arm(
    agentic_dir: Path, expected_sha: str, units_by_id: Mapping[str, dict]
) -> tuple[dict, dict]:
    """The optional fourth arm, read from an ``amsc.agentic_chunker`` tree.

    Reduced contract: chunks + mapping + judge summary + boundary-diff are
    required; retrieval / query-results / structural quality / timing are
    optional (they exist only after ``amsc.agentic_benchmark`` has run).
    The tree must pin the same canonical as the benchmark tree, and a
    page-sliced smoke tree is refused rather than shown beside
    full-document arms.
    """
    agentic_dir = Path(agentic_dir)
    resolved = _load_json(agentic_dir / "resolved-config.json")
    manifest = _load_json(agentic_dir / "manifest.json")
    if resolved.get("pages"):
        raise ValueError(
            f"{agentic_dir} is a page-sliced smoke tree; the viewer refuses "
            "to show it beside full-document arms"
        )
    if manifest.get("canonical_sha256") != expected_sha:
        raise ValueError(
            f"{agentic_dir} was built from a different canonical corpus than "
            "the benchmark tree; the viewer refuses to pair them"
        )
    chunks_raw = _load_jsonl(agentic_dir / "agentic" / "chunks.jsonl")
    mapping = _load_json(agentic_dir / "agentic" / "mapping.json")
    summary = _load_json(agentic_dir / "judge" / "summary.json")
    diff = _load_json(agentic_dir / "boundary-diff.json")

    chunk_index = {chunk["chunk_id"]: i for i, chunk in enumerate(chunks_raw)}
    segments: dict[str, list] = {}
    for row in mapping["chunks"]:
        target = chunk_index.get(row["chunk_id"])
        if target is None:
            continue
        for seg in row["segments"]:
            segments.setdefault(seg["unit_id"], []).append(
                [target, seg["unit_start"], seg["unit_end"], seg["method"]]
            )
    for rows in segments.values():
        rows.sort(key=lambda r: (r[0], r[1]))

    kind = "agentic_structure_llm"
    chunks = [
        {
            "id": chunk["chunk_id"],
            "num": _chunk_number(chunk["chunk_id"]),
            "n": chunk["token_count"],
            "pg": chunk.get("pages") or [],
            "hd": chunk.get("heading"),
            "hh": html.escape(heading_plain(chunk["heading"]), quote=False)
            if chunk.get("heading")
            else None,
            "sp": chunk.get("section_paths") or [],
            "sd": _clean_path((chunk.get("section_paths") or [[]])[0]),
            "st": chunk.get("split_strategies") or [],
            "u": chunk["unit_ids"],
        }
        for chunk in chunks_raw
    ]
    for index, chunk in enumerate(chunks):
        chunk["rs"] = _boundary_reason(kind, chunks, index, units_by_id, segments)

    links = derive_continuations(chunks_raw, kind=kind)
    budget_links = [
        link for link in links
        if link["relation_type"] == "TOKEN_BUDGET_CONTINUATION"
    ]
    groups = continuation_groups(len(chunks_raw), budget_links)
    forward = {link["from_index"]: link["to_index"] for link in links}
    backward = {link["to_index"]: link["from_index"] for link in links}
    relation_in = {link["to_index"]: link["relation_type"] for link in links}
    for index, chunk in enumerate(chunks):
        chunk["cp"] = backward.get(index)
        chunk["cn"] = forward.get(index)
        chunk["g"] = groups[index]
        chunk["rt"] = relation_in.get(index)

    # LLM boundary attribution -- recorded in the audit, so the viewer may
    # show it (unlike hybrid, whose benchmark records no attribution). The
    # window's boundary is the cut after ``chosen_after_unit_id``; the chunk
    # that STARTS at that boundary carries the flag.
    consulted: dict[str, dict] = {}
    for window in diff.get("windows") or []:
        after = _base(window["chosen_after_unit_id"])
        # Only a cut that survived into the final chunks is a moved
        # boundary; a provisional cut the rejoin absorbed never reaches a
        # chunk here (no chunk ends at it), so it cannot be mislabelled.
        moved = bool(window["final_boundary_moved"])
        reason = None
        if moved:
            for decision in window.get("decisions") or []:
                if (
                    _base(decision.get("cut_after_unit_id", "")) == after
                    and decision.get("effective") == "SPLIT"
                ):
                    reason = decision.get("reason_code")
                    break
        consulted[after] = {
            "m": 1 if moved else 0,
            "rc": reason,
            "fb": window.get("fallback"),
        }
    for index in range(1, len(chunks)):
        previous = chunks[index - 1]
        if not previous["u"]:
            continue
        flag = consulted.get(_base(previous["u"][-1]))
        if flag is not None:
            chunks[index]["llm"] = flag

    queries: dict[str, dict] = {}
    query_path = agentic_dir / "agentic" / "query-results.jsonl"
    if query_path.is_file():
        for row in _load_jsonl(query_path):
            queries[row["query_id"]] = {
                "f": row.get("first_relevant_rank"),
                "cov": row.get("source_evidence_coverage"),
                "res": [
                    {
                        "r": result["rank"],
                        "c": chunk_index.get(result["chunk_id"]),
                        "m": result.get("matched_evidence_unit_ids") or [],
                        "pg": result.get("pages") or [],
                        "tk": result.get("token_count"),
                    }
                    for result in row.get("results") or []
                ],
            }

    def _optional_json(path: Path) -> Any:
        return _load_json(path) if path.is_file() else None

    arm = {
        "kind": kind,
        "chunks": chunks,
        "m": _membership(chunks_raw),
        "seg": segments,
        "q": queries,
        "ret": _optional_json(agentic_dir / "agentic" / "retrieval.json"),
        "sq": _optional_json(agentic_dir / "agentic" / "structural_quality.json"),
        "tim": _optional_json(agentic_dir / "agentic" / "timing.json"),
        "health": mapping.get("health") or {},
    }
    meta = {
        "mode": manifest.get("mode"),
        "model": manifest.get("model_id"),
        "summary": summary,
        "diff": diff.get("summary") or {},
    }
    return arm, meta


def load_corpus(
    benchmark_dir: Path, root: Path, agentic_dir: Path | None = None
) -> dict:
    """Read one benchmark tree plus its pinned canonical into viewer data."""
    benchmark_dir = Path(benchmark_dir)
    for name in REQUIRED_TREE_FILES:
        _require(benchmark_dir / name)

    config = _load_json(benchmark_dir / "resolved-config.json")
    manifest = _load_json(benchmark_dir / "manifest.json")
    summary = _load_json(benchmark_dir / "benchmark-summary.json")
    source = config["source"]

    units_path = _require(root / source["units"])
    digest = hashlib.sha256(units_path.read_bytes()).hexdigest()
    pinned = source.get("units_sha256") or manifest.get("canonical_sha256")
    if pinned and digest != pinned:
        raise ValueError(
            f"{units_path} hashes {digest[:16]}... but the benchmark was run "
            f"against {pinned[:16]}...; the viewer refuses to pair a canonical "
            "with results produced from a different one"
        )

    units_raw = _load_jsonl(units_path)
    units: list[dict] = []
    units_by_id: dict[str, dict] = {}
    for unit in units_raw:
        text = unit["text"]
        display = display_html(text, unit["type"])
        entry = {
            "i": unit["unit_id"],
            "t": unit["type"],
            "p": unit["source"]["page"],
            "x": text,
            "h": display if display != html.escape(text, quote=False) else 0,
            "s": unit.get("section_path") or [],
            "sd": _clean_path(unit.get("section_path") or []),
            "r": unit.get("semantic_role"),
            "o": unit.get("opens_section"),
            "l": unit.get("heading_level"),
            "b": unit["source"].get("block"),
        }
        units.append(entry)
        units_by_id[entry["i"]] = entry

    gold_path = _require(root / source["gold_queries"])
    gold_raw = _load_json(gold_path)
    gold = [
        {
            "id": q["query_id"],
            "q": q["question"],
            "a": q.get("expected_answer"),
            "ev": q.get("evidence_unit_ids") or [],
            "pg": q.get("evidence_pages") or [],
            "ty": q.get("evidence_type"),
            "df": q.get("difficulty"),
        }
        for q in gold_raw["queries"]
    ]

    arm_kinds = {arm: config["arms"][arm]["kind"] for arm in ARM_ORDER}
    arms: dict[str, dict] = {}
    for arm in ARM_ORDER:
        arm_dir = benchmark_dir / arm
        for name in REQUIRED_ARM_FILES:
            _require(arm_dir / name)
        chunks_raw = _load_jsonl(arm_dir / "chunks.jsonl")
        mapping = _load_json(arm_dir / "mapping.json")

        chunk_index = {chunk["chunk_id"]: i for i, chunk in enumerate(chunks_raw)}
        segments: dict[str, list] = {}
        for row in mapping["chunks"]:
            target = chunk_index.get(row["chunk_id"])
            if target is None:
                continue
            for seg in row["segments"]:
                segments.setdefault(seg["unit_id"], []).append(
                    [target, seg["unit_start"], seg["unit_end"], seg["method"]]
                )
        for rows in segments.values():
            rows.sort(key=lambda r: (r[0], r[1]))

        chunks = [
            {
                "id": chunk["chunk_id"],
                "num": _chunk_number(chunk["chunk_id"]),
                "n": chunk["token_count"],
                "pg": chunk.get("pages") or [],
                "hd": chunk.get("heading"),
                "hh": html.escape(heading_plain(chunk["heading"]), quote=False)
                if chunk.get("heading")
                else None,
                "sp": chunk.get("section_paths") or [],
                "sd": _clean_path((chunk.get("section_paths") or [[]])[0]),
                "st": chunk.get("split_strategies") or [],
                "u": chunk["unit_ids"],
            }
            for chunk in chunks_raw
        ]
        for index, chunk in enumerate(chunks):
            chunk["rs"] = _boundary_reason(
                arm_kinds[arm], chunks, index, units_by_id, segments
            )

        # Continuation links -- the derived relationship layer, computed by
        # amsc.chunk_relations (single source of truth) over the same frozen
        # rows. ``cp``/``cn`` carry every same-section link so the detail panel
        # can name its type; ``g`` (the expansion-chain group) is built from
        # TOKEN_BUDGET_CONTINUATION links only, because only those are walked
        # by the local expansion.
        links = derive_continuations(chunks_raw, kind=arm_kinds[arm])
        budget_links = [
            link for link in links
            if link["relation_type"] == "TOKEN_BUDGET_CONTINUATION"
        ]
        groups = continuation_groups(len(chunks_raw), budget_links)
        forward = {link["from_index"]: link["to_index"] for link in links}
        backward = {link["to_index"]: link["from_index"] for link in links}
        relation_in = {link["to_index"]: link["relation_type"] for link in links}
        for index, chunk in enumerate(chunks):
            chunk["cp"] = backward.get(index)
            chunk["cn"] = forward.get(index)
            chunk["g"] = groups[index]
            chunk["rt"] = relation_in.get(index)

        queries: dict[str, dict] = {}
        for row in _load_jsonl(arm_dir / "query-results.jsonl"):
            queries[row["query_id"]] = {
                "f": row.get("first_relevant_rank"),
                "cov": row.get("source_evidence_coverage"),
                "res": [
                    {
                        "r": result["rank"],
                        "c": chunk_index.get(result["chunk_id"]),
                        "m": result.get("matched_evidence_unit_ids") or [],
                        "pg": result.get("pages") or [],
                        "tk": result.get("token_count"),
                    }
                    for result in row.get("results") or []
                ],
            }

        arms[arm] = {
            "kind": arm_kinds[arm],
            "chunks": chunks,
            "m": _membership(chunks_raw),
            "seg": segments,
            "q": queries,
            "ret": _load_json(arm_dir / "retrieval.json"),
            "sq": _load_json(arm_dir / "structural_quality.json"),
            "tim": _load_json(arm_dir / "timing.json"),
            "health": mapping.get("health") or {},
        }

    diffs = _difference_points(units, arms)

    result = {
        "label": DOC_LABELS.get(benchmark_dir.name, benchmark_dir.name),
        "units": units,
        "arms": arms,
        "gold": gold,
        "diffs": diffs,
        "diffPages": sorted({point["p"] for point in diffs}),
        "pages": sorted({unit["p"] for unit in units}),
        "meta": {
            "diag": summary.get("arm_diagnostics") or {},
            "guard": summary.get("interpretation_guardrail"),
            "etypes": summary.get("evidence_type_hit_at_5") or {},
            "qcomp": summary.get("query_comparison") or {},
            "parserFindings": summary.get("parser_baseline_finding_count"),
            "secondary": summary.get("secondary_gold"),
            "timing": summary.get("timing") or {},
            "budgets": config.get("tokens") or {},
            "canonicalSha": manifest.get("canonical_sha256"),
            "status": summary.get("status"),
            "queryCount": summary.get("query_count") or len(gold),
        },
    }
    if agentic_dir is not None:
        # The fourth arm rides in ``arms`` so every arm-indexed renderer works
        # unchanged, but it never enters ARM_ORDER: the frozen dashboard
        # tables and the three-arm difference definition stay untouched, and
        # a build without an agentic tree is byte-identical to today's.
        agentic_arm, agentic_meta = _load_agentic_arm(
            Path(agentic_dir), digest, units_by_id
        )
        result["arms"]["agentic"] = agentic_arm
        result["agenticMeta"] = agentic_meta
    return result


def _difference_points(units: Sequence[dict], arms: Mapping[str, dict]) -> list[dict]:
    """Where the three arms disagree on a boundary between content units.

    Definition (deterministic): take the canonical content units in order
    (headings excluded -- two arms leave them out of ``unit_ids``). For each
    consecutive pair, ``split(arm)`` is true iff the two units' first-chunk
    memberships differ in that arm. The pair is a difference point iff the
    three split values are not all equal. Pairs where any arm lacks a
    membership for either unit are skipped rather than guessed.
    """
    content = [unit for unit in units if unit["t"] != "heading"]
    points: list[dict] = []
    for left, right in zip(content, content[1:]):
        split: dict[str, bool] = {}
        usable = True
        for arm in ARM_ORDER:
            membership = arms[arm]["m"]
            left_at = membership.get(left["i"])
            right_at = membership.get(right["i"])
            if left_at is None or right_at is None:
                usable = False
                break
            split[arm] = left_at != right_at
        if not usable:
            continue
        if len(set(split.values())) > 1:
            points.append({"a": left["i"], "b": right["i"], "p": right["p"], "s": split})
    return points


# --------------------------------------------------------------------------
# building
# --------------------------------------------------------------------------


def build_viewer(
    benchmarks: Mapping[str, Path],
    output: Path,
    root: Path = Path("."),
    agentic: Mapping[str, Path] | None = None,
) -> Path:
    """Build the single-file viewer for the given benchmark trees.

    ``agentic`` optionally maps a document id to an ``amsc.agentic_chunker``
    tree; that document gains the fourth arm. Without it the output is
    byte-identical to a three-arm build.
    """
    if not benchmarks:
        raise ValueError("at least one benchmark tree is required")
    agentic = dict(agentic or {})
    unknown = sorted(set(agentic) - set(benchmarks))
    if unknown:
        raise ValueError(
            f"agentic trees given for unknown documents: {unknown}; every "
            "agentic tree needs its benchmark tree"
        )
    output = Path(output)
    if "evaluation" in output.parts:
        raise ValueError("refusing to write the viewer into evaluation/ (frozen)")

    docs = {
        doc: load_corpus(
            Path(directory),
            Path(root),
            agentic_dir=agentic.get(doc),
        )
        for doc, directory in sorted(benchmarks.items())
    }
    data = {
        "docs": docs,
        "armOrder": list(ARM_ORDER),
        "armLabels": ARM_LABELS,
        "generator": "amsc.viewer_v2",
    }
    payload = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).replace("</", "<\\/")

    document = _TEMPLATE.replace("__VIEWER_DATA__", payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    return output


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.viewer_v2",
        description=(
            "Build the self-contained Viewer v2 HTML from completed "
            "chunk-benchmark output trees"
        ),
    )
    parser.add_argument(
        "--benchmark",
        action="append",
        required=True,
        metavar="DOC=DIR",
        help="document id and its benchmark output tree, e.g. "
        "kkb-2024=artifacts/chunk-benchmark-v5/kkb-2024 (repeatable)",
    )
    parser.add_argument(
        "--agentic",
        action="append",
        default=[],
        metavar="DOC=DIR",
        help="optional agentic-chunker tree for a document, e.g. "
        "kkb-2024=artifacts/agentic-chunker/kkb-2024 (repeatable)",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    benchmarks: dict[str, Path] = {}
    for spec in args.benchmark:
        doc, _, directory = spec.partition("=")
        if not directory:
            parser.error(f"--benchmark expects DOC=DIR, got {spec!r}")
        benchmarks[doc] = Path(directory)
    agentic: dict[str, Path] = {}
    for spec in args.agentic:
        doc, _, directory = spec.partition("=")
        if not directory:
            parser.error(f"--agentic expects DOC=DIR, got {spec!r}")
        agentic[doc] = Path(directory)

    destination = build_viewer(
        benchmarks, args.output, root=args.root, agentic=agentic
    )
    print(json.dumps({"output": str(destination), "documents": sorted(benchmarks)}))
    return 0


# --------------------------------------------------------------------------
# template
# --------------------------------------------------------------------------

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>AMSC Chunking Viewer v2</title>
<style>
:root{
  --paper:#fbfaf7; --panel:#ffffff; --ink:#22262b; --muted:#6b7280;
  --line:#e4e2dc; --accent:#2757ad; --accent-soft:#e8eefb;
  --good:#1a7f37; --warn:#b45309; --bad:#b42318;
  --tintA:#f2f6fd; --tintB:#faf4ea; --mark:#fff3b0;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--paper);color:var(--ink);
  font:15px/1.55 "Segoe UI",system-ui,-apple-system,sans-serif}
button{font:inherit;color:inherit;background:none;border:none;cursor:pointer}
select{font:inherit;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:#fff}
.topbar{position:sticky;top:0;z-index:40;background:var(--panel);
  border-bottom:1px solid var(--line);padding:10px 22px;
  display:flex;gap:18px;align-items:center;flex-wrap:wrap}
.brand{font-weight:600;letter-spacing:.2px}
.brand small{color:var(--muted);font-weight:400;margin-left:8px}
.tabs{display:flex;gap:4px;background:#f0efe9;border-radius:9px;padding:3px}
.tabs button{padding:6px 16px;border-radius:7px;color:var(--muted);font-weight:500}
.tabs button.on{background:#fff;color:var(--ink);box-shadow:0 1px 2px rgba(0,0,0,.08)}
.seg{display:flex;gap:4px;background:#f0efe9;border-radius:9px;padding:3px}
.seg button{padding:5px 13px;border-radius:7px;color:var(--muted)}
.seg button.on{background:var(--accent);color:#fff}
.bar-right{margin-left:auto;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.filterseg button.on{background:#3d3f43;color:#fff}
.diffnav button{border:1px solid var(--line);border-radius:6px;padding:4px 10px;background:#fff}
.diffnav button:disabled{opacity:.4;cursor:default}
.diffcount{color:var(--muted);font-size:13px}
main{max-width:1720px;margin:0 auto;padding:22px}
.hidden{display:none!important}

/* ---- presentation ---- */
.pres-layout{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:22px}
.docpage{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:38px 46px;font-family:Georgia,"Times New Roman",serif;font-size:16px}
.docpage .pagehead{font-family:"Segoe UI",system-ui,sans-serif;color:var(--muted);
  font-size:13px;margin-bottom:18px;display:flex;justify-content:space-between}
.chunkline{display:flex;align-items:center;gap:10px;margin:20px 0 12px;
  font-family:"Segoe UI",system-ui,sans-serif}
.chunkline .rule{flex:1;border-top:3px solid var(--accent);opacity:.5}
.chunkline.tech .rule{border-top:2px dashed #c9a24b;opacity:.75}
.chunkline .kind{font-size:11.5px;font-weight:700;letter-spacing:.6px;color:var(--accent);
  text-transform:uppercase;white-space:nowrap}
.chunkline.tech .kind{color:#8a5a09}
.chunkpill{background:var(--accent-soft);color:var(--accent);border:1px solid #c8d8f2;
  border-radius:999px;padding:3px 14px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap}
.chunkline.tech .chunkpill{background:#fdf6e7;color:#8a5a09;border-color:#ecd9ab}
.chunkpill .why{font-weight:400;color:#41537a}
.chunkline.tech .chunkpill .why{color:#8a6a2f}
.u.contedge{border-left:3px solid #e4c988}
.u.expmember{border-left:3px solid #c9861b;background:#fdf6e7}
.conttoggle{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--muted);cursor:pointer}
.modehint{font-size:12px;color:var(--muted);width:100%;padding-left:2px}
.seg button small{display:block;font-size:10.5px;font-weight:400;line-height:1.1;opacity:.75}
.detail-links button{color:var(--accent);text-decoration:underline;padding:0;font-size:13px}
.diffbadge{background:#fdecc8;color:var(--warn);border:1px solid #f2d9a4;border-radius:999px;
  padding:3px 10px;font-size:12px;font-weight:600;white-space:nowrap}
.diffbadge .glyphs{font-weight:400;margin-left:6px}
.u{padding:2px 10px;border-left:3px solid transparent;border-radius:4px}
.u.tintA{background:var(--tintA)}
.u.tintB{background:var(--tintB)}
.u.evflash{outline:3px solid var(--warn);outline-offset:2px}
.u h1,.u h2,.u h3,.u h4,.u h5,.u h6{font-family:"Segoe UI",system-ui,sans-serif;
  line-height:1.3;margin:14px 0 6px}
.u h1{font-size:24px}.u h2{font-size:21px}.u h3{font-size:18px}
.u h4{font-size:16px}.u h5{font-size:15px}.u h6{font-size:14px;color:#3c4046}
.u p{margin:7px 0}
.u ul{margin:7px 0 7px 22px}
.u li{margin:3px 0}
.tblwrap{overflow-x:auto;margin:10px 0}
.tblwrap table{border-collapse:collapse;font-size:13.5px;font-family:"Segoe UI",system-ui,sans-serif}
.tblwrap th,.tblwrap td{border:1px solid var(--line);padding:4px 9px;text-align:left}
.tblwrap th{background:#f4f3ee}
.sidecard{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:18px;position:sticky;top:74px;max-height:calc(100vh - 96px);overflow:auto}
.sidecard h3{font-size:15px;margin-bottom:10px}
.sidecard .kv{display:grid;grid-template-columns:96px 1fr;gap:5px 10px;font-size:13.5px}
.sidecard .kv dt{color:var(--muted)}
.sidecard .empty{color:var(--muted);font-size:13.5px}
.reason-sent{margin-top:12px;padding:10px 12px;background:#f6f5f0;border-radius:8px;font-size:13.5px}
.arminfo{margin-top:14px;border-top:1px solid var(--line);padding-top:12px;
  font-size:12.5px;color:var(--muted)}

/* ---- query ---- */
.qhead{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px 24px;margin-bottom:18px}
.qhead .qq{font-size:19px;font-weight:600;margin-bottom:6px}
.qhead .qa{color:#374151;margin-bottom:10px}
.qhead .qmeta{color:var(--muted);font-size:13px;margin-bottom:10px}
.evbox{border-left:3px solid var(--warn);background:#fdf9ef;padding:10px 14px;border-radius:0 8px 8px 0;
  font-family:Georgia,serif;font-size:14.5px;max-height:210px;overflow:auto}
.evbox .evlabel{font-family:"Segoe UI",system-ui,sans-serif;font-size:12px;color:var(--warn);
  font-weight:600;letter-spacing:.4px;text-transform:uppercase;margin-bottom:6px}
.qcols{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
.qcol{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;min-width:0}
.qcol .armname{font-weight:600;margin-bottom:8px;display:flex;align-items:center;gap:8px}
.status{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:2px 11px;font-size:13px;font-weight:600}
.status.ok{background:#e8f5ec;color:var(--good)}
.status.mid{background:#fdf3e2;color:var(--warn)}
.status.miss{background:#fbeae7;color:var(--bad)}
.qcol .covline{color:var(--muted);font-size:12.5px;margin-bottom:10px}
.rchunk{border:1px solid var(--line);border-radius:9px;padding:12px;font-family:Georgia,serif;
  font-size:14px;max-height:330px;overflow:auto}
.rchunk mark{background:var(--mark);padding:0 2px;border-radius:2px}
.rchunk .rhead{font-family:"Segoe UI",system-ui,sans-serif;font-size:12.5px;color:var(--muted);margin-bottom:8px}
.rchunk .piece{margin:6px 0}
.top5{margin-top:12px}
.top5 summary{cursor:pointer;color:var(--accent);font-size:13.5px}
.top5 .row{display:flex;gap:8px;align-items:baseline;padding:6px 4px;border-bottom:1px solid var(--line);font-size:13px;flex-wrap:wrap}
.top5 .row .rk{font-weight:600;min-width:44px}
.top5 .row .mt{color:var(--good)}
.qlink{margin-top:10px;font-size:13px}
.qlink button{color:var(--accent);text-decoration:underline;padding:0}
.llmslot{margin-top:18px;border:1px dashed var(--line);border-radius:12px;padding:14px 18px;
  color:var(--muted);font-size:13px;background:#fcfbf8}

/* ---- debug ---- */
.dbg{display:grid;grid-template-columns:minmax(0,1fr) 400px;gap:20px}
.dbgunit{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:10px;cursor:pointer}
.dbgunit.sel{outline:2px solid var(--accent)}
.dbgunit .head{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:6px}
.chip{font:12px/1.4 Consolas,monospace;background:#f0efe9;border-radius:5px;padding:1px 8px}
.chip.role{background:#e6e0f3}
.chip.opens{background:#dcefe2}
.chip.noopen{background:#f6e3e0}
.dbgunit .path{font-size:12px;color:var(--muted);margin-bottom:6px;font-family:Consolas,monospace;word-break:break-all}
.dbgunit .txt{font-size:13px;color:#374151;white-space:pre-wrap;max-height:80px;overflow:hidden}
.dbgtable{width:100%;border-collapse:collapse;font:12px Consolas,monospace;margin-top:8px}
.dbgtable th,.dbgtable td{border:1px solid var(--line);padding:2px 7px;text-align:left}
.dbgtable th{background:#f4f3ee;font-family:"Segoe UI",system-ui,sans-serif}
.inspector{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;
  position:sticky;top:74px;max-height:calc(100vh - 96px);overflow:auto;font-size:13px}
.inspector pre{white-space:pre-wrap;font:12.5px Consolas,monospace;background:#f6f5f0;
  border-radius:8px;padding:10px;margin-top:8px;max-height:280px;overflow:auto}

/* ---- benchmark ---- */
.bench h2{margin:26px 0 10px;font-size:18px}
.bench .note{color:var(--muted);font-size:13px;max-width:900px}
.guard{border-left:3px solid var(--accent);background:var(--accent-soft);
  padding:10px 16px;border-radius:0 8px 8px 0;font-size:13.5px;margin:12px 0 4px;max-width:900px}
.cards{display:flex;gap:14px;flex-wrap:wrap;margin-top:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 20px;min-width:150px}
.card .v{font-size:23px;font-weight:600;font-variant-numeric:tabular-nums}
.card .k{color:var(--muted);font-size:12.5px}
.btable{border-collapse:collapse;background:var(--panel);border-radius:10px;overflow:hidden;
  font-variant-numeric:tabular-nums;margin-top:8px}
.btable th,.btable td{border:1px solid var(--line);padding:7px 16px;text-align:right;font-size:14px}
.btable th:first-child,.btable td:first-child{text-align:left}
.btable th{background:#f4f3ee;font-weight:600}
.btable td.best{font-weight:700;color:var(--accent)}
.btable td.best::after{content:" \25CF";font-size:9px;vertical-align:2px}
.legend{color:var(--muted);font-size:12.5px;margin-top:6px}
.pairlists{display:flex;gap:16px;flex-wrap:wrap;margin-top:8px}
.pairlists .pl{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;font-size:13px}
.pairlists .pl b{font-weight:600}
.qidchip{font-family:Consolas,monospace;background:#f0efe9;border-radius:4px;padding:0 6px;font-size:12px;cursor:pointer}
details.secgold{margin-top:14px}
details.secgold summary{cursor:pointer;color:var(--accent)}
footer{color:var(--muted);font-size:12px;padding:26px 22px;text-align:center}
</style>
</head>
<body>
<div class="topbar">
  <span class="brand">AMSC Chunking<small>Viewer v2</small></span>
  <select id="docsel" title="Doküman"></select>
  <div class="tabs" id="modetabs">
    <button data-mode="presentation">Sunum</button>
    <button data-mode="query">Sorgu</button>
    <button data-mode="debug">Debug</button>
    <button data-mode="benchmark">Benchmark</button>
  </div>
  <div class="seg" id="armseg"></div>
  <div class="bar-right">
    <span id="pagectl">
      Sayfa <select id="pagesel"></select>
    </span>
    <span class="seg filterseg" id="filterseg">
      <button data-f="all">Tümü</button>
      <button data-f="diff">Yalnız farklar</button>
    </span>
    <span class="diffnav" id="diffnav">
      <button id="prevdiff">&#8592; Önceki fark</button>
      <button id="nextdiff">Sonraki fark &#8594;</button>
      <span class="diffcount" id="diffcount"></span>
    </span>
    <label class="conttoggle" id="conttoggle" title="Retrieval sonrası birlikte taşınabilecek devam chunk'larını görselleştirir; benchmark sonucunu değiştirmez">
      <input type="checkbox" id="contchk"> Devam zinciri (local expansion)
    </label>
  </div>
  <div class="modehint hidden" id="modehint"></div>
</div>
<main>
  <div id="view-presentation" class="pres-layout" data-mode="presentation">
    <div id="prespage"></div>
    <aside class="sidecard" id="presdetail"></aside>
  </div>
  <div id="view-query" class="hidden" data-mode="query">
    <div style="margin-bottom:14px">
      Gold sorgu:
      <select id="querysel" style="max-width:900px"></select>
    </div>
    <div id="queryhead"></div>
    <div class="qcols" id="querycols"></div>
    <div class="llmslot" id="llmslot">
      LLM cevap karşılaştırması — gelecek aşama için ayrılmış alan. Bu turda üretim yok.
    </div>
  </div>
  <div id="view-debug" class="dbg hidden" data-mode="debug">
    <div id="dbglist"></div>
    <aside class="inspector" id="inspector"></aside>
  </div>
  <div id="view-benchmark" class="bench hidden" data-mode="benchmark"></div>
</main>
<footer id="foot"></footer>
<script id="viewer-data" type="application/json">__VIEWER_DATA__</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("viewer-data").textContent);
const ARMS = DATA.armOrder;
const ARM_LABEL = DATA.armLabels;

const REASONS = {
  doc_start:   {label:"Doküman başlangıcı",
                sent:"Bu, dokümanın ilk chunk'ı."},
  new_section: {label:"Yeni bölüm başladı",
                sent:"Bir önceki chunk'ın bölümü kapandı; bu chunk yeni bir bölüm başlığıyla açılıyor."},
  label_split: {label:"Ara başlıkta bölündü",
                sent:"Aynı bölümün içinde, okuyucunun zaten duraksadığı bir ara başlıkta kesildi."},
  budget_split:{label:"Token bütçesi doldu",
                sent:"Bölüm hedef token bütçesini aştığı için bölündü; bölüm başlığı iki parçada da korunuyor."},
  md_size:     {label:"Boyut tabanlı kesim",
                sent:"Markdown yöntemi bölüm yapısına bakmaz; hedef boyuta ulaşıldığında keser."},
  md_overlap:  {label:"Boyut tabanlı kesim + örtüşme",
                sent:"Hedef boyuta ulaşıldı; önceki chunk'ın kuyruğu örtüşme (overlap) olarak bu chunk'a taşındı."},
  md_heading:  {label:"Başlık sınırında kesim",
                sent:"Kesim, markdown ayracının denk geldiği bir başlık sınırında gerçekleşti."}
};

// Continuation connector text, per boundary reason. Shown only when the
// boundary carries a TOKEN_BUDGET_CONTINUATION link (same section, adjacent).
const CONT_LABELS = {
  budget_split: "Önceki chunk'ın devamı — boyut sınırı nedeniyle ayrıldı",
  label_split:  "Önceki chunk'ın devamı — ara başlıkta bölündü",
  md_size:      "Önceki chunk'ın devamı — boyut sınırı nedeniyle ayrıldı",
  md_overlap:   "Önceki chunk'ın devamı — boyut sınırı (kuyruk örtüşme olarak taşındı)",
  md_heading:   "Önceki chunk'ın devamı — başlık sınırında kesildi"
};

// Presentation-mode naming. Standard is the product's fast mode; the
// embedding-assisted hybrid stays visible as a research arm, NOT a product
// mode -- the product's Deep Analysis (Structure + LLM-assisted chunking)
// runs a backend LLM boundary judge and has no measured data in this run.
const MODE_NAMES = {
  "structure-only": {top:"Standard", sub:"Structure-only · hızlı ve deterministic"},
  "hybrid":         {top:"Hybrid", sub:"embedding-assisted · araştırma kolu"},
  "markdown":       {top:"Markdown", sub:"baseline"},
  "agentic":        {top:"Agentic Chunker", sub:"Structure + LLM · ayrı koşu"}
};
const MODE_ARM_ORDER = ["structure-only", "hybrid", "markdown"];
// The fourth arm exists only for documents whose build carried an
// agentic-chunker tree; the frozen three-arm order above never changes.
const armLabel = a => ARM_LABEL[a] || (MODE_NAMES[a] && MODE_NAMES[a].top) || a;
const hasAgentic = () => Boolean(D().arms.agentic);
const armsList = () => hasAgentic() ? ARMS.concat(["agentic"]) : ARMS;
const presArms = () => hasAgentic() ? MODE_ARM_ORDER.concat(["agentic"]) : MODE_ARM_ORDER;

const MODE_HINTS = {
  "structure-only": "Standard — Structure-only: hızlı ve deterministic. Ürünün " +
    "Deep Analysis modu (Structure + LLM-assisted chunking) önemli dokümanlarda " +
    "zor chunk sınırlarını backend'de LLM ile değerlendirir; yalnız ingest " +
    "sırasında çalışır, retrieval'a ve cevaba karışmaz. Bu koşuda Deep Analysis " +
    "verisi yoktur.",
  "hybrid": "Hybrid — embedding-assisted araştırma kolu (ürün modu değildir): " +
    "bütçeyi aşan bir bölümde kural birden fazla geçerli kesim adayı " +
    "bıraktığında, kesim yeri semantik benzerlikle seçilir (H1 arbitration). " +
    "Bir güven/belirsizlik dedektörü değildir.",
  "markdown": null,
  "agentic": "Agentic Chunker — Structure + LLM: yapısal kural aday sınırları " +
    "belirler, generative model her adaya SPLIT/KEEP oyu verir; son seçim, " +
    "fallback ve token limitleri deterministic kuralda kalır. Ayrı ve " +
    "model-bağımlı bir koşudur; frozen üç kolun benchmark karşılaştırmasına " +
    "dahil değildir, kazanan ilan edilmez."
};

const state = {
  doc: Object.keys(DATA.docs)[0],
  mode: "presentation",
  arm: ARMS[2] || ARMS[0],
  page: null,
  filter: "all",
  diffIdx: -1,
  query: null,
  selChunk: null,
  selUnit: null,
  contShow: false
};

const D = () => DATA.docs[state.doc];
const A = () => D().arms[state.arm];
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");

function unitById(id){ return D()._byId[id]; }
function indexDocs(){
  for (const doc of Object.values(DATA.docs)) {
    doc._byId = {};
    doc.units.forEach(u => { doc._byId[u.i] = u; });
    doc._diffKey = new Set(doc.diffs.map(d => d.a + "|" + d.b));
  }
}
indexDocs();

/* -------- unit rendering (presentation-grade) -------- */
function unitHtml(u){
  if (u.h !== 0 && u.h !== null && u.h !== undefined) {
    if (u.t === "heading") {
      const lvl = Math.min(Math.max(u.l || 3, 1), 6);
      return "<h" + lvl + ">" + u.h + "</h" + lvl + ">";
    }
    if (u.t === "table" || u.t === "list") return u.h;
    return "<p>" + u.h + "</p>";
  }
  if (u.t === "heading") {
    const lvl = Math.min(Math.max(u.l || 3, 1), 6);
    return "<h" + lvl + ">" + esc(u.x) + "</h" + lvl + ">";
  }
  return "<p>" + esc(u.x) + "</p>";
}

/* -------- top bar -------- */
function initBar(){
  const docsel = $("docsel");
  docsel.innerHTML = Object.entries(DATA.docs)
    .map(([id, doc]) => `<option value="${id}">${esc(doc.label)}</option>`).join("");
  docsel.value = state.doc;
  docsel.onchange = () => { state.doc = docsel.value; state.page = null;
    state.query = null; state.selChunk = null; state.selUnit = null; state.diffIdx = -1;
    if (!D().arms[state.arm]) state.arm = ARMS[2] || ARMS[0];
    render(); };

  $("modetabs").querySelectorAll("button").forEach(b => {
    b.onclick = () => { state.mode = b.dataset.mode; render(); };
  });
  $("contchk").onchange = () => { state.contShow = $("contchk").checked; render(); };
  $("filterseg").querySelectorAll("button").forEach(b => {
    b.onclick = () => { state.filter = b.dataset.f; state.diffIdx = -1; syncPage(); render(); };
  });
  $("prevdiff").onclick = () => stepDiff(-1);
  $("nextdiff").onclick = () => stepDiff(1);
}

function pageList(){
  return state.filter === "diff" && D().diffPages.length ? D().diffPages : D().pages;
}
function syncPage(){
  const pages = pageList();
  if (!pages.includes(state.page)) state.page = pages[0];
}
function stepDiff(delta){
  const diffs = D().diffs;
  if (!diffs.length) return;
  state.diffIdx = (state.diffIdx + delta + diffs.length) % diffs.length;
  const point = diffs[state.diffIdx];
  state.filter = "diff";
  state.page = point.p;
  state.mode = "presentation";
  render();
  const el = document.querySelector(`[data-diff="${point.a}|${point.b}"]`);
  if (el) { el.scrollIntoView({block:"center"}); el.style.boxShadow = "0 0 0 3px #f2d9a4"; }
}

function renderArmSeg(){
  const seg = $("armseg");
  if (state.mode === "presentation") {
    seg.innerHTML = presArms().map(a => {
      const naming = MODE_NAMES[a] || {top: armLabel(a), sub: ""};
      return `<button data-arm="${a}">${esc(naming.top)}<small>${esc(naming.sub)}</small></button>`;
    }).join("");
  } else {
    seg.innerHTML = armsList().map(a =>
      `<button data-arm="${a}">${esc(armLabel(a))}</button>`).join("");
  }
  seg.querySelectorAll("button").forEach(b => {
    b.onclick = () => { state.arm = b.dataset.arm; state.selChunk = null; render(); };
  });
}

function syncBar(){
  $("modetabs").querySelectorAll("button").forEach(b =>
    b.classList.toggle("on", b.dataset.mode === state.mode));
  renderArmSeg();
  $("armseg").querySelectorAll("button").forEach(b =>
    b.classList.toggle("on", b.dataset.arm === state.arm));
  $("filterseg").querySelectorAll("button").forEach(b =>
    b.classList.toggle("on", b.dataset.f === state.filter));
  const inPage = state.mode === "presentation" || state.mode === "debug";
  $("pagectl").style.display = inPage ? "" : "none";
  $("armseg").style.display = (state.mode === "benchmark" || state.mode === "query") ? "none" : "";
  $("filterseg").style.display = state.mode === "presentation" ? "" : "none";
  $("diffnav").style.display = state.mode === "presentation" ? "" : "none";
  $("conttoggle").style.display = state.mode === "presentation" ? "" : "none";
  $("contchk").checked = state.contShow;
  const hint = state.mode === "presentation" ? MODE_HINTS[state.arm] : null;
  $("modehint").textContent = hint || "";
  $("modehint").classList.toggle("hidden", !hint);
  if (inPage) {
    syncPage();
    const sel = $("pagesel");
    sel.innerHTML = pageList().map(p => `<option value="${p}">${p}</option>`).join("");
    sel.value = state.page;
    sel.onchange = () => { state.page = Number(sel.value); render(); };
  }
  const diffs = D().diffs;
  $("diffcount").textContent = diffs.length
    ? (state.diffIdx >= 0 ? (state.diffIdx + 1) + " / " : "") + diffs.length + " fark noktası"
    : "fark yok";
  $("prevdiff").disabled = $("nextdiff").disabled = !diffs.length;
}

/* -------- presentation -------- */
function pageUnits(page){ return D().units.filter(u => u.p === page); }

function boundaryPositions(units, arm){
  // Boundary sits before the first unit of a new chunk; consecutive unmapped
  // units (headings the arm keeps out of unit_ids) attach to the chunk below.
  const m = D().arms[arm].m;
  const marks = new Array(units.length).fill(null);
  let previous;
  for (let k = 0; k < units.length; k++) {
    const at = m[units[k].i];
    if (at === undefined) continue;
    if (at !== previous) {
      let pos = k;
      while (pos > 0 && m[units[pos - 1].i] === undefined) pos--;
      marks[pos] = at;
      previous = at;
    }
  }
  return marks;
}

function renderPresentation(){
  const units = pageUnits(state.page);
  const arm = state.arm, armData = A();
  const marks = boundaryPositions(units, arm);
  const m = armData.m;
  const diffKey = D()._diffKey;
  const diffByRight = {};
  D().diffs.forEach(d => { diffByRight[d.b] = d; });

  const expansion = state.contShow && state.selChunk !== null
    ? simulateExpansion(armData, state.selChunk) : null;
  const expMembers = expansion ? new Set(expansion.members) : null;

  let htmlOut = `<div class="docpage"><div class="pagehead">` +
    `<span>${esc(D().label)} — sayfa ${state.page}</span>` +
    `<span>${esc(armLabel(arm))}</span></div>`;
  let tint = 0;
  for (let k = 0; k < units.length; k++) {
    const u = units[k];
    if (marks[k] !== null) {
      const chunk = armData.chunks[marks[k]];
      const isCont = chunk.cp !== null && chunk.cp !== undefined;
      const why = isCont
        ? (CONT_LABELS[chunk.rs] || "Önceki chunk'ın devamı")
        : (REASONS[chunk.rs] || {label: chunk.rs}).label;
      const kindText = isCont ? "· · · teknik sınır — içerik devam ediyor · · ·" : "yeni bölüm";
      tint = marks[k] % 2;
      htmlOut += `<div class="chunkline ${isCont ? "tech" : "struct"}">` +
        `<span class="kind">${kindText}</span>` +
        `<span class="chunkpill" data-chunk="${marks[k]}">` +
        `Chunk ${chunk.num} · ${chunk.n} token · <span class="why">${esc(why)}</span>` +
        (state.contShow && chunk.rt === "TOKEN_BUDGET_CONTINUATION" ? " ⟡" : "") + `</span>` +
        `<span class="rule"></span>`;
      const d = diffByRight[u.i];
      if (state.filter === "diff" && d && diffKey.has(d.a + "|" + d.b)) {
        const glyphs = ARMS.map(a =>
          ARM_LABEL[a][0] + ":" + (d.s[a] ? "✂" : "—")).join(" ");
        htmlOut += `<span class="diffbadge" data-diff="${d.a}|${d.b}">FARK` +
          `<span class="glyphs">${glyphs}</span></span>`;
      }
      htmlOut += `</div>`;
    }
    const at = m[u.i];
    let cls = at === undefined ? "" : (at % 2 === 0 ? "tintA" : "tintB");
    if (at !== undefined && state.contShow) {
      const chunk = armData.chunks[at];
      if (expMembers && expMembers.has(at)) cls += " expmember";
      else if (chunk.g !== null && chunk.g !== undefined) cls += " contedge";
    }
    htmlOut += `<div class="u ${cls}" data-uid="${u.i}"` +
      (at !== undefined ? ` data-uchunk="${at}"` : "") + `>` + unitHtml(u) + `</div>`;
  }
  htmlOut += "</div>";
  $("prespage").innerHTML = htmlOut;

  $("prespage").querySelectorAll(".chunkpill").forEach(el => {
    el.onclick = () => { state.selChunk = Number(el.dataset.chunk); renderPresDetail(); };
  });
  $("prespage").querySelectorAll(".u[data-uchunk]").forEach(el => {
    el.onclick = () => { state.selChunk = Number(el.dataset.uchunk); renderPresDetail(); };
  });
  renderPresDetail();
}

function expansionBudget(){
  const budgets = D().meta.budgets || {};
  return budgets.hard_max_tokens || 1126;
}

// Mirror of amsc.chunk_relations.expand_context: nearest-first, previous
// before next, hard budget, stop at any missing link (a real section
// boundary). Visualization only -- retrieval ranks are untouched.
function simulateExpansion(armData, seedIdx, budget){
  budget = budget === undefined ? expansionBudget() : budget;
  const chunks = armData.chunks;
  if (!chunks[seedIdx]) return null;
  let total = chunks[seedIdx].n;
  const members = [seedIdx];
  let before = seedIdx, after = seedIdx;
  let beforeOpen = true, afterOpen = true;
  while (beforeOpen || afterOpen) {
    let moved = false;
    if (beforeOpen) {
      // The link INTO chunks[before] must itself be a token-budget cut.
      const prev = chunks[before].rt === "TOKEN_BUDGET_CONTINUATION" ? chunks[before].cp : null;
      if (prev === null || prev === undefined) beforeOpen = false;
      else if (total + chunks[prev].n > budget) beforeOpen = false;
      else { members.push(prev); total += chunks[prev].n; before = prev; moved = true; }
    }
    if (afterOpen) {
      const nextRaw = chunks[after].cn;
      const next = (nextRaw !== null && nextRaw !== undefined &&
        chunks[nextRaw].rt === "TOKEN_BUDGET_CONTINUATION") ? nextRaw : null;
      if (next === null) afterOpen = false;
      else if (total + chunks[next].n > budget) afterOpen = false;
      else { members.push(next); total += chunks[next].n; after = next; moved = true; }
    }
    if (!moved) break;
  }
  members.sort((a, b) => a - b);
  return {members, total, budget};
}

function jumpToChunk(idx){
  const chunk = A().chunks[idx];
  state.selChunk = idx;
  if (chunk.pg.length && chunk.pg[0] !== state.page) state.page = chunk.pg[0];
  render();
}

function renderPresDetail(){
  const box = $("presdetail");
  const armData = A();
  const diag = D().meta.diag[state.arm] || {};
  let armNote = "";
  if (state.arm === "hybrid") {
    armNote = `Hybrid kolu: büyük bölümlerin iç kesim noktaları semantik skorla seçilir. ` +
      `Bu koşuda ${diag.arbitrated_boundary_count ?? "?"} bölüm-içi kesimin ` +
      `${diag.arbitration_changed_boundary_count ?? "?"} tanesi açgözlü kesimden farklı seçildi; ` +
      `${diag.h1_fallback_section_count ?? "?"} bölümde uygun aday yoktu. ` +
      `Chunk başına hangi kesimin semantik seçim olduğu artifact'te kayıtlı değildir ve burada iddia edilmez.`;
  } else if (state.arm === "markdown") {
    armNote = `Markdown kolu bölüm yapısına bakmaz: ${diag.chunk_size_tokens ?? 700} token hedefi, ` +
      `${diag.chunk_overlap_tokens ?? 140} token örtüşme.`;
  } else if (state.arm === "agentic") {
    const am = D().agenticMeta || {};
    const s = am.summary || {}, bd = am.diff || {};
    armNote = `Agentic Chunker: yapısal adaylar section başına tek çağrıda oylanır; ` +
      `bu koşuda ${bd.decision_windows ?? s.decision_window_count ?? "?"} karar penceresinin ` +
      `${bd.window_moved ?? s.window_moved_count ?? "?"} tanesinde LLM oyu greedy'den farklı kesim seçti; ` +
      `final chunk sınırı olarak kalan: ${bd.final_boundary_moved ?? s.final_boundary_moved_count ?? "?"}` +
      ` (rejoin ile geri birleşen: ${bd.rejoined_after_agentic_cut ?? s.rejoined_after_agentic_cut_count ?? 0})` +
      (am.model ? ` (model: ${am.model})` : "") +
      `. Ayrı, model-bağımlı bir koşudur; kazanan iddiası yoktur.`;
  } else {
    armNote = "Structure-only kolu her bölümü kendi başlığı altında tutar; yalnız hedef bütçeyi aşan bölümler bölünür.";
  }
  if (state.selChunk === null || !armData.chunks[state.selChunk]) {
    box.innerHTML = `<h3>Chunk detayı</h3><div class="empty">Bir chunk şeridine ya da metnine tıklayın.</div>` +
      `<div class="arminfo">${esc(armNote)}</div>`;
    return;
  }
  const chunk = armData.chunks[state.selChunk];
  const reason = REASONS[chunk.rs] || {label: chunk.rs, sent: ""};
  const prev = chunk.cp, next = chunk.cn;
  const hasLink = (prev !== null && prev !== undefined) || (next !== null && next !== undefined);
  const link = idx => `<button data-jump="${idx}">Chunk ${armData.chunks[idx].num}</button>`;
  const inType = chunk.rt;
  const outType = (next !== null && next !== undefined) ? armData.chunks[next].rt : null;
  const budgetNeighbor =
    (inType === "TOKEN_BUDGET_CONTINUATION") || (outType === "TOKEN_BUDGET_CONTINUATION");
  const expansion = simulateExpansion(armData, state.selChunk);
  const expandable = expansion && expansion.members.length > 1;
  let expLine;
  if (expandable) {
    expLine = `evet — ${expansion.members.map(i => "Chunk " + armData.chunks[i].num).join(" + ")} · ${expansion.total} token ≤ bütçe ${expansion.budget}`;
  } else if (budgetNeighbor) {
    expLine = `hayır — komşu devam chunk'ı bütçeye (${expansionBudget()}) sığmıyor`;
  } else if (hasLink) {
    expLine = `hayır — komşu sınır token-budget değil (${inType || outType})`;
  } else {
    expLine = "hayır — devam bağlantısı yok (bölüm sınırı)";
  }
  box.innerHTML = `<h3>Chunk ${chunk.num}</h3>
    <dl class="kv">
      <dt>Token</dt><dd>${chunk.n}</dd>
      <dt>Başlık</dt><dd>${chunk.hh ? chunk.hh : "<span class='empty'>—</span>"}</dd>
      <dt>Bölüm</dt><dd>${chunk.sd.length ? esc(chunk.sd.join(" › ")) : "<span class='empty'>—</span>"}</dd>
      <dt>Sayfalar</dt><dd>${chunk.pg.join(", ")}</dd>
      <dt>Önceki</dt><dd class="detail-links">${prev !== null && prev !== undefined ? link(prev) + " (devamı bu chunk)" : "<span class='empty'>—</span>"}</dd>
      <dt>Sonraki</dt><dd class="detail-links">${next !== null && next !== undefined ? link(next) + " (bu chunk'ın devamı)" : "<span class='empty'>—</span>"}</dd>
      <dt>İlişki</dt><dd>${inType ? esc(inType) : (outType ? esc(outType) + " (sonrakiyle)" : "<span class='empty'>—</span>")}</dd>
      <dt>Aynı bölüm</dt><dd>${hasLink ? "evet" : "—"}</dd>
      <dt>Sınır nedeni</dt><dd>${esc(reason.label)}</dd>
      ${chunk.llm ? `<dt>LLM kararı</dt><dd>${chunk.llm.m
        ? "sınır LLM oyu ile taşındı" + (chunk.llm.rc ? " (" + esc(chunk.llm.rc) + ")" : "")
        : "pencere değerlendirildi; açgözlü kesim korundu"}</dd>` : ""}
      <dt>Expansion adayı</dt><dd>${esc(expLine)}</dd>
    </dl>
    <div class="reason-sent"><b>${esc(reason.label)}.</b> ${esc(reason.sent || "")}</div>
    <div class="arminfo">${esc(armNote)}</div>`;
  box.querySelectorAll("button[data-jump]").forEach(b => {
    b.onclick = () => jumpToChunk(Number(b.dataset.jump));
  });
}

/* -------- query -------- */
function statusOf(frr){
  if (frr === 1) return {cls:"ok", glyph:"✓", text:"Rank 1"};
  if (frr !== null && frr !== undefined && frr <= 5)
    return {cls:"mid", glyph:"!", text:"Rank " + frr + " — top-5 içinde"};
  return {cls:"miss", glyph:"×", text:"Top-5 dışında"};
}

function chunkPieces(chunkIdx, arm){
  const armData = D().arms[arm];
  const chunk = armData.chunks[chunkIdx];
  const pieces = [];
  const seen = new Set();
  for (const raw of chunk.u) {
    const baseId = raw.split("#")[0];
    if (seen.has(baseId)) continue;
    seen.add(baseId);
    const u = unitById(baseId);
    if (!u) continue;
    const segs = (armData.seg[baseId] || []).filter(s => s[0] === chunkIdx);
    if (!segs.length) { pieces.push({u, text:u.x}); continue; }
    for (const s of segs) pieces.push({u, text:u.x.slice(s[1], s[2])});
  }
  return pieces;
}

function renderedChunk(chunkIdx, arm, evidence){
  const chunk = D().arms[arm].chunks[chunkIdx];
  const evSet = new Set(evidence);
  let out = `<div class="rchunk"><div class="rhead">Chunk ${chunk.num} · ${chunk.n} token · sayfa ${chunk.pg.join(", ")}</div>`;
  if (chunk.hh) out += `<div class="piece"><b>${chunk.hh}</b></div>`;
  for (const piece of chunkPieces(chunkIdx, arm)) {
    const body = piece.text === piece.u.x ? unitHtml(piece.u)
      : "<p>" + esc(piece.text) + "</p>";
    out += `<div class="piece">` + (evSet.has(piece.u.i) ? "<mark>" + body + "</mark>" : body) + `</div>`;
  }
  return out + "</div>";
}

function renderQuery(){
  const gold = D().gold;
  const sel = $("querysel");
  // The agentic column appears only when its tree carries query results
  // (after amsc.agentic_benchmark); the frozen three columns never move.
  const qArms = ARMS.concat(
    hasAgentic() && Object.keys(D().arms.agentic.q).length ? ["agentic"] : []);
  if (state.query === null || !gold.some(g => g.id === state.query)) state.query = gold[0] && gold[0].id;
  sel.innerHTML = gold.map(g => {
    const worst = Math.max(...qArms.map(a => {
      const f = (D().arms[a].q[g.id] || {}).f;
      return f === null || f === undefined ? 9 : f;
    }));
    const mark = worst === 1 ? "✓" : worst <= 5 ? "!" : "×";
    return `<option value="${g.id}">${mark} ${g.id} — ${esc(g.q)}</option>`;
  }).join("");
  sel.value = state.query;
  sel.onchange = () => { state.query = sel.value; render(); };

  const g = gold.find(x => x.id === state.query);
  if (!g) { $("queryhead").innerHTML = ""; $("querycols").innerHTML = ""; return; }

  const evHtml = g.ev.map(id => {
    const u = unitById(id);
    return u ? `<div>${unitHtml(u)}</div>` : "";
  }).join("");
  $("queryhead").innerHTML = `<div class="qhead">
    <div class="qq">${esc(g.q)}</div>
    ${g.a ? `<div class="qa">Beklenen cevap: ${esc(g.a)}</div>` : ""}
    <div class="qmeta">${g.id} · kanıt türü: ${esc(g.ty || "—")} · zorluk: ${esc(g.df || "—")} · kanıt sayfaları: ${g.pg.join(", ")}</div>
    <div class="evbox"><div class="evlabel">Gold kanıt (${g.ev.length} unit)</div>${evHtml}</div>
  </div>`;

  $("querycols").innerHTML = qArms.map(arm => {
    const qres = D().arms[arm].q[g.id];
    if (!qres) return `<div class="qcol"><div class="armname">${esc(armLabel(arm))}</div><div class="covline">sonuç yok</div></div>`;
    const st = statusOf(qres.f);
    const relevant = qres.res.find(r => r.r === qres.f && r.m.length);
    let body = "";
    if (relevant && relevant.c !== null) {
      body = renderedChunk(relevant.c, arm, g.ev);
    } else {
      body = `<div class="rchunk"><div class="rhead">Top-5 içinde gold kanıt taşıyan chunk yok.</div></div>`;
    }
    const rows = qres.res.map(r => {
      const chunk = r.c === null ? null : D().arms[arm].chunks[r.c];
      const matched = r.m.length
        ? `<span class="mt">✓ ${r.m.length} kanıt unit</span>` : "";
      return `<div class="row"><span class="rk">#${r.r}</span>` +
        `<span>${chunk ? "Chunk " + chunk.num : "—"}</span>` +
        `<span>s.${r.pg.join(",")}</span><span>${r.tk} tok</span>${matched}</div>`;
    }).join("");
    return `<div class="qcol">
      <div class="armname">${esc(armLabel(arm))} <span class="status ${st.cls}">${st.glyph} ${st.text}</span></div>
      <div class="covline">kanıt kapsaması: ${qres.cov === null || qres.cov === undefined ? "—" : (qres.cov * 100).toFixed(0) + "%"}</div>
      ${body}
      <details class="top5"><summary>Top-5 listesi</summary>${rows}</details>
      <div class="qlink"><button data-goto="${arm}">Bu kolun chunk sınırlarını sayfada gör →</button></div>
    </div>`;
  }).join("");

  $("querycols").querySelectorAll("button[data-goto]").forEach(b => {
    b.onclick = () => {
      state.mode = "presentation";
      state.arm = b.dataset.goto;
      state.filter = "all";
      state.page = g.pg[0] || D().pages[0];
      render();
      g.ev.forEach(id => {
        const el = document.querySelector(`.u[data-uid="${id}"]`);
        if (el) el.classList.add("evflash");
      });
      const first = document.querySelector(".u.evflash");
      if (first) first.scrollIntoView({block:"center"});
    };
  });
}

/* -------- debug -------- */
function renderDebug(){
  const units = pageUnits(state.page);
  $("dbglist").innerHTML = units.map(u => {
    const chips = [
      `<span class="chip">${u.i}</span>`,
      `<span class="chip">${u.t}</span>`,
      u.r ? `<span class="chip role">${u.r}</span>` : "",
      u.o === true ? `<span class="chip opens">opens_section</span>` :
        u.o === false ? `<span class="chip noopen">opens=false</span>` : "",
      u.l !== null && u.l !== undefined ? `<span class="chip">level ${u.l}</span>` : "",
      u.b !== null && u.b !== undefined ? `<span class="chip">block ${u.b}</span>` : "",
      `<span class="chip">p.${u.p}</span>`
    ].join("");
    const rows = ARMS.map(arm => {
      const armData = D().arms[arm];
      const segs = armData.seg[u.i] || [];
      if (!segs.length) return `<tr><td>${esc(ARM_LABEL[arm])}</td><td colspan="3">unmapped</td></tr>`;
      return segs.map(s => {
        const chunk = armData.chunks[s[0]];
        const frag = chunk.u.find(x => x.split("#")[0] === u.i && x.includes("#"));
        return `<tr><td>${esc(ARM_LABEL[arm])}</td><td>${chunk.id}${frag ? " · " + frag.split("#")[1] : ""}</td>` +
          `<td>${s[1]}–${s[2]}</td><td>${s[3]}</td></tr>`;
      }).join("");
    }).join("");
    return `<div class="dbgunit${state.selUnit === u.i ? " sel" : ""}" data-uid="${u.i}">
      <div class="head">${chips}</div>
      <div class="path">${esc(JSON.stringify(u.s))}</div>
      <div class="txt">${esc(u.x)}</div>
      <table class="dbgtable"><tr><th>arm</th><th>chunk · fragment</th><th>offset</th><th>method</th></tr>${rows}</table>
    </div>`;
  }).join("");
  $("dbglist").querySelectorAll(".dbgunit").forEach(el => {
    el.onclick = () => { state.selUnit = el.dataset.uid; renderInspector();
      $("dbglist").querySelectorAll(".dbgunit").forEach(x =>
        x.classList.toggle("sel", x.dataset.uid === state.selUnit)); };
  });
  renderInspector();
}

function renderInspector(){
  const box = $("inspector");
  const u = state.selUnit && unitById(state.selUnit);
  if (!u) { box.innerHTML = "<b>Unit inspector</b><div style='color:var(--muted);margin-top:8px'>Bir unit'e tıklayın.</div>"; return; }
  const fields = {
    unit_id: u.i, type: u.t, page: u.p, semantic_role: u.r,
    opens_section: u.o, heading_level: u.l, block: u.b, section_path: u.s
  };
  box.innerHTML = `<b>Unit inspector — ${esc(u.i)}</b>` +
    `<pre>${esc(JSON.stringify(fields, null, 1))}</pre>` +
    `<div style="margin-top:8px;font-weight:600">Ham metin</div><pre>${esc(u.x)}</pre>`;
}

/* -------- benchmark -------- */
function fmt(v, digits){ return v === null || v === undefined ? "—" : Number(v).toFixed(digits === undefined ? 4 : digits); }
function benchTable(title, rows, columns, higherBetter){
  // rows: [{arm, values:{col:v}}]
  const best = {};
  for (const col of columns) {
    const vals = rows.map(r => r.values[col.k]).filter(v => v !== null && v !== undefined);
    if (vals.length) best[col.k] = higherBetter === false ? Math.min(...vals) : Math.max(...vals);
  }
  let out = `<h2>${esc(title)}</h2><div class="scroll" style="overflow-x:auto"><table class="btable"><tr><th>Yöntem</th>` +
    columns.map(c => `<th>${esc(c.t)}</th>`).join("") + "</tr>";
  for (const row of rows) {
    out += `<tr><td>${esc(row.arm)}</td>` + columns.map(c => {
      const v = row.values[c.k];
      const cls = best[c.k] !== undefined && v === best[c.k] && rows.length > 1 ? "best" : "";
      return `<td class="${cls}">${fmt(v, c.d)}</td>`;
    }).join("") + "</tr>";
  }
  return out + "</table></div>";
}

function renderBenchmark(){
  const doc = D(), meta = doc.meta;
  const arms = doc.arms;
  let out = "";

  out += `<div class="guard">${esc(meta.guard || "")}</div>`;
  out += `<div class="cards">
    <div class="card"><div class="v">${meta.queryCount}</div><div class="k">gold sorgu</div></div>` +
    ARMS.map(a => `<div class="card"><div class="v">${arms[a].ret.chunk_count}</div><div class="k">${esc(ARM_LABEL[a])} chunk</div></div>`).join("") +
    `<div class="card"><div class="v">${meta.parserFindings ?? "—"}</div><div class="k">parser taban bulgusu (kola ait değil)</div></div>
  </div>`;

  const retCols = [
    {k:"hit_at_1", t:"Hit@1"}, {k:"hit_at_3", t:"Hit@3"}, {k:"hit_at_5", t:"Hit@5"},
    {k:"mrr", t:"MRR"}, {k:"evidence_coverage_at_5", t:"Kanıt kaps.@5"},
    {k:"source_evidence_coverage", t:"Kaynak kapsama"}
  ];
  out += benchTable("Retrieval — birincil gold set", ARMS.map(a => ({
    arm: ARM_LABEL[a], values: arms[a].ret
  })), retCols);
  out += `<div class="legend">● = en iyi gözlenen değer (bu koşuda). Tek bir yöntem her metrikte önde değildir; sonuçlar PoC parametreleriyle alınmıştır.</div>`;

  const et = meta.etypes;
  const etKeys = Object.keys(et).sort();
  if (etKeys.length) {
    out += `<h2>Kanıt türüne göre Hit@5</h2><div style="overflow-x:auto"><table class="btable"><tr><th>Tür</th><th>Sorgu</th>` +
      ARMS.map(a => `<th>${esc(ARM_LABEL[a])}</th>`).join("") + "</tr>" +
      etKeys.map(k => `<tr><td>${esc(k)}</td><td>${et[k].query_count}</td>` +
        ARMS.map(a => `<td>${et[k][a] ?? "—"}</td>`).join("") + "</tr>").join("") +
      "</table></div>";
  }

  const qc = meta.qcomp;
  if (qc && qc.pairwise_hit_at_5) {
    out += `<h2>Sorgu düzeyi karşılaştırma (Hit@5)</h2><div class="pairlists">`;
    for (const [pair, sides] of Object.entries(qc.pairwise_hit_at_5)) {
      const nice = pair.replace(/_vs_/, " ↔ ").replace(/_hit_at_5/, "");
      out += `<div class="pl"><b>${esc(nice)}</b><br>kazanılan: ${sides.gained.length ? sides.gained.map(q => `<span class="qidchip" data-q="${q}">${q}</span>`).join(" ") : "—"}<br>` +
        `kaybedilen: ${sides.lost.length ? sides.lost.map(q => `<span class="qidchip" data-q="${q}">${q}</span>`).join(" ") : "—"}</div>`;
    }
    out += `<div class="pl"><b>Üç yöntemin de kaçırdığı</b><br>` +
      ((qc.missed_by_all_at_5 || []).map(q => `<span class="qidchip" data-q="${q}">${q}</span>`).join(" ") || "—") + `</div></div>`;
  }

  const sqCols = [
    {k:"chunk_count", t:"Chunk", d:0}, {k:"tok_med", t:"Token medyan", d:1},
    {k:"tok_p90", t:"p90", d:0}, {k:"tok_max", t:"maks", d:0},
    {k:"below_min", t:"<160", d:0}, {k:"above_soft", t:">900", d:0},
    {k:"heading_led", t:"Başlıkla açılan", d:4}, {k:"multi_sec", t:"Çok bölümlü", d:0},
    {k:"mid_sent", t:"Cümle ortası kesim", d:0}, {k:"tab_frag", t:"Tablo bölünmesi", d:0},
    {k:"list_frag", t:"Liste bölünmesi", d:0}, {k:"dup_mass", t:"Tekrarlanan kütle", d:4}
  ];
  out += benchTable("Yapısal kalite (chunk türevli)", ARMS.map(a => {
    const s = arms[a].sq;
    return {arm: ARM_LABEL[a], values: {
      chunk_count: s.chunk_count,
      tok_med: s.token_count && s.token_count.median,
      tok_p90: s.token_count && s.token_count.p90_nearest_rank,
      tok_max: s.token_count && s.token_count.max,
      below_min: s.size_bands && s.size_bands.below_min_count,
      above_soft: s.size_bands && s.size_bands.above_soft_max_count,
      heading_led: s.structure && s.structure.heading_led_ratio,
      multi_sec: s.structure && s.structure.multi_section_count,
      mid_sent: s.fragmentation && s.fragmentation.mid_sentence_split_count,
      tab_frag: s.fragmentation && s.fragmentation.table_units_fragmented,
      list_frag: s.fragmentation && s.fragmentation.list_units_fragmented,
      dup_mass: s.duplication && s.duplication.duplicate_token_mass_ratio
    }};
  }), sqCols.map(c => ({...c, t:c.t})), undefined);
  out += `<div class="legend">Bu tabloda "en iyi" işareti yoktur: metriklerin bir kısmı yöntem tanımının sonucudur (örn. markdown örtüşmesi tekrarlanan kütleyi yapısal olarak yükseltir).</div>`;

  const timing = meta.timing || {};
  const timCols = [
    {k:"chunk", t:"Chunking medyan (ms)", d:1}, {k:"index", t:"İndeks (ms)", d:1},
    {k:"p50", t:"Arama p50 (ms)", d:2}, {k:"p90", t:"Arama p90 (ms)", d:2},
    {k:"cold", t:"Cold embedding (ms)", d:0}
  ];
  out += benchTable("Zamanlama", ARMS.map(a => {
    const t = timing[a] || arms[a].tim || {};
    return {arm: ARM_LABEL[a], values: {
      chunk: t.chunk_ms_median, index: t.index_build_ms,
      p50: t.search_p50_ms, p90: t.search_p90_ms,
      cold: t.cold ? t.cold.chunk_ms_cold : null
    }};
  }), timCols, false);
  out += `<div class="legend">Cold sütunu yalnız Hybrid için anlamlıdır (boundary-embedding önbelleği boşken). Markdown ve Structure-only model yüklemez; cold ≡ warm.</div>`;

  const sec = meta.secondary;
  if (sec && sec.metrics) {
    out += `<details class="secgold"><summary>İkincil gold set (${esc((sec.gold_queries || "").split("/").pop() || "v1")})</summary>`;
    out += benchTable("Retrieval — ikincil set", ARMS.map(a => ({
      arm: ARM_LABEL[a], values: sec.metrics[a] || {}
    })), retCols) + "</details>";
  }

  // The agentic arm never enters the frozen tables above: it is a separate,
  // model-dependent run and is shown in its own clearly-labelled panel.
  const ag = arms.agentic;
  if (ag) {
    const am = doc.agenticMeta || {};
    const s = am.summary || {}, bd = am.diff || {};
    out += `<h2>Agentic Chunker — ayrı koşu</h2>`;
    out += `<div class="guard">Model-bağımlı sonuç (yalnız replay-deterministic); ` +
      `frozen üç kolun karşılaştırmasına dahil değildir ve kazanan ilan edilmez. ` +
      `Model: ${esc(am.model || "—")} · mod: ${esc(am.mode || "—")}.</div>`;
    out += `<div class="cards">
      <div class="card"><div class="v">${ag.chunks.length}</div><div class="k">Agentic chunk</div></div>
      <div class="card"><div class="v">${bd.decision_windows ?? s.decision_window_count ?? "—"}</div><div class="k">karar penceresi</div></div>
      <div class="card"><div class="v">${bd.window_moved ?? s.window_moved_count ?? "—"}</div><div class="k">pencere düzeyinde farklı seçim</div></div>
      <div class="card"><div class="v">${bd.final_boundary_moved ?? s.final_boundary_moved_count ?? "—"}</div><div class="k">final chunk sınırı taşınan</div></div>
      <div class="card"><div class="v">${bd.rejoined_after_agentic_cut ?? s.rejoined_after_agentic_cut_count ?? "—"}</div><div class="k">rejoin ile geri birleşen</div></div>
      <div class="card"><div class="v">${s.provider_call_count ?? "—"}</div><div class="k">provider çağrısı</div></div>
    </div>`;
    if (ag.ret) {
      out += benchTable("Retrieval — Agentic (ayrı koşu, aynı gold + BM25 ayarları)",
        [{arm: armLabel("agentic"), values: ag.ret}], retCols);
      out += `<div class="legend">Bu tablo tek satırdır ve frozen üçlü tablodaki "en iyi" işaretlerine katılmaz; yan yana okuma yaparken model bağımlılığı ve tek koşu olduğu unutulmamalıdır.</div>`;
    } else {
      out += `<div class="legend">Bu ağaçta agentic retrieval değerlendirmesi yok — amsc.agentic_benchmark henüz koşulmamış.</div>`;
    }
  }

  $("view-benchmark").innerHTML = out;
  $("view-benchmark").querySelectorAll(".qidchip[data-q]").forEach(el => {
    el.onclick = () => { state.mode = "query"; state.query = el.dataset.q; render(); };
  });
}

/* -------- shell -------- */
function render(){
  syncBar();
  for (const mode of ["presentation","query","debug","benchmark"]) {
    $("view-" + mode).classList.toggle("hidden", state.mode !== mode);
  }
  if (state.mode === "presentation") renderPresentation();
  else if (state.mode === "query") renderQuery();
  else if (state.mode === "debug") renderDebug();
  else renderBenchmark();
  $("foot").textContent = D().label + " · canonical " +
    (D().meta.canonicalSha || "").slice(0, 16) + "… · " + (D().meta.status || "") +
    " · fark tanımı: ardışık iki içerik unit'i arasında chunk sınırı olup olmadığında üç yöntemin uyuşmadığı noktalar";
}
initBar();
render();
</script>
</body>
</html>
"""


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
