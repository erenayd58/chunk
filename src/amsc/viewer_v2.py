"""Viewer v2 -- the Chunking + RAG PoC as one self-contained HTML product.

Reads completed artifact trees and emits a single offline HTML file with four
modes, each a level of the same product:

* **Sunum** -- what we did and what the difference is: the four chunking
  methods explained, the same page of a document compared across chunkers,
  every boundary with a human-language reason, and the Standard vs Deep
  Analysis results in a few numbers.
* **Sorgu** -- how it works in use: the frozen gold-query retrieval view
  (offline) and, when served by :mod:`amsc.viewer_server`, a live
  "ask the document" chat over the same chunks with source cards.
* **Debug** -- why the system decided what it decided: canonical units,
  section paths, mappings, the Deep Analysis decision trail (Standard cut,
  proposed cut, final cut, verifier verdict, smells before/after), parser
  findings and representation ceilings.
* **Benchmark** -- what the measurements say: the frozen three-arm
  benchmark untouched, and a separate, clearly-labelled Deep Analysis panel
  with structural, retrieval, LLM-usage and latency numbers.

Inputs, per document:

* ``--benchmark DOC=DIR`` -- a frozen ``amsc.chunk_benchmark`` tree (three
  arms, gold queries, pinned canonical). Optional when ``--deep`` is given.
* ``--deep DOC=DIR`` -- an ``amsc.deep_run`` tree packaged by
  ``amsc.deep_arm`` (``arm/``, ``standard/``, ``boundary-decisions.json``).
  Adds the Agentic Chunker (Deep Analysis) as the fourth arm, or, without a
  benchmark tree, builds a Standard-vs-Deep document on its own.
* ``--agentic DOC=DIR`` -- the earlier ``amsc.agentic_chunker`` research
  tree, kept for provenance; it fills the same fourth-arm slot with its own
  reduced attribution and cannot be combined with ``--deep`` for one document.

Nothing is recomputed and nothing upstream is touched: the module is a pure
reader that verifies every tree's canonical pin. Chunk text is not embedded;
it is reconstructed from the canonical unit texts through the mapping
segments. Beside the HTML it writes ``catalog.json`` -- the documents, arms
and chunk files the HTML shows -- which is what the chat server serves, so
the live chat and the page can never disagree about which chunks exist.

Every derived value is deterministic. **Boundary reasons** are restricted to
what the artifacts record: a section change, a label seam, a size split, a
markdown overlap; the Deep arm additionally carries the decision story
``amsc.deep_arm`` derived (origin of each final cut, the smells a moved cut
removed, verifier verdicts). **The differences filter** is defined over
consecutive content units (headings excluded, because two arms leave them
out of ``unit_ids``): a pair is a difference point when the three frozen
arms disagree on whether a chunk boundary falls between the two units.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import methods
from .chunk_relations import continuation_groups, derive_continuations
from .viewer_v2_template import TEMPLATE

#: The frozen benchmark's three arms, in the benchmark's order, and the four
#: product methods -- both read from the registry so this reader cannot
#: disagree with the builders and the console about what a method is called.
ARM_ORDER = methods.benchmark_arms()
PRODUCT_ARM_ORDER = methods.ORDER

ARM_LABELS = {
    "markdown": "Markdown",
    "hybrid": "Hybrid",
    "structure-only": "Structure-only",
    "agentic": "Agentic Chunker",
}

DOC_LABELS = {"kkb-2024": "KKB 2024", "kkb-2022": "KKB 2022", "arcelik-2024": "Arçelik 2024"}

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
#: A packaged Deep arm needs these; retrieval files are optional (no gold).
REQUIRED_DEEP_ARM_FILES = ("manifest.json", "chunks.jsonl", "mapping.json", "structural_quality.json")

#: List prices observed on the reference endpoint on 2026-08-29, USD per
#: million tokens, used only for the "approximate cost" line. Not a claim
#: about any deployment's cost; the numbers beside it are the real ones.
REFERENCE_PRICE_PER_M = {"prompt": 0.04815, "completion": 0.19305, "embedding": 0.01}
#: Characters per cl100k token measured on the KKB/Arçelik canonicals.
CHARS_PER_TOKEN = 2.45

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


def _optional_json(path: Path) -> Any:
    return _load_json(path) if path.is_file() else None


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


def _segments_by_unit(mapping: Mapping[str, Any], chunk_index: Mapping[str, int]) -> dict[str, list]:
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
    return segments


def _chunk_entries(chunks_raw: Sequence[dict]) -> list[dict]:
    return [
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
            "u": chunk.get("fragment_unit_ids") or chunk["unit_ids"],
        }
        for chunk in chunks_raw
    ]


def _attach_links(chunks: list[dict], chunks_raw: Sequence[dict], kind: str) -> None:
    # Continuation links -- the derived relationship layer, computed by
    # amsc.chunk_relations (single source of truth) over the same frozen
    # rows. ``cp``/``cn`` carry every same-section link so the detail panel
    # can name its type; ``g`` (the expansion-chain group) is built from
    # TOKEN_BUDGET_CONTINUATION links only, because only those are walked
    # by the local expansion.
    links = derive_continuations(chunks_raw, kind=kind)
    budget_links = [
        link for link in links if link["relation_type"] == "TOKEN_BUDGET_CONTINUATION"
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


def _query_entries(rows: Sequence[dict], chunk_index: Mapping[str, int]) -> dict[str, dict]:
    queries: dict[str, dict] = {}
    for row in rows:
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
    return queries


def _load_arm_dir(
    arm_dir: Path,
    *,
    kind: str,
    units_by_id: Mapping[str, dict],
    require_retrieval: bool,
) -> tuple[dict, list[dict]]:
    """One arm from a directory holding chunks + mapping (+ retrieval files)."""
    names = REQUIRED_ARM_FILES if require_retrieval else ("chunks.jsonl", "mapping.json")
    for name in names:
        _require(arm_dir / name)
    chunks_raw = _load_jsonl(arm_dir / "chunks.jsonl")
    mapping = _load_json(arm_dir / "mapping.json")
    chunk_index = {chunk["chunk_id"]: i for i, chunk in enumerate(chunks_raw)}
    segments = _segments_by_unit(mapping, chunk_index)
    chunks = _chunk_entries(chunks_raw)
    for index, chunk in enumerate(chunks):
        chunk["rs"] = _boundary_reason(kind, chunks, index, units_by_id, segments)
    _attach_links(chunks, chunks_raw, kind)
    query_path = arm_dir / "query-results.jsonl"
    queries = _query_entries(_load_jsonl(query_path), chunk_index) if query_path.is_file() else {}
    arm = {
        "kind": kind,
        "chunks": chunks,
        "m": _membership(chunks_raw),
        "seg": segments,
        "q": queries,
        "ret": _optional_json(arm_dir / "retrieval.json"),
        "sq": _optional_json(arm_dir / "structural_quality.json"),
        "tim": _optional_json(arm_dir / "timing.json"),
        "health": mapping.get("health") or {},
    }
    return arm, chunks_raw


def _load_agentic_arm(
    agentic_dir: Path, expected_sha: str, units_by_id: Mapping[str, dict]
) -> tuple[dict, dict]:
    """The earlier research arm, read from an ``amsc.agentic_chunker`` tree.

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
    kind = "agentic_structure_llm"
    arm, _chunks_raw = _load_arm_dir(
        agentic_dir / "agentic", kind=kind, units_by_id=units_by_id, require_retrieval=False
    )
    summary = _load_json(agentic_dir / "judge" / "summary.json")
    diff = _load_json(agentic_dir / "boundary-diff.json")
    chunks = arm["chunks"]

    # LLM boundary attribution -- recorded in the audit, so the viewer may
    # show it (unlike hybrid, whose benchmark records no attribution). The
    # window's boundary is the cut after ``chosen_after_unit_id``; the chunk
    # that STARTS at that boundary carries the flag.
    consulted: dict[str, dict] = {}
    for window in diff.get("windows") or []:
        after = _base(window["chosen_after_unit_id"])
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
        consulted[after] = {"m": 1 if moved else 0, "rc": reason, "fb": window.get("fallback")}
    for index in range(1, len(chunks)):
        previous = chunks[index - 1]
        if not previous["u"]:
            continue
        flag = consulted.get(_base(previous["u"][-1]))
        if flag is not None:
            chunks[index]["llm"] = flag

    meta = {
        "mode": manifest.get("mode"),
        "model": manifest.get("model_id"),
        "summary": summary,
        "diff": diff.get("summary") or {},
    }
    return arm, meta


