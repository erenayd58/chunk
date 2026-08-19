from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import numpy as np

from .config import V3Config, V4Config
from .evaluation import (
    evaluate_checkpoint,
    load_annotations,
    load_jsonl_objects,
    sha256_file,
)
from .failure_analysis import DiagnosticRun, RunDiagnostics, analyze_run
from .io import load_jsonl_units
from .merge import SemanticSafeMergeResolver, V4ChunkDraft
from .models import BoundaryEvidence, ChunkBoundary, ContentUnit, RawDocumentUnit
from .selection import V2TailResolver
from .semantic_comparators import (
    ComparatorBoundaryProvenance,
    ComparatorIntervalBoundarySelector,
    CosineKernelChangePointComparator,
    LocalSemanticProminenceComparator,
)
from .strength import DualBoundaryStrengthAnnotator
from .tokenization import TiktokenTokenCounter, TokenCounter
from .units import HeadingAttachmentBuilder, RenderedTokenBudgeter, render_units
from .v5_research import (
    AUTHORITATIVE_CANONICAL_SHA256,
    AUTHORITATIVE_V3_EXACT_F1,
    AUTHORITATIVE_V3_PLUS_MINUS_ONE_F1,
    _assert_boundary_unit_alignment,
    _assert_frozen_shared_config,
    _base_chunk_metadata,
    _boundary_index_by_raw_gap,
    _embedding_provenance_by_unit,
    _load_retained_embeddings,
    _unique,
    _unique_dicts,
    _unique_lists,
)


_CORE_FILES = (
    "chunks.jsonl",
    "boundaries.jsonl",
    "metrics.json",
    "resolved-config.json",
)


