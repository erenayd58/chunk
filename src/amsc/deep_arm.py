"""Package a Deep Analysis run as a viewer arm, with its decision story.

A ``deep_run`` tree records *what* was chosen (``chunks.jsonl``,
``selection-audit.json``) and how it measures against Standard
(``quality-vs-standard.json``). What it does not record in one place is the
story a reader wants at each boundary: was this cut Standard's own, did the
quality contract move it, did a model propose it and did the verifier keep
it, or is it forced by a unit no partition can get inside. This module
derives that story deterministically from the tree plus the canonical, and
writes the files the viewer and the benchmark panel read:

    <deep_tree>/arm/manifest.json            arm kind, canonical pin, models, status
    <deep_tree>/arm/chunks.jsonl             rows with canonical unit ids (+ fragment ids)
    <deep_tree>/arm/mapping.json             chunk <-> unit resolution (amsc.chunk_mapping)
    <deep_tree>/arm/structural_quality.json  chunk_quality.measure, parser baseline subtracted
    <deep_tree>/arm/retrieval.json           frozen-metric BM25 scores  (only with --frozen-tree)
    <deep_tree>/arm/query-results.jsonl      per-query ranks             (only with --frozen-tree)
    <deep_tree>/arm/timing.json              search latency              (only with --frozen-tree)
    <deep_tree>/standard/...                 the same set for the Standard partition
    <deep_tree>/boundary-decisions.json      the per-section / per-boundary story

Retrieval numbers come from the frozen evaluator through
:mod:`amsc.agentic_benchmark`'s ``_evaluate_gold`` -- the same BM25 settings,
gold set and metric code as the frozen three arms -- and are written beside
the arm, never into the frozen tree. A page-sliced tree or a different
canonical is refused. Nothing here calls a model.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import boundary_quality as bq
from . import chunk_quality
from . import deep_analysis as da
from .agentic_benchmark import _evaluate_gold
from .chunk_benchmark import normalize_unit_ids_for_retrieval
from .chunk_mapping import base_unit_id, map_chunks
from .deep_pipeline import run_standard
from .evaluation import sha256_file
from .io import load_jsonl_units
from .models import RawDocumentUnit
from .structural_chunker import _sections
from .tokenization import TiktokenTokenCounter, TokenCounter

ARM_KIND = "deep_analysis"
GENERATOR = "amsc.deep_arm"

#: Section-level outcomes, in the order the counts are reported.
SECTION_STATUSES = (
    "standard_kept",
    "deterministic_improved",
    "llm_accepted",
    "llm_reverted",
    "contract_reverted",
)
#: Per final boundary: where the cut came from.
CUT_ORIGINS = ("standard", "deterministic", "llm")

_GROUP_KEY = re.compile(r"^cg-(\d+)-(\d+)-(\d+)$")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def refuse_output(path: Path) -> None:
    resolved = path.resolve()
    if "evaluation" in resolved.parts:
        raise ValueError(f"refusing to write into evaluation/: {resolved}")
    for ancestor in [resolved, *resolved.parents]:
        if (ancestor / "benchmark-summary.json").is_file():
            raise ValueError(f"refusing to write into the frozen benchmark tree at {ancestor}")


# --------------------------------------------------------------------------
# the decision story
# --------------------------------------------------------------------------


def _cut_smells(
    section, position: int, units_by_id: Mapping[str, RawDocumentUnit], config: bq.QualityConfig
) -> list[str]:
    left, right = section.pieces[position - 1], section.pieces[position]
    return bq.boundary_smells(
        units_by_id[base_unit_id(left.unit_id)],
        units_by_id[base_unit_id(right.unit_id)],
        left_raw_id=left.unit_id,
        right_raw_id=right.unit_id,
        config=config,
    )


def _spans_between(cuts_a: Sequence[int], cuts_b: Sequence[int], length: int) -> list[tuple[int, int]]:
    """Maximal spans between cuts common to both partitions where they differ."""
    shared = sorted(set(cuts_a) & set(cuts_b))
    edges = [0, *shared, length]
    spans: list[tuple[int, int]] = []
    only_a, only_b = set(cuts_a) - set(cuts_b), set(cuts_b) - set(cuts_a)
    for start, end in zip(edges, edges[1:]):
        if any(start < c < end for c in only_a | only_b):
            spans.append((start, end))
    return spans


def boundary_story(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    config: da.DeepConfig,
    audit: Mapping[str, Any],
    quality: Mapping[str, Any],
    verdicts: Sequence[Mapping[str, Any]] = (),
    proposer_audit: Sequence[Mapping[str, Any]] = (),
    deterministic_cuts: Mapping[int, Sequence[int]] | None = None,
) -> dict[str, Any]:
    """Attribute every final boundary and every section outcome.

    ``deterministic_cuts`` is recomputed (LLM-free selector) when not given,
    which is what makes the story derivable from a tree that only recorded
    the final partition.
    """
    quality_config = config.quality()
    sections = _sections(units, counter, config.hard_max_tokens, config.respect_semantic_roles)
    units_by_id = {unit.unit_id: unit for unit in units}
    if deterministic_cuts is None:
        _rows, det_audit = da.chunk_units(units, counter=counter, config=config)
        deterministic_cuts = {int(k): tuple(v) for k, v in det_audit["cuts_by_section"].items()}
    det = {int(k): tuple(v) for k, v in deterministic_cuts.items()}
    std = {int(k): tuple(v) for k, v in audit["standard_cuts_by_section"].items()}
    final = {int(k): tuple(v) for k, v in audit["cuts_by_section"].items()}
    plan_by_index = {int(p["section_index"]): p for p in audit.get("sections", [])}
    quality_by_index = {
        int(s["section_index"]): s for s in quality.get("sections_with_differences", [])
    }
    consulted = {int(a["section_index"]) for a in proposer_audit if a.get("status") == "ok"}
    verdicts_by_index: dict[int, list[dict[str, Any]]] = {}
    for row in verdicts:
        match = _GROUP_KEY.match(str(row.get("group_key", "")))
        entry = {
            "group_key": row.get("group_key"),
            "accepted": bool(row.get("accepted")),
            "reason": row.get("reason"),
            "start": int(match.group(2)) if match else None,
            "end": int(match.group(3)) if match else None,
        }
        verdicts_by_index.setdefault(int(row["section_index"]), []).append(entry)

    counts = {status: 0 for status in SECTION_STATUSES}
    origin_counts = {origin: 0 for origin in CUT_ORIGINS}
    ceiling = 0
    llm_consulted = 0
    story_sections: list[dict[str, Any]] = []
    by_cut_after: dict[str, dict[str, Any]] = {}

    for index, section in enumerate(sections):
        s_cuts, d_cuts, f_cuts = std.get(index, ()), det.get(index, ()), final.get(index, ())
        s_set, d_set, f_set = set(s_cuts), set(d_cuts), set(f_cuts)
        plan = plan_by_index.get(index)
        reverted = plan.get("reverted") if plan else None
        section_verdicts = verdicts_by_index.get(index, [])
        accepted_groups = [v for v in section_verdicts if v["accepted"]]
        reverted_groups = [v for v in section_verdicts if not v["accepted"]]

        if reverted in ("smell_vector", "hard_cap"):
            status = "contract_reverted"
        elif f_set != d_set:
            status = "llm_accepted"
        elif d_set != s_set:
            status = "deterministic_improved"
        elif reverted_groups:
            status = "llm_reverted"
        else:
            status = "standard_kept"
        counts[status] += 1
        if index in consulted:
            llm_consulted += 1

        piece_ids = [piece.unit_id for piece in section.pieces]
        pos_ids = lambda positions: [piece_ids[p - 1] for p in positions]  # noqa: E731

        boundaries: list[dict[str, Any]] = []
        for position in sorted(s_set | d_set | f_set):
            left, right = section.pieces[position - 1], section.pieces[position]
            inside_unit = base_unit_id(left.unit_id) == base_unit_id(right.unit_id)
            in_final = position in f_set
            if in_final:
                origin = "standard" if position in s_set else ("deterministic" if position in d_set else "llm")
                origin_counts[origin] += 1
                if inside_unit:
                    ceiling += 1
            else:
                origin = "removed_by_llm" if position in d_set else "removed_by_deterministic"
            record = {
                "position": position,
                "cut_after_unit_id": left.unit_id,
                "cut_before_unit_id": right.unit_id,
                "in_standard": position in s_set,
                "in_deterministic": position in d_set,
                "in_final": in_final,
                "origin": origin,
                "inside_unit": inside_unit,
                "smells": _cut_smells(section, position, units_by_id, quality_config),
                "label": bool(right.label),
            }
            boundaries.append(record)

        # Change groups against Standard explain each moved boundary by the
        # smells of the Standard cuts it replaced -- the unit a reader can
        # accept or reject as a whole.
        groups: list[dict[str, Any]] = []
        piece_tokens = [piece.tokens for piece in section.pieces]

        def block_sizes(start: int, end: int, cuts: Sequence[int]) -> list[int]:
            edges = [start, *[p for p in cuts if start < p < end], end]
            return [sum(piece_tokens[a:b]) for a, b in zip(edges, edges[1:])]

        for start, end in _spans_between(s_cuts, f_cuts, len(section.pieces)):
            std_in = [p for p in s_cuts if start < p < end]
            fin_in = [p for p in f_cuts if start < p < end]
            removed = sorted(
                {smell for p in std_in for smell in _cut_smells(section, p, units_by_id, quality_config)}
            )
            introduced = sorted(
                {smell for p in fin_in for smell in _cut_smells(section, p, units_by_id, quality_config)}
            )
            std_sizes = block_sizes(start, end, s_cuts)
            fin_sizes = block_sizes(start, end, f_cuts)
            # Piece-token sums (heading render excluded): enough to say why a
            # size-only move happened, not a restatement of chunk token counts.
            size_effect = {
                "standard_block_tokens": std_sizes,
                "final_block_tokens": fin_sizes,
                "below_min": {
                    "standard": sum(1 for s in std_sizes if s < config.min_tokens),
                    "final": sum(1 for s in fin_sizes if s < config.min_tokens),
                },
                "above_soft_max": {
                    "standard": sum(1 for s in std_sizes if s > config.soft_max_tokens),
                    "final": sum(1 for s in fin_sizes if s > config.soft_max_tokens),
                },
            }
            groups.append(
                {
                    "start": start,
                    "end": end,
                    "unit_ids": piece_ids[start:end],
                    "standard_cuts_after": pos_ids(std_in),
                    "final_cuts_after": pos_ids(fin_in),
                    "removed_smells": removed,
                    "introduced_smells": introduced,
                    "size_effect": size_effect,
                    "origin": "llm" if any(p not in d_set for p in fin_in) else "deterministic",
                }
            )

        q = quality_by_index.get(index)
        entry = {
            "section_index": index,
            "heading": section.heading,
            "section_path": list(section.section_path),
            "piece_unit_ids": piece_ids,
            "pages": sorted({p.page for p in section.pieces if p.page is not None}),
            "tokens": section.tokens,
            "status": status,
            "llm_consulted": index in consulted,
            "reverted": reverted,
            "size_traded": bool(q and q.get("size_traded")),
            "verdict_tiered": q.get("verdict_tiered") if q else bq.VERDICT_TIE,
            "smells": {
                "standard": (q or {}).get("standard", {}).get("vector"),
                "deep": (q or {}).get("deep", {}).get("vector"),
            },
            "standard_cuts_after": pos_ids(s_cuts),
            "deterministic_cuts_after": pos_ids(d_cuts),
            "final_cuts_after": pos_ids(f_cuts),
            "boundaries": boundaries,
            "change_groups": groups,
            "llm_proposals": [
                {
                    **v,
                    "unit_ids": piece_ids[v["start"] : v["end"]] if v["start"] is not None else [],
                }
                for v in section_verdicts
            ],
        }
        story_sections.append(entry)

        for group in groups:
            for cut_after in group["final_cuts_after"]:
                by_cut_after[cut_after] = {
                    "section_index": index,
                    "status": "llm_accepted" if group["origin"] == "llm" else "det_moved",
                    "removed_smells": group["removed_smells"],
                    "introduced_smells": group["introduced_smells"],
                    "group_units": group["unit_ids"],
                    "standard_cuts_after": group["standard_cuts_after"],
                    "size_effect": {
                        k: group["size_effect"][k] for k in ("below_min", "above_soft_max")
                    },
                }
            if not group["final_cuts_after"] and group["standard_cuts_after"]:
                # A merge: Standard cut here, Deep did not. The chunk that
                # now spans the group starts at the group's first unit; the
                # story is attached to the boundary *before* it when that
                # boundary is a final cut, else to the section entry only.
                merged_key = f"merge:{group['unit_ids'][0]}"
                by_cut_after[merged_key] = {
                    "section_index": index,
                    "status": "det_merged" if group["origin"] == "deterministic" else "llm_merged",
                    "removed_smells": group["removed_smells"],
                    "group_units": group["unit_ids"],
                    "standard_cuts_after": group["standard_cuts_after"],
                    "size_effect": {
                        k: group["size_effect"][k] for k in ("below_min", "above_soft_max")
                    },
                }
        for record in boundaries:
            if not record["in_final"]:
                continue
            key = record["cut_after_unit_id"]
            if key in by_cut_after:
                if record["inside_unit"]:
                    by_cut_after[key]["inside_unit"] = True
                continue
            by_cut_after[key] = {
                "section_index": index,
                "status": "ceiling" if record["inside_unit"] else "kept",
                "smells": record["smells"],
                "inside_unit": record["inside_unit"],
            }
        for proposal in reverted_groups:
            # A reverted proposal leaves the deterministic cuts in place; the
            # reader still deserves to know the model asked for something
            # else here and why it did not win.
            for cut_after in pos_ids([p for p in f_cuts if proposal["start"] is not None and proposal["start"] <= p < proposal["end"]]):
                by_cut_after.setdefault(cut_after, {"section_index": index, "status": "kept"})
                by_cut_after[cut_after]["llm_reverted"] = proposal["reason"]
        for proposal in accepted_groups:
            for cut_after in pos_ids([p for p in f_cuts if proposal["start"] is not None and proposal["start"] <= p < proposal["end"]]):
                if cut_after in by_cut_after:
                    by_cut_after[cut_after]["verifier"] = "unanimous"

    return {
        "arm_kind": ARM_KIND,
        "config": {**config.__dict__},
        "counts": {
            "sections": len(sections),
            **counts,
            "llm_consulted_sections": llm_consulted,
            "final_boundaries_by_origin": origin_counts,
            "ceiling_boundaries": ceiling,
            "llm_proposals": sum(len(v) for v in verdicts_by_index.values()),
            "llm_proposals_accepted": sum(
                1 for v in verdicts_by_index.values() for g in v if g["accepted"]
            ),
        },
        "sections": story_sections,
        "by_cut_after": by_cut_after,
    }


# --------------------------------------------------------------------------
# packaging
# --------------------------------------------------------------------------


def _package_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    units: Sequence[RawDocumentUnit],
    counter: TokenCounter,
    config: da.DeepConfig,
    baseline,
    output_dir: Path,
    frozen_tree: Path | None,
    root: Path,
    units_sha: str,
) -> dict[str, Any]:
    normalised = [normalize_unit_ids_for_retrieval(row) for row in rows]
    mapping = map_chunks(units, normalised)
    _write_jsonl(output_dir / "chunks.jsonl", normalised)
    _write_json(output_dir / "mapping.json", mapping.as_dict())
    structural = chunk_quality.measure(
        units,
        normalised,
        mapping,
        counter=counter,
        min_tokens=config.min_tokens,
        soft_max_tokens=config.soft_max_tokens,
        hard_max_tokens=config.hard_max_tokens,
        baseline=baseline,
    )
    _write_json(output_dir / "structural_quality.json", structural)
    retrieval: dict[str, Any] | None = None
    if frozen_tree is not None:
        frozen_config = _read_json(frozen_tree / "resolved-config.json")
        source = frozen_config["source"]
        if source.get("units_sha256") != units_sha:
            raise ValueError(
                "the frozen benchmark tree pins a different canonical than the "
                "deep tree; refusing to score against its gold set"
            )
        retrieval = _evaluate_gold(
            gold_path=root / source["gold_queries"],
            units=units,
            units_sha=units_sha,
            rows=normalised,
            mapping=mapping,
            counter=counter,
            frozen_config=frozen_config,
            output_dir=output_dir,
        )
    return {
        "chunk_count": len(normalised),
        "structural_quality": structural,
        "retrieval": retrieval,
    }


def package_arm(
    rows: Sequence[Mapping[str, Any]],
    *,
    units: Sequence[RawDocumentUnit],
    output_dir: Path,
    config: da.DeepConfig | None = None,
    counter: TokenCounter | None = None,
    baseline: Any | None = None,
) -> dict[str, Any]:
    """Package one chunker's rows into the arm directory the viewer reads.

    The public seam behind :func:`package` -- the live workspace runs several
    chunkers over one canonical and needs each written in the same shape, by
    the same writer, so a variant cannot drift from the benchmark's idea of
    what an arm is. No retrieval is scored: a document with no gold set has
    no retrieval numbers, and inventing some would be worse than having none.
    """
    counter = counter or TiktokenTokenCounter("cl100k_base")
    config = config or da.DeepConfig()
    return _package_rows(
        rows,
        units=units,
        counter=counter,
        config=config,
        baseline=baseline if baseline is not None else chunk_quality.parser_baseline(units),
        output_dir=Path(output_dir),
        frozen_tree=None,
        root=Path("."),
        units_sha="",
    )


def package(
    deep_tree: Path,
    units_path: Path,
    *,
    root: Path = Path("."),
    frozen_tree: Path | None = None,
    counter: TokenCounter | None = None,
    write_standard: bool = True,
) -> dict[str, Any]:
    """Write the arm files and the decision story; return a summary."""
    deep_tree = Path(deep_tree)
    refuse_output(deep_tree)
    summary = _read_json(deep_tree / "summary.json")
    audit = _read_json(deep_tree / "selection-audit.json")
    quality = _read_json(deep_tree / "quality-vs-standard.json")
    rows = _read_jsonl(deep_tree / "chunks.jsonl")
    verdicts = _read_jsonl(deep_tree / "verifier" / "verdicts.jsonl")
    proposer_audit = _read_jsonl(deep_tree / "proposer" / "audit.jsonl")

    units = load_jsonl_units(units_path)
    units_sha = sha256_file(units_path)
    if summary.get("document_id") != units[0].document_id:
        raise ValueError(
            f"the deep tree was built for {summary.get('document_id')!r}, "
            f"not {units[0].document_id!r}"
        )
    config = da.DeepConfig(**{k: v for k, v in summary["config"].items() if k in da.DeepConfig.__dataclass_fields__})
    counter = counter or TiktokenTokenCounter("cl100k_base")
    baseline = chunk_quality.parser_baseline(units)

    packaged = _package_rows(
        rows,
        units=units,
        counter=counter,
        config=config,
        baseline=baseline,
        output_dir=deep_tree / "arm",
        frozen_tree=frozen_tree,
        root=root,
        units_sha=units_sha,
    )
    standard_packaged: dict[str, Any] | None = None
    if write_standard:
        standard_rows = run_standard(units, counter=counter, config=config)
        standard_packaged = _package_rows(
            standard_rows,
            units=units,
            counter=counter,
            config=config,
            baseline=baseline,
            output_dir=deep_tree / "standard",
            frozen_tree=frozen_tree,
            root=root,
            units_sha=units_sha,
        )

    story = boundary_story(
        units,
        counter=counter,
        config=config,
        audit=audit,
        quality=quality,
        verdicts=verdicts,
        proposer_audit=proposer_audit,
    )
    story["canonical_sha256"] = units_sha
    story["document_id"] = units[0].document_id
    _write_json(deep_tree / "boundary-decisions.json", story)

    try:
        units_file = str(Path(units_path).resolve().relative_to(Path(root).resolve())).replace("\\", "/")
    except ValueError:
        units_file = str(units_path)
    manifest = {
        "arm_kind": ARM_KIND,
        "generator": GENERATOR,
        "document_id": units[0].document_id,
        "canonical_sha256": units_sha,
        "units_file": units_file,
        "mode": summary.get("mode"),
        "status": summary.get("status"),
        "model_id": summary.get("model_id"),
        "verifier_model_id": summary.get("verifier_model_id"),
        "prompt_template_version": summary.get("prompt_template_version"),
        "config": {**config.__dict__},
        "frozen_tree": frozen_tree.as_posix() if frozen_tree else None,
        "has_retrieval": packaged["retrieval"] is not None,
        "has_standard": standard_packaged is not None,
        "parser_baseline_finding_count": len(baseline),
    }
    _write_json(deep_tree / "arm" / "manifest.json", manifest)
    return {
        "deep_tree": deep_tree.as_posix(),
        "chunk_count": {
            "deep": packaged["chunk_count"],
            "standard": standard_packaged["chunk_count"] if standard_packaged else None,
        },
        "retrieval": {
            "deep": packaged["retrieval"],
            "standard": standard_packaged["retrieval"] if standard_packaged else None,
        },
        "story_counts": story["counts"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.deep_arm",
        description="Package a Deep Analysis tree as a viewer arm with its decision story",
    )
    parser.add_argument("--deep-tree", required=True, type=Path)
    parser.add_argument("--units", required=True, type=Path)
    parser.add_argument("--frozen-tree", type=Path, help="a completed chunk-benchmark tree for gold scoring")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--no-standard", action="store_true", help="skip packaging the Standard partition")
    parser.add_argument("--encoding", default="cl100k_base")
    args = parser.parse_args(argv)
    summary = package(
        args.deep_tree,
        args.units,
        root=args.root,
        frozen_tree=args.frozen_tree,
        counter=TiktokenTokenCounter(args.encoding),
        write_standard=not args.no_standard,
    )
    compact = {
        "deep_tree": summary["deep_tree"],
        "chunk_count": summary["chunk_count"],
        "story_counts": summary["story_counts"],
        "retrieval": {
            arm: (None if metrics is None else {k: metrics[k] for k in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr")})
            for arm, metrics in summary["retrieval"].items()
        },
    }
    print(json.dumps(compact, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