def _compact_story(story: Mapping[str, Any]) -> dict:
    sections = []
    for section in story.get("sections") or []:
        sections.append(
            {
                "i": section["section_index"],
                "h": heading_plain(section["heading"]) if section.get("heading") else None,
                "pg": section.get("pages") or [],
                "tt": section.get("tokens"),
                "st": section["status"],
                "cons": bool(section.get("llm_consulted")),
                "rv": section.get("reverted"),
                "vt": section.get("verdict_tiered"),
                "sz": bool(section.get("size_traded")),
                "std": section.get("standard_cuts_after") or [],
                "det": section.get("deterministic_cuts_after") or [],
                "fin": section.get("final_cuts_after") or [],
                "sm": section.get("smells") or {},
                "gr": [
                    {
                        "u": group["unit_ids"],
                        "sc": group["standard_cuts_after"],
                        "fc": group["final_cuts_after"],
                        "rm": group["removed_smells"],
                        "in": group["introduced_smells"],
                        "or": group["origin"],
                        "se": {
                            k: group["size_effect"][k] for k in ("below_min", "above_soft_max")
                        } if group.get("size_effect") else None,
                    }
                    for group in section.get("change_groups") or []
                ],
                "pr": [
                    {"k": p.get("group_key"), "a": bool(p.get("accepted")), "r": p.get("reason"), "u": p.get("unit_ids") or []}
                    for p in section.get("llm_proposals") or []
                ],
            }
        )
    return {"counts": story.get("counts") or {}, "sections": sections}