def run_phase3c_research(
    *,
    units_path: str | Path,
    annotations_path: str | Path,
    v3_output_dir: str | Path,
    v3_config_path: str | Path,
    v4_config_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    units_path = Path(units_path)
    annotations_path = Path(annotations_path)
    v3_output_dir = Path(v3_output_dir)
    target = Path(output_dir)
    units_sha = sha256_file(units_path)
    if units_sha != AUTHORITATIVE_CANONICAL_SHA256:
        raise ValueError("Phase 3C requires the frozen canonical KKB input")
    units = load_jsonl_units(units_path)
    annotations = load_annotations(annotations_path)
    if annotations.source_units_sha256 != units_sha:
        raise ValueError("Frozen annotations do not match canonical input")

    v3_config = V3Config.from_yaml(v3_config_path)
    v4_config = V4Config.from_yaml(v4_config_path)
    _assert_frozen_shared_config(v3_config, v4_config)
    token_counter = TiktokenTokenCounter(v3_config.token_counter.encoding)
    budgeter = RenderedTokenBudgeter(
        token_counter,
        v3_config.tokens.hard_max_tokens,
    )
    prepared = HeadingAttachmentBuilder(budgeter).build(units)
    units_by_id = {unit.unit_id: unit for unit in prepared}
    base_chunks = load_jsonl_objects(v3_output_dir / "chunks.jsonl")
    base_boundaries = [
        BoundaryEvidence.model_validate(row)
        for row in load_jsonl_objects(v3_output_dir / "boundaries.jsonl")
    ]
    base_metrics = json.loads(
        (v3_output_dir / "metrics.json").read_text(encoding="utf-8")
    )
    _assert_v3_control(base_metrics)
    _assert_boundary_unit_alignment(base_boundaries, units_by_id)
    embedding_provenance = _embedding_provenance_by_unit(base_chunks)
    base_metadata = _base_chunk_metadata(base_chunks)
    retained_embeddings = _load_retained_embeddings(
        prepared,
        v3_config,
        base_metadata,
    )
    target.mkdir(parents=True, exist_ok=True)
    _copy_control(v3_output_dir, target / "c0")

    c1_comparator = LocalSemanticProminenceComparator(
        v3_config.semantic,
        v3_config.multi_scale,
    ).compute(base_boundaries, units_by_id)
    c2_comparator = CosineKernelChangePointComparator(
        v3_config.semantic
    ).compute(
        prepared=prepared,
        boundaries=base_boundaries,
        units_by_id=units_by_id,
        retained_embeddings=retained_embeddings,
        token_counter=token_counter,
    )

    run_metrics: dict[str, dict[str, Any]] = {}
    for run_id, comparator in (
        ("c1", c1_comparator),
        ("c2", c2_comparator),
    ):
        chunks, boundaries = _run_comparator(
            run_id=run_id,
            prepared=prepared,
            base_boundaries=base_boundaries,
            comparator_by_boundary=comparator,
            v3_config=v3_config,
            v4_config=v4_config,
            token_counter=token_counter,
            budgeter=budgeter,
            embedding_provenance=embedding_provenance,
            base_metadata=base_metadata,
            retained_embeddings=None,
            merge_enabled=False,
        )
        run_metrics[run_id] = _write_and_evaluate(
            run_dir=target / run_id,
            run_id=run_id,
            chunks=chunks,
            boundaries=boundaries,
            comparator_by_boundary=comparator,
            resolved_config=_resolved_config(
                v3_config,
                v4_config,
                run_id,
                next(iter(comparator.values())).method_id,
                merge_enabled=False,
            ),
            units=units,
            annotations=annotations,
            units_sha=units_sha,
        )

    initial_diagnostics = _load_diagnostics(
        target,
        ("c0", "c1", "c2"),
        units,
        annotations,
        units_sha,
    )
    winner_id = _select_development_winner(run_metrics, initial_diagnostics)
    winner_comparator = c1_comparator if winner_id == "c1" else c2_comparator
    winner_method = next(iter(winner_comparator.values())).method_id
    c3_chunks, c3_boundaries = _run_comparator(
        run_id="c3",
        prepared=prepared,
        base_boundaries=base_boundaries,
        comparator_by_boundary=winner_comparator,
        v3_config=v3_config,
        v4_config=v4_config,
        token_counter=token_counter,
        budgeter=budgeter,
        embedding_provenance=embedding_provenance,
        base_metadata=base_metadata,
        retained_embeddings=retained_embeddings,
        merge_enabled=True,
    )
    run_metrics["c3"] = _write_and_evaluate(
        run_dir=target / "c3",
        run_id="c3",
        chunks=c3_chunks,
        boundaries=c3_boundaries,
        comparator_by_boundary=winner_comparator,
        resolved_config=_resolved_config(
            v3_config,
            v4_config,
            "c3",
            winner_method,
            merge_enabled=True,
            winner_id=winner_id,
        ),
        units=units,
        annotations=annotations,
        units_sha=units_sha,
    )

    diagnostics = _load_diagnostics(
        target,
        ("c0", "c1", "c2", "c3"),
        units,
        annotations,
        units_sha,
    )
    comparator_by_run = {
        "c1": c1_comparator,
        "c2": c2_comparator,
        "c3": winner_comparator,
    }
    summary = _build_summary(
        target=target,
        diagnostics=diagnostics,
        comparator_by_run=comparator_by_run,
        base_boundaries=base_boundaries,
        units=units,
        winner_id=winner_id,
        winner_method=winner_method,
    )
    _write_json(target / "summary.json", summary)
    (target / "semantic-comparator-report.md").write_text(
        _render_markdown(summary),
        encoding="utf-8",
        newline="\n",
    )
    return summary


def _run_comparator(
    *,
    run_id: str,
    prepared: Sequence[ContentUnit],
    base_boundaries: Sequence[BoundaryEvidence],
    comparator_by_boundary: Mapping[int, ComparatorBoundaryProvenance],
    v3_config: V3Config,
    v4_config: V4Config,
    token_counter: TokenCounter,
    budgeter: RenderedTokenBudgeter,
    embedding_provenance: Mapping[str, dict[str, Any]],
    base_metadata: Mapping[str, Any],
    retained_embeddings: Mapping[str, np.ndarray] | None,
    merge_enabled: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    boundaries = [
        boundary.model_copy(
            update={
                "semantic_candidate": comparator_by_boundary[
                    boundary.boundary_index
                ].semantic_candidate,
                "candidate_chunk_tokens": None,
                "target_distance": None,
                "selection_score": None,
                "selected_reason": None,
                "structural": None,
                "original_boundary_strength": None,
                "effective_boundary_strength": None,
                "selection_signal": None,
                "selection_strategy": None,
                "merge_decisions": None,
            }
        )
        for boundary in base_boundaries
    ]
    if merge_enabled:
        boundaries = DualBoundaryStrengthAnnotator(
            epsilon=v4_config.selection.strength_epsilon
        ).apply(boundaries)
    boundary_by_pair = {
        (item.left_unit_id, item.right_unit_id): item for item in boundaries
    }
    selector = ComparatorIntervalBoundarySelector(
        budgeter=budgeter,
        token_limits=v3_config.tokens,
        semantic=None,
        selection=v3_config.selection,
        semantic_boundary_reason="adaptive_semantic_boundary",
        tail_resolver=V2TailResolver(budgeter, v3_config.tokens),
        removed_tail_selected_reason=(
            f"removed_by_phase3c_{run_id}_tail_coalescing"
        ),
        comparator_by_boundary=comparator_by_boundary,
    )
    drafts: list[V4ChunkDraft] = []
    updated_boundaries: list[BoundaryEvidence] = []
    cursor = 0
    while cursor < len(prepared):
        if prepared[cursor].text_for_embedding is None:
            unit = prepared[cursor]
            drafts.append(
                V4ChunkDraft(
                    units=[unit],
                    end_boundary=ChunkBoundary(
                        reason=unit.forced_split_reason
                        or "nonsemantic_heading_boundary"
                    ),
                    original_chunk_indices=(len(drafts),),
                )
            )
            cursor += 1
            continue
        run_end = cursor
        while (
            run_end < len(prepared)
            and prepared[run_end].text_for_embedding is not None
        ):
            run_end += 1
        run_units = prepared[cursor:run_end]
        run_boundaries = [
            boundary_by_pair[(run_units[index].unit_id, run_units[index + 1].unit_id)]
            for index in range(len(run_units) - 1)
        ]
        segments, updated = selector.select(run_units, run_boundaries)
        updated_boundaries.extend(updated)
        for segment in segments:
            drafts.append(
                V4ChunkDraft(
                    units=list(run_units[segment.start : segment.end]),
                    end_boundary=segment.end_boundary,
                    original_chunk_indices=(len(drafts),),
                    unmerged_short_tail_reason=segment.unmerged_short_tail_reason,
                    tail_coalesced=segment.tail_coalesced,
                    removed_tail_boundary_reason=segment.metadata.get(
                        "removed_tail_boundary_reason"
                    ),
                )
            )
        cursor = run_end
    for draft in drafts[:-1]:
        if draft.end_boundary.reason == "document_end":
            draft.end_boundary = ChunkBoundary(reason="nonsemantic_forced_boundary")
    if drafts:
        drafts[-1].end_boundary = ChunkBoundary(reason="document_end")

    if merge_enabled:
        if retained_embeddings is None:
            raise ValueError("C3 merge requires retained cached embeddings")
        drafts, updated_boundaries = SemanticSafeMergeResolver(
            config=v4_config.merge,
            token_limits=v4_config.tokens,
            token_counter=token_counter,
            budgeter=budgeter,
        ).resolve(drafts, updated_boundaries, retained_embeddings)

    boundary_rows = [
        _boundary_row(
            item,
            comparator_by_boundary[item.boundary_index],
            run_id,
        )
        for item in updated_boundaries
    ]
    chunks = _materialize_chunks(
        run_id=run_id,
        document_id=prepared[0].document_id,
        drafts=drafts,
        comparator_by_boundary=comparator_by_boundary,
        token_counter=token_counter,
        hard_max_tokens=v3_config.tokens.hard_max_tokens,
        embedding_provenance=embedding_provenance,
        base_metadata=base_metadata,
        config_hash=_config_hash(
            v3_config,
            v4_config,
            run_id,
            next(iter(comparator_by_boundary.values())).method_id,
            merge_enabled,
        ),
    )
    return chunks, boundary_rows


def _materialize_chunks(
    *,
    run_id: str,
    document_id: str,
    drafts: Sequence[V4ChunkDraft],
    comparator_by_boundary: Mapping[int, ComparatorBoundaryProvenance],
    token_counter: TokenCounter,
    hard_max_tokens: int,
    embedding_provenance: Mapping[str, dict[str, Any]],
    base_metadata: Mapping[str, Any],
    config_hash: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start_boundary = ChunkBoundary(reason="document_start")
    for index, draft in enumerate(drafts, start=1):
        text = render_units(draft.units)
        token_count = token_counter.count(text)
        if token_count > hard_max_tokens:
            raise AssertionError("Phase 3C comparator violated frozen hard cap")
        row: dict[str, Any] = {
            "chunk_id": f"{document_id}:phase3c-{run_id}-chunk-{index:04d}",
            "document_id": document_id,
            "text": text,
            "token_count": token_count,
            "unit_ids": _unique(
                unit_id
                for unit in draft.units
                for unit_id in unit.raw_unit_ids
            ),
            "content_unit_ids": [unit.unit_id for unit in draft.units],
            "section_paths": _unique_lists(
                list(unit.section_path) for unit in draft.units if unit.section_path
            ),
            "source_spans": _unique_dicts(
                span.model_dump(exclude_none=True)
                for unit in draft.units
                for span in unit.source_spans
            ),
            "start_boundary": _chunk_boundary_row(
                start_boundary,
                comparator_by_boundary,
                run_id,
            ),
            "end_boundary": _chunk_boundary_row(
                draft.end_boundary,
                comparator_by_boundary,
                run_id,
            ),
            "tail_coalesced": draft.tail_coalesced,
            "semantic_embeddings": [
                embedding_provenance[unit.unit_id]
                for unit in draft.units
                if unit.unit_id in embedding_provenance
            ],
            "algorithm_version": "amsc-phase3c-research",
            "research_ablation": run_id,
            "boundary_embedding_model": base_metadata["boundary_embedding_model"],
            "boundary_prefix_policy": base_metadata["boundary_prefix_policy"],
            "boundary_model_input_limit": base_metadata[
                "boundary_model_input_limit"
            ],
            "token_counter_id": token_counter.counter_id,
            "hard_cap_semantics": "configured_poc_counter_only",
            "config_hash": config_hash,
        }
        if draft.unmerged_short_tail_reason is not None:
            row["unmerged_short_tail_reason"] = draft.unmerged_short_tail_reason
        if draft.removed_tail_boundary_reason is not None:
            row["removed_tail_boundary_reason"] = draft.removed_tail_boundary_reason
        if draft.merge_decisions:
            row["merge_decisions"] = [
                item.model_dump(exclude_none=True) for item in draft.merge_decisions
            ]
        if draft.accepted_merge is not None:
            row["accepted_merge"] = draft.accepted_merge.model_dump(
                exclude_none=True
            )
        rows.append(row)
        start_boundary = draft.end_boundary
    return rows


def _write_and_evaluate(
    *,
    run_dir: Path,
    run_id: str,
    chunks: Sequence[dict[str, Any]],
    boundaries: Sequence[dict[str, Any]],
    comparator_by_boundary: Mapping[int, ComparatorBoundaryProvenance],
    resolved_config: dict[str, Any],
    units: Sequence[RawDocumentUnit],
    annotations: Any,
    units_sha: str,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(run_dir / "chunks.jsonl", chunks)
    _write_jsonl(run_dir / "boundaries.jsonl", boundaries)
    _write_jsonl(
        run_dir / "comparator-provenance.jsonl",
        [
            {
                "boundary_index": index,
                **comparator_by_boundary[index].model_dump(exclude_none=True),
            }
            for index in sorted(comparator_by_boundary)
        ],
    )
    _write_json(run_dir / "resolved-config.json", resolved_config)
    metrics = evaluate_checkpoint(
        units=units,
        annotations=annotations,
        chunks=chunks,
        boundaries=boundaries,
        resolved_config=resolved_config,
        units_sha256=units_sha,
    )
    metrics["research_ablation"] = run_id
    metrics["validation_status"] = "development_checkpoint_only"
    _write_json(run_dir / "metrics.json", metrics)
    return metrics


def _load_diagnostics(
    target: Path,
    run_ids: Sequence[str],
    units: Sequence[RawDocumentUnit],
    annotations: Any,
    units_sha: str,
) -> dict[str, RunDiagnostics]:
    result: dict[str, RunDiagnostics] = {}
    for run_id in run_ids:
        directory = target / run_id
        metrics = json.loads(
            (directory / "metrics.json").read_text(encoding="utf-8")
        )
        metrics.pop("research_ablation", None)
        metrics.pop("validation_status", None)
        diagnostic = analyze_run(
            run=DiagnosticRun(
                run_id=run_id,
                chunks=tuple(load_jsonl_objects(directory / "chunks.jsonl")),
                boundaries=tuple(load_jsonl_objects(directory / "boundaries.jsonl")),
                resolved_config=json.loads(
                    (directory / "resolved-config.json").read_text(encoding="utf-8")
                ),
                authoritative_metrics=metrics,
            ),
            units=units,
            annotations=annotations,
            units_sha256=units_sha,
        )
        result[run_id] = diagnostic
        _write_jsonl(
            target / f"{run_id}-predictions.jsonl",
            diagnostic.prediction_rows,
        )
    return result


def _select_development_winner(
    metrics: Mapping[str, Mapping[str, Any]],
    diagnostics: Mapping[str, RunDiagnostics],
) -> str:
    def rank(run_id: str) -> tuple[float, float, int, int]:
        boundary = metrics[run_id]["boundary_metrics"]
        semantic_fp = sum(
            diagnostics[run_id].summary["fp_by_reason"].get(reason, 0)
            for reason in (
                "adaptive_semantic_boundary",
                "fixed_semantic_boundary",
            )
        )
        return (
            boundary["primary_plus_minus_one"]["f1"],
            boundary["secondary_exact"]["f1"],
            -semantic_fp,
            1 if run_id == "c1" else 0,
        )

    return max(("c1", "c2"), key=rank)


def _build_summary(
    *,
    target: Path,
    diagnostics: Mapping[str, RunDiagnostics],
    comparator_by_run: Mapping[
        str, Mapping[int, ComparatorBoundaryProvenance]
    ],
    base_boundaries: Sequence[BoundaryEvidence],
    units: Sequence[RawDocumentUnit],
    winner_id: str,
    winner_method: str,
) -> dict[str, Any]:
    runs: dict[str, Any] = {}
    for run_id in ("c0", "c1", "c2", "c3"):
        metrics = json.loads(
            (target / run_id / "metrics.json").read_text(encoding="utf-8")
        )
        chunk = metrics["chunk_metrics"]
        summary = diagnostics[run_id].summary
        fp = summary["fp_by_reason"]
        semantic_fp = sum(
            fp.get(reason, 0)
            for reason in (
                "adaptive_semantic_boundary",
                "fixed_semantic_boundary",
            )
        )
        size_tp = summary["tp_by_reason"]["size_fallback_tp"]
        hard_tp = summary["tp_by_reason"]["hard_fallback_tp"]
        size_fp = fp.get("size_fallback", 0)
        hard_fp = fp.get("hard_limit_fallback", 0)
        runs[run_id] = {
            "exact": metrics["boundary_metrics"]["secondary_exact"],
            "plus_minus_one": metrics["boundary_metrics"][
                "primary_plus_minus_one"
            ],
            "semantic_tp": summary["tp_by_reason"]["semantic_tp"],
            "semantic_fp": semantic_fp,
            "size_fallback_tp": size_tp,
            "size_fallback_fp": size_fp,
            "hard_fallback_tp": hard_tp,
            "hard_fallback_fp": hard_fp,
            "fallback_tp": size_tp + hard_tp,
            "fallback_fp": size_fp + hard_fp,
            "fn": summary["missed"],
            "chunk_count": chunk["chunk_count"],
            "token_count": chunk["token_count"],
            "below_min_token_chunk_ratio": chunk[
                "below_min_token_chunk_ratio"
            ],
            "size_fallback_count": chunk["size_fallback_count"],
            "hard_fallback_count": chunk["hard_fallback_count"],
            "selected_semantic_boundary_count": chunk[
                "semantic_boundary_count"
            ],
            "merge_proposal_count": chunk["merge_proposal_count"],
            "accepted_merge_count": chunk["accepted_merge_count"],
        }

    status_by_run = {
        run_id: {row["annotation_id"]: row for row in item.gold_rows}
        for run_id, item in diagnostics.items()
    }
    original_missed = [
        row for row in diagnostics["c0"].gold_rows if row["status"] == "MISSED"
    ]
    boundary_by_gap = _boundary_index_by_raw_gap(base_boundaries, units)
    rescue_rows: list[dict[str, Any]] = []
    for original in original_missed:
        annotation_id = original["annotation_id"]
        gold_gap = int(original["gold_gap_index"])
        gold_boundary_index = boundary_by_gap.get(gold_gap)
        row: dict[str, Any] = {
            "annotation_id": annotation_id,
            "region_id": original["region_id"],
            "c0_status": original["status"],
            "c0_multi_scale_suppression": original[
                "multi_scale_suppression"
            ],
        }
        for run_id in ("c1", "c2", "c3"):
            current = status_by_run[run_id][annotation_id]
            gold_comparator = (
                comparator_by_run[run_id].get(gold_boundary_index)
                if gold_boundary_index is not None
                else None
            )
            reason = current["prediction_selected_reason"]
            semantic_rescue = (
                current["status"] != "MISSED"
                and reason == "adaptive_semantic_boundary"
            )
            row[f"{run_id}_status"] = current["status"]
            row[f"{run_id}_matched_gap"] = current["matched_prediction_gap"]
            row[f"{run_id}_matched_reason"] = reason
            row[f"{run_id}_genuine_semantic_rescue"] = semantic_rescue
            if gold_comparator is not None:
                row[f"{run_id}_gold_score"] = gold_comparator.score
                row[f"{run_id}_gold_threshold"] = (
                    gold_comparator.adaptive_threshold.value
                    if gold_comparator.adaptive_threshold is not None
                    else None
                )
                row[f"{run_id}_gold_candidate"] = (
                    gold_comparator.semantic_candidate
                )
                row[f"{run_id}_gold_evidence"] = (
                    gold_comparator.threshold_relative_evidence
                )
            if current["matched_prediction_gap"] is not None:
                boundary_index = boundary_by_gap.get(
                    current["matched_prediction_gap"]
                )
                comparator = (
                    comparator_by_run[run_id].get(boundary_index)
                    if boundary_index is not None
                    else None
                )
                if comparator is not None:
                    row[f"{run_id}_comparator_method"] = comparator.method_id
                    row[f"{run_id}_score"] = comparator.score
                    row[f"{run_id}_threshold"] = (
                        comparator.adaptive_threshold.value
                        if comparator.adaptive_threshold is not None
                        else None
                    )
                    row[f"{run_id}_evidence"] = (
                        comparator.threshold_relative_evidence
                    )
        rescue_rows.append(row)
    _write_jsonl(target / "high-fn-semantic-rescue.jsonl", rescue_rows)

    c0_status = status_by_run["c0"]
    regressions: dict[str, list[str]] = {}
    for run_id in ("c1", "c2", "c3"):
        regressions[run_id] = sorted(
            annotation_id
            for annotation_id, base in c0_status.items()
            if base["status"] != "MISSED"
            and status_by_run[run_id][annotation_id]["status"] == "MISSED"
        )
    return {
        "schema_version": "1.0",
        "status": "development_comparator_research_only",
        "validated": False,
        "gold_parameter_tuning": False,
        "canonical_sha256": AUTHORITATIVE_CANONICAL_SHA256,
        "c0_byte_identical": all(
            (target / "c0" / name).read_bytes()
            == (target.parent / "baseline" / "v3" / name).read_bytes()
            for name in _CORE_FILES
        ),
        "winner_for_c3": winner_id,
        "winner_method": winner_method,
        "winner_selection_policy": (
            "development primary F1, then exact F1, then fewer semantic FP, "
            "then deterministic C1 tie-break; no parameter fitting"
        ),
        "runs": runs,
        "comparator_candidate_count": {
            run_id: sum(
                item.semantic_candidate
                for item in comparator_by_run[run_id].values()
            )
            for run_id in ("c1", "c2", "c3")
        },
        "original_seven_high_fn": rescue_rows,
        "genuine_semantic_rescues": {
            run_id: [
                row["annotation_id"]
                for row in rescue_rows
                if row[f"{run_id}_genuine_semantic_rescue"]
            ]
            for run_id in ("c1", "c2", "c3")
        },
        "regressed_previously_matched_high": regressions,
    }


def _render_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Phase 3C Semantic Comparator Research",
        "",
        "> Development checkpoint only. No gold annotation was used for parameter "
        "tuning, and no validation claim is made.",
        "",
        f"C3 uses `{summary['winner_for_c3']}` / `{summary['winner_method']}` plus "
        "the frozen post-conformance semantic-safe merge.",
        "",
        "## C0–C3 metrics",
        "",
        "| Run | Exact P/R/F1 | ±1 P/R/F1 | Semantic TP/FP | Fallback TP/FP | FN | Chunks | Token min/med/P90/max | <160 | Size/hard fallback |",
        "|---|---|---|---:|---:|---:|---:|---|---:|---:|",
    ]
    for run_id in ("c0", "c1", "c2", "c3"):
        run = summary["runs"][run_id]
        exact = run["exact"]
        primary = run["plus_minus_one"]
        token = run["token_count"]
        lines.append(
            f"| {run_id.upper()} | {exact['precision']:.4f}/{exact['recall']:.4f}/{exact['f1']:.4f} | "
            f"{primary['precision']:.4f}/{primary['recall']:.4f}/{primary['f1']:.4f} | "
            f"{run['semantic_tp']}/{run['semantic_fp']} | "
            f"{run['fallback_tp']}/{run['fallback_fp']} | {run['fn']} | "
            f"{run['chunk_count']} | {token['min']}/{token['median']:.1f}/"
            f"{token['p90_nearest_rank']}/{token['max']} | "
            f"{run['below_min_token_chunk_ratio']:.2%} | "
            f"{run['size_fallback_count']}/{run['hard_fallback_count']} |"
        )
    lines.extend(
        [
            "",
            "## Existing seven HIGH false negatives",
            "",
            "| Annotation | Suppression | C1 status/reason | C2 status/reason | C3 status/reason |",
            "|---|---:|---|---|---|",
        ]
    )
    for row in summary["original_seven_high_fn"]:
        lines.append(
            f"| {row['annotation_id']} | "
            f"{str(row['c0_multi_scale_suppression']).lower()} | "
            f"{row['c1_status']}/{row['c1_matched_reason'] or '-'} | "
            f"{row['c2_status']}/{row['c2_matched_reason'] or '-'} | "
            f"{row['c3_status']}/{row['c3_matched_reason'] or '-'} |"
        )
    lines.extend(["", "### Genuine semantic rescues", ""])
    for run_id in ("c1", "c2", "c3"):
        rescued = summary["genuine_semantic_rescues"][run_id]
        lines.append(f"- {run_id.upper()}: {', '.join(rescued) if rescued else 'none'}")
    lines.extend(
        [
            "",
            "### Gold-position comparator evidence",
            "",
            "| Annotation | C1 score/threshold/candidate | C2 score/threshold/candidate |",
            "|---|---|---|",
        ]
    )
    for row in summary["original_seven_high_fn"]:
        c1_threshold = row.get("c1_gold_threshold")
        c2_threshold = row.get("c2_gold_threshold")
        lines.append(
            f"| {row['annotation_id']} | "
            f"{row.get('c1_gold_score', 0.0):.6f}/"
            f"{_format_optional_float(c1_threshold)}"
            f"/{str(row.get('c1_gold_candidate')).lower()} | "
            f"{row.get('c2_gold_score', 0.0):.6f}/"
            f"{_format_optional_float(c2_threshold)}"
            f"/{str(row.get('c2_gold_candidate')).lower()} |"
        )
    lines.extend(["", "### Previously matched HIGH regressions", ""])
    for run_id in ("c1", "c2", "c3"):
        regressed = summary["regressed_previously_matched_high"][run_id]
        lines.append(
            f"- {run_id.upper()}: {', '.join(regressed) if regressed else 'none'}"
        )
    return "\n".join(lines) + "\n"


def _format_optional_float(value: Any) -> str:
    return "-" if value is None else f"{float(value):.6f}"


def _copy_control(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in _CORE_FILES:
        shutil.copyfile(source / name, destination / name)
        if (source / name).read_bytes() != (destination / name).read_bytes():
            raise AssertionError(f"C0 byte copy failed for {name}")


def _assert_v3_control(metrics: Mapping[str, Any]) -> None:
    boundary = metrics["boundary_metrics"]
    if (
        boundary["secondary_exact"]["f1"] != AUTHORITATIVE_V3_EXACT_F1
        or boundary["primary_plus_minus_one"]["f1"]
        != AUTHORITATIVE_V3_PLUS_MINUS_ONE_F1
    ):
        raise ValueError("C0 is not the authoritative V3 baseline")


def _resolved_config(
    v3: V3Config,
    v4: V4Config,
    run_id: str,
    method_id: str,
    *,
    merge_enabled: bool,
    winner_id: str | None = None,
) -> dict[str, Any]:
    payload = v3.model_dump(mode="json")
    payload["algorithm"] = {
        "version": "phase3c-research",
        "tuning_status": "no_gold_parameter_tuning",
    }
    payload["research"] = {
        "ablation": run_id,
        "comparator_method": method_id,
        "development_checkpoint": True,
        "gold_parameter_tuning": False,
        "validated": False,
    }
    if winner_id is not None:
        payload["research"]["winner_source"] = winner_id
    if merge_enabled:
        payload["merge"] = v4.merge.model_dump(mode="json")
    return payload


def _config_hash(
    v3: V3Config,
    v4: V4Config,
    run_id: str,
    method_id: str,
    merge_enabled: bool,
) -> str:
    canonical = json.dumps(
        _resolved_config(
            v3,
            v4,
            run_id,
            method_id,
            merge_enabled=merge_enabled,
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _boundary_row(
    boundary: BoundaryEvidence,
    comparator: ComparatorBoundaryProvenance,
    run_id: str,
) -> dict[str, Any]:
    row = boundary.model_dump(exclude_none=True)
    row["research_ablation"] = run_id
    row["semantic_candidate_strategy"] = comparator.method_id
    row["comparator"] = comparator.model_dump(exclude_none=True)
    return row


def _chunk_boundary_row(
    boundary: ChunkBoundary,
    comparator_by_boundary: Mapping[int, ComparatorBoundaryProvenance],
    run_id: str,
) -> dict[str, Any]:
    row = boundary.model_dump(exclude_none=True)
    if boundary.boundary_index is not None:
        comparator = comparator_by_boundary[boundary.boundary_index]
        row["research_ablation"] = run_id
        row["semantic_candidate_strategy"] = comparator.method_id
        row["comparator"] = comparator.model_dump(exclude_none=True)
    return row


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m amsc.phase3c_research")
    parser.add_argument("--units", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--v3-output", required=True, type=Path)
    parser.add_argument("--v3-config", required=True, type=Path)
    parser.add_argument("--v4-config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = run_phase3c_research(
        units_path=args.units,
        annotations_path=args.annotations,
        v3_output_dir=args.v3_output,
        v3_config_path=args.v3_config,
        v4_config_path=args.v4_config,
        output_dir=args.output,
    )
    print(
        json.dumps(
            {
                "status": summary["status"],
                "winner_for_c3": summary["winner_for_c3"],
                "output": str(args.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