def _sum_chars(path: Path, key: str) -> int:
    if not path.is_file():
        return 0
    total = 0
    for row in _load_jsonl(path):
        value = row.get(key)
        total += len(value) if isinstance(value, str) else int(value or 0)
    return total


def _load_deep_arm(
    deep_dir: Path, expected_sha: str | None, units_by_id: Mapping[str, dict]
) -> tuple[dict, dict | None, dict, dict]:
    """The Deep Analysis arm from a packaged ``amsc.deep_run`` tree.

    Returns (agentic arm, standard arm or None, deep meta, compact story).
    """
    deep_dir = Path(deep_dir)
    arm_dir = deep_dir / "arm"
    for name in REQUIRED_DEEP_ARM_FILES:
        _require(arm_dir / name)
    manifest = _load_json(arm_dir / "manifest.json")
    if manifest.get("arm_kind") != "deep_analysis":
        raise ValueError(f"{arm_dir} is not a packaged Deep Analysis arm (run amsc.deep_arm)")
    if expected_sha and manifest.get("canonical_sha256") != expected_sha:
        raise ValueError(
            f"{deep_dir} was packaged from a different canonical corpus than "
            "the benchmark tree; the viewer refuses to pair them"
        )
    summary = _load_json(deep_dir / "summary.json")
    story_raw = _load_json(deep_dir / "boundary-decisions.json")
    quality = _load_json(deep_dir / "quality-vs-standard.json")

    arm, _rows = _load_arm_dir(
        arm_dir, kind="deep_analysis", units_by_id=units_by_id, require_retrieval=False
    )
    standard_arm: dict | None = None
    if (deep_dir / "standard" / "chunks.jsonl").is_file():
        standard_arm, _srows = _load_arm_dir(
            deep_dir / "standard", kind="structure_first", units_by_id=units_by_id, require_retrieval=False
        )

    by_cut_after = story_raw.get("by_cut_after") or {}
    # Every boundary the story recorded, by the unit it cuts after. A change
    # group's status describes the group; a reader pointing at one boundary is
    # asking about that boundary, so its own record answers -- which layer
    # placed or removed it, and which smells it carried.
    cut_origin: dict[str, str] = {}
    cut_smells: dict[str, list] = {}
    for section in story_raw.get("sections") or []:
        for boundary in section.get("boundaries") or []:
            key = boundary.get("cut_after_unit_id")
            if not key:
                continue
            if boundary.get("origin"):
                cut_origin[key] = boundary["origin"]
            if boundary.get("smells"):
                cut_smells[key] = list(boundary["smells"])
    merged_at: dict[str, dict] = {}
    std_changed: dict[str, dict] = {}
    for key, record in by_cut_after.items():
        if key.startswith("merge:"):
            merged_at[key[len("merge:"):]] = record
        for cut in record.get("standard_cuts_after") or []:
            # "removed_by_llm" / "removed_by_deterministic" is this cut's own
            # actor; the group status is the fallback for older trees.
            own = cut_origin.get(cut)
            origin = ("llm" if own == "removed_by_llm" else "deterministic") if own else (
                "llm" if record.get("status") in ("llm_accepted", "llm_merged") else "deterministic")
            std_changed[cut] = {
                "status": "std_changed",
                "removed_smells": record.get("removed_smells") or [],
                "cut_smells": cut_smells.get(cut) or [],
                "origin": origin,
                "size_effect": record.get("size_effect"),
            }
    chunks = arm["chunks"]
    for index, chunk in enumerate(chunks):
        if index >= 1 and chunks[index - 1]["u"]:
            cut_after = chunks[index - 1]["u"][-1]
            decision = by_cut_after.get(cut_after)
            if decision is not None:
                chunk["dec"] = {
                    k: v for k, v in decision.items()
                    if k in ("status", "removed_smells", "introduced_smells", "size_effect",
                             "llm_reverted", "verifier", "inside_unit", "section_index", "smells")
                }
                # A group whose *other* cut the model placed does not make this
                # cut the model's: the boundary's own origin decides.
                own = cut_origin.get(cut_after)
                if own in ("deterministic", "llm") and chunk["dec"].get("status") in ("det_moved", "llm_accepted"):
                    chunk["dec"]["status"] = "llm_accepted" if own == "llm" else "det_moved"
                if cut_smells.get(cut_after):
                    chunk["dec"]["cut_smells"] = cut_smells[cut_after]
        merged = [merged_at[u] for u in chunk["u"] if u in merged_at]
        if merged:
            chunk["mg"] = [
                {k: v for k, v in record.items() if k in ("status", "removed_smells", "size_effect", "standard_cuts_after")}
                for record in merged
            ]
    section_of: dict[str, int] = {}
    for section in story_raw.get("sections") or []:
        for unit_id in section.get("piece_unit_ids") or []:
            section_of[_base(unit_id)] = section["section_index"]
    for chunk in chunks:
        if chunk["u"]:
            chunk["si"] = section_of.get(_base(chunk["u"][0]))

    story = _compact_story(story_raw)
    story["sectionOf"] = section_of
    story["stdChanged"] = std_changed

    proposer_calls = deep_dir / "proposer" / "calls.jsonl"
    verifier_calls = deep_dir / "verifier" / "calls.jsonl"
    prompt_chars = _sum_chars(proposer_calls, "prompt_chars") + _sum_chars(verifier_calls, "prompt_chars")
    response_chars = _sum_chars(deep_dir / "proposer" / "responses.jsonl", "response") + _sum_chars(
        deep_dir / "verifier" / "responses.jsonl", "response"
    )
    est_prompt = round(prompt_chars / CHARS_PER_TOKEN)
    est_completion = round(response_chars / CHARS_PER_TOKEN)
    proposer = summary.get("proposer") or {}
    verifier = summary.get("verifier") or {}
    call_counts = {
        "proposer": int(proposer.get("call_count") or 0),
        "verifier": 2 * int(verifier.get("group_count") or 0),
    }
    call_counts["total"] = call_counts["proposer"] + call_counts["verifier"]
    meta = {
        "mode": summary.get("mode"),
        "status": summary.get("status"),
        "model": summary.get("model_id") or manifest.get("model_id"),
        "verifierModel": summary.get("verifier_model_id") or manifest.get("verifier_model_id"),
        "promptVersion": summary.get("prompt_template_version"),
        "config": summary.get("config") or {},
        "chunkCount": summary.get("chunk_count") or {},
        "smellTotal": summary.get("smell_total") or {},
        "totals": summary.get("totals") or {},
        "verdictsTiered": summary.get("verdicts_tiered") or {},
        "regressions": summary.get("structural_regression_count"),
        "strictRegressions": summary.get("strict_regression_count"),
        "sizeTrades": summary.get("size_trade_count"),
        "changeGroups": summary.get("change_group_count"),
        "selection": summary.get("selection") or {},
        "llmEffect": summary.get("llm_effect") or {},
        "proposer": proposer,
        "verifier": verifier,
        "timing": summary.get("timing_seconds") or {},
        "calls": call_counts,
        "chars": {"prompt": prompt_chars, "response": response_chars},
        "estTokens": {"prompt": est_prompt, "completion": est_completion},
        "estCostUsd": round(
            est_prompt / 1e6 * REFERENCE_PRICE_PER_M["prompt"]
            + est_completion / 1e6 * REFERENCE_PRICE_PER_M["completion"],
            4,
        ),
        "storyCounts": story_raw.get("counts") or {},
        "sectionCount": quality.get("section_count"),
        "retrieval": {
            "deep": arm["ret"],
            "standard": standard_arm["ret"] if standard_arm else None,
        },
        "hasRetrieval": bool(manifest.get("has_retrieval")),
        "frozenTree": manifest.get("frozen_tree"),
        "tuning": (summary.get("claim_discipline") or {}).get("tuning_status"),
    }
    return arm, standard_arm, meta, story


def _parser_findings(units_raw: Sequence[dict]) -> list[dict]:
    from .structural_qa import lint

    report = lint(list(units_raw), [])
    return [
        {
            "r": finding.rule,
            "c": finding.confidence,
            "t": finding.target_id,
            "p": finding.page,
            "why": finding.reason,
            "ev": (finding.evidence or "")[:160],
        }
        for finding in sorted(report.findings, key=lambda f: f.sort_key())
    ]


def _oversized_units(units_raw: Sequence[dict], hard_max_tokens: int) -> dict[str, int]:
    """Units no partition can keep whole: token count above the hard cap."""
    candidates = [unit for unit in units_raw if len(unit["text"]) > hard_max_tokens]
    if not candidates:
        return {}
    from .tokenization import TiktokenTokenCounter

    counter = TiktokenTokenCounter("cl100k_base")
    oversized: dict[str, int] = {}
    for unit in candidates:
        tokens = counter.count(unit["text"])
        if tokens > hard_max_tokens:
            oversized[unit["unit_id"]] = tokens
    return oversized


#: Arm kinds a packaged directory may declare, so an extra arm cannot be
#: labelled with a mechanism the boundary-reason reader does not know. A
#: live view of the registry: a method registered there is accepted here.
ARM_KINDS = methods.KINDS


def load_corpus(
    benchmark_dir: Path | None,
    root: Path,
    agentic_dir: Path | None = None,
    deep_dir: Path | None = None,
    label: str | None = None,
    extra_arm_dirs: Mapping[str, Path] | None = None,
    units_path: Path | None = None,
) -> dict:
    """Read one document's trees plus its pinned canonical into viewer data.

    ``extra_arm_dirs`` names further arms packaged over the *same* canonical --
    the live workspace runs several chunkers on one parse and packages each
    with the same writer the benchmark uses. They are read with the reduced
    contract (chunks + mapping, retrieval optional), because a document with
    no gold set has no retrieval numbers and must not be given any.
    """
    if benchmark_dir is None and deep_dir is None and not (units_path and extra_arm_dirs):
        raise ValueError(
            "a document needs a benchmark tree, a packaged deep tree, or a canonical "
            "with at least one packaged arm"
        )
    if agentic_dir is not None and deep_dir is not None:
        raise ValueError("--agentic and --deep cannot both fill the fourth arm of one document")

    config: dict = {}
    manifest: dict = {}
    summary: dict = {}
    if benchmark_dir is not None:
        benchmark_dir = Path(benchmark_dir)
        for name in REQUIRED_TREE_FILES:
            _require(benchmark_dir / name)
        config = _load_json(benchmark_dir / "resolved-config.json")
        manifest = _load_json(benchmark_dir / "manifest.json")
        summary = _load_json(benchmark_dir / "benchmark-summary.json")
        source = config["source"]
        units_path = _require(root / source["units"])
        pinned = source.get("units_sha256") or manifest.get("canonical_sha256")
    elif deep_dir is not None:
        deep_manifest = _load_json(Path(deep_dir) / "arm" / "manifest.json")
        units_path = _require(root / deep_manifest["units_file"])
        pinned = deep_manifest.get("canonical_sha256")
        source = {}
    else:
        # Arms only: the canonical is named directly and every arm was
        # packaged from it, so there is nothing to cross-check it against.
        units_path = _require(Path(units_path))
        pinned = None
        source = {}
    digest = hashlib.sha256(units_path.read_bytes()).hexdigest()
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

    gold: list[dict] = []
    if source.get("gold_queries"):
        gold_raw = _load_json(_require(root / source["gold_queries"]))
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

    arms: dict[str, dict] = {}
    arm_kinds: dict[str, str] = {}
    if benchmark_dir is not None:
        arm_kinds = {arm: config["arms"][arm]["kind"] for arm in ARM_ORDER}
        for arm in ARM_ORDER:
            arms[arm], _rows = _load_arm_dir(
                benchmark_dir / arm, kind=arm_kinds[arm], units_by_id=units_by_id, require_retrieval=True
            )

    budgets = dict(config.get("tokens") or {})
    deep_meta: dict | None = None
    story: dict | None = None
    agentic_meta: dict | None = None
    if deep_dir is not None:
        deep_arm, standard_arm, deep_meta, story = _load_deep_arm(Path(deep_dir), digest, units_by_id)
        arms["agentic"] = deep_arm
        if "structure-only" not in arms:
            if standard_arm is None:
                raise ValueError(f"{deep_dir} carries no standard/ arm and no benchmark tree was given")
            arms["structure-only"] = standard_arm
        if not budgets:
            budgets = {
                key: deep_meta["config"].get(key)
                for key in ("min_tokens", "target_tokens", "soft_max_tokens", "hard_max_tokens")
                if deep_meta["config"].get(key) is not None
            }
        # The Standard arm gains the symmetric story: which of its cuts Deep
        # removed or moved, and what that fixed.
        std_chunks = arms["structure-only"]["chunks"]
        for index in range(1, len(std_chunks)):
            previous = std_chunks[index - 1]
            if previous["u"] and previous["u"][-1] in story["stdChanged"]:
                std_chunks[index]["dec"] = story["stdChanged"][previous["u"][-1]]
        for chunk in std_chunks:
            if chunk["u"]:
                chunk["si"] = story["sectionOf"].get(_base(chunk["u"][0]))
    elif agentic_dir is not None:
        # The fourth arm rides in ``arms`` so every arm-indexed renderer works
        # unchanged, but it never enters ARM_ORDER: the frozen dashboard
        # tables and the three-arm difference definition stay untouched, and
        # a build without an agentic tree is byte-identical to today's.
        agentic_arm, agentic_meta = _load_agentic_arm(Path(agentic_dir), digest, units_by_id)
        arms["agentic"] = agentic_arm

    # Arms packaged over the same canonical by the live workspace. Read with
    # the reduced contract: no retrieval, because a document with no gold set
    # has none and must not be given any.
    for name, arm_dir in dict(extra_arm_dirs or {}).items():
        if name in arms:
            raise ValueError(f"{name!r} is already filled; an extra arm cannot replace it")
        if name not in ARM_KINDS:
            raise ValueError(f"unknown arm {name!r}; expected one of {sorted(ARM_KINDS)}")
        arms[name], _rows = _load_arm_dir(
            Path(arm_dir), kind=ARM_KINDS[name], units_by_id=units_by_id, require_retrieval=False
        )
    if not arms:
        raise ValueError("a document needs at least one packaged arm")

    diffs = _difference_points(units, arms) if all(arm in arms for arm in ARM_ORDER) else []
    deep_diff_pages: list[int] = []
    if story is not None:
        deep_diff_pages = sorted(
            {
                page
                for section in story["sections"]
                if section["st"] != "standard_kept" and section["gr"]
                for page in section["pg"]
            }
        )

    hard_max = int(budgets.get("hard_max_tokens") or 1126)
    oversized = _oversized_units(units_raw, hard_max)
    findings = _parser_findings(units_raw)
    findings_by_unit: dict[str, list[str]] = {}
    for finding in findings:
        findings_by_unit.setdefault(finding["t"], []).append(finding["r"])
    for unit in units:
        if unit["i"] in oversized:
            unit["big"] = oversized[unit["i"]]
        if unit["i"] in findings_by_unit:
            unit["pf"] = sorted(set(findings_by_unit[unit["i"]]))

    doc_id = (benchmark_dir.name if benchmark_dir is not None else units_raw[0]["document_id"])
    kind = "benchmark" if benchmark_dir is not None else ("deep-only" if deep_dir is not None else "arms-only")
    result = {
        "label": label or DOC_LABELS.get(doc_id, doc_id),
        "id": units_raw[0]["document_id"],
        "kind": kind,
        "units": units,
        "arms": arms,
        "gold": gold,
        "diffs": diffs,
        "diffPages": sorted({point["p"] for point in diffs}),
        "deepDiffPages": deep_diff_pages,
        "pages": sorted({unit["p"] for unit in units}),
        "parser": {"count": len(findings), "findings": findings},
        "meta": {
            "diag": summary.get("arm_diagnostics") or {},
            "guard": summary.get("interpretation_guardrail"),
            "etypes": summary.get("evidence_type_hit_at_5") or {},
            "qcomp": summary.get("query_comparison") or {},
            "parserFindings": summary.get("parser_baseline_finding_count", len(findings)),
            "secondary": summary.get("secondary_gold"),
            "timing": summary.get("timing") or {},
            "budgets": budgets,
            "canonicalSha": manifest.get("canonical_sha256") or digest,
            "status": summary.get("status") or ("deep_analysis_run" if deep_dir else None),
            "queryCount": summary.get("query_count") or len(gold),
            "unitCount": len(units),
            "pageCount": len({unit["p"] for unit in units}),
            "deep": deep_meta,
        },
    }
    if story is not None:
        result["story"] = story
    if agentic_meta is not None:
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


def _relative(path: Path, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _catalog(
    docs: Mapping[str, dict],
    benchmarks: Mapping[str, Path],
    deep: Mapping[str, Path],
    agentic: Mapping[str, Path],
    root: Path,
) -> dict:
    """What the chat server serves: exactly the arms the HTML shows."""
    documents: dict[str, dict] = {}
    for doc, data in docs.items():
        arms: dict[str, dict] = {}
        if doc in benchmarks:
            config = _load_json(Path(benchmarks[doc]) / "resolved-config.json")
            units = config["source"]["units"]
            for arm in ARM_ORDER:
                arms[arm] = {
                    "kind": data["arms"][arm]["kind"],
                    "label": ARM_LABELS[arm],
                    "chunks": _relative(Path(benchmarks[doc]) / arm / "chunks.jsonl", root),
                }
        else:
            units = _load_json(Path(deep[doc]) / "arm" / "manifest.json")["units_file"]
            arms["structure-only"] = {
                "kind": "structure_first",
                "label": ARM_LABELS["structure-only"],
                "chunks": _relative(Path(deep[doc]) / "standard" / "chunks.jsonl", root),
            }
        if doc in deep:
            arms["agentic"] = {
                "kind": "deep_analysis",
                "label": ARM_LABELS["agentic"],
                "chunks": _relative(Path(deep[doc]) / "arm" / "chunks.jsonl", root),
            }
        elif doc in agentic:
            arms["agentic"] = {
                "kind": "agentic_structure_llm",
                "label": ARM_LABELS["agentic"],
                "chunks": _relative(Path(agentic[doc]) / "agentic" / "chunks.jsonl", root),
            }
        documents[doc] = {
            "label": data["label"],
            "units": units if isinstance(units, str) else str(units),
            "canonical_sha256": data["meta"]["canonicalSha"],
            "arms": arms,
        }
    # The build inputs, so the published page can be rebuilt from its own
    # catalog and held byte-identical to a fresh build.
    build = {
        "benchmarks": {doc: _relative(path, root) for doc, path in benchmarks.items()},
        "deep": {doc: _relative(path, root) for doc, path in deep.items()},
        "agentic": {doc: _relative(path, root) for doc, path in agentic.items()},
        "labels": {doc: data["label"] for doc, data in docs.items()},
        "document_order": list(docs),
    }
    return {"generator": "amsc.viewer_v2", "documents": documents, "build": build}


def build_viewer(
    benchmarks: Mapping[str, Path],
    output: Path,
    root: Path = Path("."),
    agentic: Mapping[str, Path] | None = None,
    deep: Mapping[str, Path] | None = None,
    labels: Mapping[str, str] | None = None,
    write_catalog: bool = True,
) -> Path:
    """Build the single-file viewer for the given trees.

    ``benchmarks`` maps a document id to a frozen chunk-benchmark tree;
    ``deep`` maps a document id to a packaged Deep Analysis tree (a document
    may appear only there); ``agentic`` maps a document id to the earlier
    research tree. Without ``deep``/``agentic`` the output is byte-identical
    to a three-arm build.
    """
    agentic = dict(agentic or {})
    deep = dict(deep or {})
    labels = dict(labels or {})
    # Benchmark-backed documents first, in the order given, then the
    # deep-only ones: the page opens on the richest document.
    documents = list(benchmarks) + [doc for doc in deep if doc not in benchmarks]
    if not documents:
        raise ValueError("at least one benchmark tree or packaged deep tree is required")
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
            Path(benchmarks[doc]) if doc in benchmarks else None,
            Path(root),
            agentic_dir=agentic.get(doc),
            deep_dir=deep.get(doc),
            label=labels.get(doc),
        )
        for doc in documents
    }
    data = {
        "docs": docs,
        "docOrder": documents,
        "armOrder": list(ARM_ORDER),
        "armLabels": ARM_LABELS,
        "productArmOrder": list(PRODUCT_ARM_ORDER),
        "price": {**REFERENCE_PRICE_PER_M, "note": "list prices observed 2026-08-29; approximate"},
        "generator": "amsc.viewer_v2",
    }
    payload = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).replace("</", "<\\/")

    document = TEMPLATE.replace("__VIEWER_DATA__", payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    if write_catalog:
        catalog = _catalog(docs, benchmarks, deep, agentic, Path(root))
        (output.parent / "catalog.json").write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return output


def _parse_specs(parser: argparse.ArgumentParser, specs: Sequence[str], flag: str) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for spec in specs:
        doc, _, directory = spec.partition("=")
        if not directory:
            parser.error(f"{flag} expects DOC=DIR, got {spec!r}")
        out[doc] = Path(directory)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.viewer_v2",
        description=(
            "Build the self-contained Viewer v2 HTML (Sunum / Sorgu / Debug / "
            "Benchmark) from completed artifact trees"
        ),
    )
    parser.add_argument(
        "--benchmark",
        action="append",
        default=[],
        metavar="DOC=DIR",
        help="document id and its frozen chunk-benchmark tree, e.g. "
        "kkb-2024=artifacts/chunk-benchmark-v5/kkb-2024 (repeatable)",
    )
    parser.add_argument(
        "--deep",
        action="append",
        default=[],
        metavar="DOC=DIR",
        help="packaged Deep Analysis tree for a document, e.g. "
        "kkb-2024=artifacts/deep-analysis/kkb-2024-final (repeatable)",
    )
    parser.add_argument(
        "--agentic",
        action="append",
        default=[],
        metavar="DOC=DIR",
        help="earlier agentic-chunker research tree for a document (repeatable)",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="DOC=LABEL",
        help="display label for a document (repeatable)",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--no-catalog", action="store_true", help="do not write catalog.json")
    args = parser.parse_args(argv)

    benchmarks = _parse_specs(parser, args.benchmark, "--benchmark")
    deep = _parse_specs(parser, args.deep, "--deep")
    agentic = _parse_specs(parser, args.agentic, "--agentic")
    labels: dict[str, str] = {}
    for spec in args.label:
        doc, _, text = spec.partition("=")
        if not text:
            parser.error(f"--label expects DOC=LABEL, got {spec!r}")
        labels[doc] = text
    if not benchmarks and not deep:
        parser.error("at least one --benchmark or --deep is required")

    destination = build_viewer(
        benchmarks, args.output, root=args.root, agentic=agentic, deep=deep,
        labels=labels, write_catalog=not args.no_catalog,
    )
    documents = list(benchmarks) + [doc for doc in deep if doc not in benchmarks]
    print(json.dumps({"output": str(destination), "documents": documents}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
