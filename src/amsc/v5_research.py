from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any

import numpy as np

from .cache import FileEmbeddingCache
from .config import V3Config, V4Config
from .embeddings import SemanticFragmentPooler
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
from .scale_calibration import (
    PerScaleAdaptiveCalibrator,
    ScaleCalibratedIntervalBoundarySelector,
    ScaleCalibrationProvenance,
)
from .selection import V2TailResolver
from .strength import DualBoundaryStrengthAnnotator
from .tokenization import TiktokenTokenCounter, TokenCounter
from .units import HeadingAttachmentBuilder, RenderedTokenBudgeter, render_units


AUTHORITATIVE_CANONICAL_SHA256 = (
    "2776742d5bddad7dcf2a03320dca36e6b384e2ba042ab99ccdecce61612720d5"
)
AUTHORITATIVE_V3_EXACT_F1 = 0.4137931034482759
AUTHORITATIVE_V3_PLUS_MINUS_ONE_F1 = 0.5517241379310344
_FRAGMENT_SUFFIX = re.compile(r"#(?:heading-)?fragment-\d+$")
_CORE_FILES = (
    "chunks.jsonl",
    "boundaries.jsonl",
    "metrics.json",
    "resolved-config.json",
)


def run_scale_calibration_research(
    *,
    units_path: str | Path,
    annotations_path: str | Path,
    v3_output_dir: str | Path,
    v3_config_path: str | Path,
    v4_config_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Run B0-B3 without mutating frozen V1-V4 artifacts or code paths."""

    units_path = Path(units_path)
    annotations_path = Path(annotations_path)
    v3_output_dir = Path(v3_output_dir)
    target = Path(output_dir)
    units_sha = sha256_file(units_path)
    if units_sha != AUTHORITATIVE_CANONICAL_SHA256:
        raise ValueError(
            "V5 research requires the frozen KKB canonical input; "
            f"observed {units_sha}"
        )

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
    base_boundary_rows = load_jsonl_objects(v3_output_dir / "boundaries.jsonl")
    base_boundaries = [
        BoundaryEvidence.model_validate(row) for row in base_boundary_rows
    ]
    base_metrics = json.loads(
        (v3_output_dir / "metrics.json").read_text(encoding="utf-8")
    )
    _assert_authoritative_v3(base_metrics)
    _assert_boundary_unit_alignment(base_boundaries, units_by_id)

    calibrations = PerScaleAdaptiveCalibrator(
        v3_config.semantic,
        v3_config.multi_scale,
    ).apply(base_boundaries, units_by_id)
    target.mkdir(parents=True, exist_ok=True)

    b0_dir = target / "b0"
    _copy_byte_identical_baseline(v3_output_dir, b0_dir)
    _write_research_manifest(
        b0_dir,
        research_id="b0",
        description="Authoritative V3 byte-identical control",
        units_sha=units_sha,
        source_dir=v3_output_dir,
    )

    b1_dir = target / "b1"
    _copy_byte_identical_baseline(v3_output_dir, b1_dir)
    _write_calibration_sidecar(b1_dir, calibrations)
    _write_research_manifest(
        b1_dir,
        research_id="b1",
        description=(
            "Diagnostic per-scale hierarchical adaptive thresholds; "
            "chunk and boundary decisions remain authoritative V3"
        ),
        units_sha=units_sha,
        source_dir=v3_output_dir,
    )

    embedding_provenance = _embedding_provenance_by_unit(base_chunks)
    base_metadata = _base_chunk_metadata(base_chunks)
    b2_chunks, b2_boundaries = _run_calibrated_selection(
        research_id="b2",
        prepared=prepared,
        base_boundaries=base_boundaries,
        calibrations=calibrations,
        v3_config=v3_config,
        v4_config=v4_config,
        token_counter=token_counter,
        budgeter=budgeter,
        embedding_provenance=embedding_provenance,
        base_metadata=base_metadata,
        retained_embeddings=None,
        merge_enabled=False,
    )
    b2_config = _resolved_research_config(v3_config, v4_config, "b2")
    b2_metrics = _write_and_evaluate_run(
        run_dir=target / "b2",
        research_id="b2",
        chunks=b2_chunks,
        boundaries=b2_boundaries,
        calibrations=calibrations,
        resolved_config=b2_config,
        units=units,
        annotations=annotations,
        units_sha=units_sha,
    )

    retained_embeddings = _load_retained_embeddings(
        prepared,
        v3_config,
        base_metadata,
    )
    b3_chunks, b3_boundaries = _run_calibrated_selection(
        research_id="b3",
        prepared=prepared,
        base_boundaries=base_boundaries,
        calibrations=calibrations,
        v3_config=v3_config,
        v4_config=v4_config,
        token_counter=token_counter,
        budgeter=budgeter,
        embedding_provenance=embedding_provenance,
        base_metadata=base_metadata,
        retained_embeddings=retained_embeddings,
        merge_enabled=True,
    )
    b3_config = _resolved_research_config(v3_config, v4_config, "b3")
    b3_metrics = _write_and_evaluate_run(
        run_dir=target / "b3",
        research_id="b3",
        chunks=b3_chunks,
        boundaries=b3_boundaries,
        calibrations=calibrations,
        resolved_config=b3_config,
        units=units,
        annotations=annotations,
        units_sha=units_sha,
    )

    diagnostics = _build_diagnostics(
        target=target,
        units=units,
        annotations=annotations,
        units_sha=units_sha,
    )
    summary = _research_summary(
        target=target,
        diagnostics=diagnostics,
        calibrations=calibrations,
        boundaries=base_boundaries,
        units=units,
        b2_metrics=b2_metrics,
        b3_metrics=b3_metrics,
    )
    _write_json(
        target / "summary.json",
        summary,
    )
    (target / "scale-calibration-report.md").write_text(
        _render_markdown(summary),
        encoding="utf-8",
        newline="\n",
    )
    return summary


def _run_calibrated_selection(
    *,
    research_id: str,
    prepared: Sequence[ContentUnit],
    base_boundaries: Sequence[BoundaryEvidence],
    calibrations: Mapping[int, ScaleCalibrationProvenance],
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
                "semantic_candidate": calibrations[
                    boundary.boundary_index
                ].fused_candidate,
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
    selector = ScaleCalibratedIntervalBoundarySelector(
        budgeter=budgeter,
        token_limits=v3_config.tokens,
        semantic=None,
        selection=v3_config.selection,
        semantic_boundary_reason="adaptive_semantic_boundary",
        tail_resolver=V2TailResolver(budgeter, v3_config.tokens),
        removed_tail_selected_reason=(
            f"removed_by_v5_research_{research_id}_tail_coalescing"
        ),
        calibration_by_boundary=calibrations,
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
            raise ValueError("B3 merge requires retained cached embeddings")
        resolver = SemanticSafeMergeResolver(
            config=v4_config.merge,
            token_limits=v4_config.tokens,
            token_counter=token_counter,
            budgeter=budgeter,
        )
        drafts, updated_boundaries = resolver.resolve(
            drafts,
            updated_boundaries,
            retained_embeddings,
        )

    boundary_rows = [
        _boundary_row(item, calibrations[item.boundary_index], research_id)
        for item in updated_boundaries
    ]
    config_hash = _research_config_hash(v3_config, v4_config, research_id)
    chunks = _materialize_chunks(
        research_id=research_id,
        document_id=prepared[0].document_id,
        drafts=drafts,
        calibrations=calibrations,
        token_counter=token_counter,
        hard_max_tokens=v3_config.tokens.hard_max_tokens,
        embedding_provenance=embedding_provenance,
        base_metadata=base_metadata,
        config_hash=config_hash,
    )
    return chunks, boundary_rows


def _materialize_chunks(
    *,
    research_id: str,
    document_id: str,
    drafts: Sequence[V4ChunkDraft],
    calibrations: Mapping[int, ScaleCalibrationProvenance],
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
            raise AssertionError("V5 research selection violated frozen hard cap")
        row: dict[str, Any] = {
            "chunk_id": f"{document_id}:v5-{research_id}-chunk-{index:04d}",
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
                calibrations,
                research_id,
            ),
            "end_boundary": _chunk_boundary_row(
                draft.end_boundary,
                calibrations,
                research_id,
            ),
            "tail_coalesced": draft.tail_coalesced,
            "semantic_embeddings": [
                embedding_provenance[unit.unit_id]
                for unit in draft.units
                if unit.unit_id in embedding_provenance
            ],
            "algorithm_version": "amsc-v5-research",
            "research_ablation": research_id,
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
            row["removed_tail_boundary_reason"] = (
                draft.removed_tail_boundary_reason
            )
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


def _write_and_evaluate_run(
    *,
    run_dir: Path,
    research_id: str,
    chunks: Sequence[dict[str, Any]],
    boundaries: Sequence[dict[str, Any]],
    calibrations: Mapping[int, ScaleCalibrationProvenance],
    resolved_config: dict[str, Any],
    units: Sequence[RawDocumentUnit],
    annotations: Any,
    units_sha: str,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(run_dir / "chunks.jsonl", chunks)
    _write_jsonl(run_dir / "boundaries.jsonl", boundaries)
    _write_calibration_sidecar(run_dir, calibrations)
    _write_json(run_dir / "resolved-config.json", resolved_config)
    metrics = evaluate_checkpoint(
        units=units,
        annotations=annotations,
        chunks=chunks,
        boundaries=boundaries,
        resolved_config=resolved_config,
        units_sha256=units_sha,
    )
    metrics["research_ablation"] = research_id
    metrics["validation_status"] = "development_checkpoint_only"
    _write_json(run_dir / "metrics.json", metrics)
    _write_research_manifest(
        run_dir,
        research_id=research_id,
        description=(
            "Per-scale calibrated fusion"
            + (" plus frozen semantic-safe merge" if research_id == "b3" else "")
        ),
        units_sha=units_sha,
        source_dir=None,
    )
    return metrics


def _build_diagnostics(
    *,
    target: Path,
    units: Sequence[RawDocumentUnit],
    annotations: Any,
    units_sha: str,
) -> dict[str, RunDiagnostics]:
    diagnostics: dict[str, RunDiagnostics] = {}
    for run_id in ("b0", "b1", "b2", "b3"):
        directory = target / run_id
        run = DiagnosticRun(
            run_id=run_id,
            chunks=tuple(load_jsonl_objects(directory / "chunks.jsonl")),
            boundaries=tuple(load_jsonl_objects(directory / "boundaries.jsonl")),
            resolved_config=json.loads(
                (directory / "resolved-config.json").read_text(encoding="utf-8")
            ),
            authoritative_metrics=json.loads(
                (directory / "metrics.json").read_text(encoding="utf-8")
            ),
        )
        # Research metrics append labels outside the authoritative evaluator result.
        run_metrics = dict(run.authoritative_metrics)
        run_metrics.pop("research_ablation", None)
        run_metrics.pop("validation_status", None)
        run = DiagnosticRun(
            run_id=run.run_id,
            chunks=run.chunks,
            boundaries=run.boundaries,
            resolved_config=run.resolved_config,
            authoritative_metrics=run_metrics,
        )
        diagnostics[run_id] = analyze_run(
            run=run,
            units=units,
            annotations=annotations,
            units_sha256=units_sha,
        )
        _write_jsonl(
            target / f"{run_id}-predictions.jsonl",
            diagnostics[run_id].prediction_rows,
        )
    return diagnostics


def _research_summary(
    *,
    target: Path,
    diagnostics: Mapping[str, RunDiagnostics],
    calibrations: Mapping[int, ScaleCalibrationProvenance],
    boundaries: Sequence[BoundaryEvidence],
    units: Sequence[RawDocumentUnit],
    b2_metrics: Mapping[str, Any],
    b3_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    del b2_metrics, b3_metrics
    runs: dict[str, Any] = {}
    for run_id, diagnostic in diagnostics.items():
        metrics = json.loads(
            (target / run_id / "metrics.json").read_text(encoding="utf-8")
        )
        boundary_metrics = metrics["boundary_metrics"]
        chunk_metrics = metrics["chunk_metrics"]
        summary = diagnostic.summary
        fp = summary["fp_by_reason"]
        runs[run_id] = {
            "exact": boundary_metrics["secondary_exact"],
            "plus_minus_one": boundary_metrics["primary_plus_minus_one"],
            "semantic_tp": summary["tp_by_reason"]["semantic_tp"],
            "size_tp": summary["tp_by_reason"]["size_fallback_tp"],
            "hard_tp": summary["tp_by_reason"]["hard_fallback_tp"],
            "semantic_fp": sum(
                fp.get(reason, 0)
                for reason in (
                    "adaptive_semantic_boundary",
                    "fixed_semantic_boundary",
                )
            ),
            "size_fp": fp.get("size_fallback", 0),
            "hard_fp": fp.get("hard_limit_fallback", 0),
            "fn": summary["missed"],
            "multi_scale_suppression_fn": summary[
                "multi_scale_suppression_high_fn"
            ],
            "chunk_count": chunk_metrics["chunk_count"],
            "below_160_ratio": chunk_metrics["below_min_token_chunk_ratio"],
            "size_fallback_count": chunk_metrics["size_fallback_count"],
            "hard_fallback_count": chunk_metrics["hard_fallback_count"],
        }

    b0_missed = {
        row["annotation_id"]: row
        for row in diagnostics["b0"].gold_rows
        if row["status"] == "MISSED"
    }
    status_by_run = {
        run_id: {row["annotation_id"]: row for row in item.gold_rows}
        for run_id, item in diagnostics.items()
    }
    boundary_by_raw_gap = _boundary_index_by_raw_gap(boundaries, units)
    rescue_rows: list[dict[str, Any]] = []
    for annotation_id, original in b0_missed.items():
        gold_gap = int(original["gold_gap_index"])
        gold_boundary_index = boundary_by_raw_gap.get(gold_gap)
        gold_calibration = (
            calibrations.get(gold_boundary_index)
            if gold_boundary_index is not None
            else None
        )
        row: dict[str, Any] = {
            "annotation_id": annotation_id,
            "region_id": original["region_id"],
            "b0_multi_scale_suppression": original[
                "multi_scale_suppression"
            ],
            "b0_shift_1": original["shift_1"],
            "b0_shift_2": original["shift_2"],
            "b0_shift_3": original["shift_3"],
            "b0_combined_shift": original["semantic_shift"],
            "b0_threshold": original["threshold"],
            "b1_candidate_scales_at_gold": (
                _candidate_scales(gold_calibration) if gold_calibration else []
            ),
            "b1_per_scale_at_gold": (
                _scale_diagnostic_rows(gold_calibration)
                if gold_calibration
                else []
            ),
        }
        for run_id in ("b0", "b1", "b2", "b3"):
            current = status_by_run[run_id][annotation_id]
            row[f"{run_id}_status"] = current["status"]
            row[f"{run_id}_matched_prediction_gap"] = current[
                "matched_prediction_gap"
            ]
            row[f"{run_id}_matched_reason"] = current[
                "prediction_selected_reason"
            ]
            rescued = (
                run_id in {"b2", "b3"}
                and current["status"] != "MISSED"
            )
            row[f"{run_id}_rescued"] = rescued
            if run_id in {"b2", "b3"} and rescued:
                predicted_gap = current["matched_prediction_gap"]
                boundary_index = boundary_by_raw_gap.get(predicted_gap)
                calibration = (
                    calibrations.get(boundary_index)
                    if boundary_index is not None
                    else None
                )
                row[f"{run_id}_rescued_by_scales"] = (
                    _candidate_scales(calibration) if calibration else []
                )
                reason = current["prediction_selected_reason"]
                row[f"{run_id}_rescue_mechanism"] = (
                    "calibrated_semantic_evidence"
                    if reason == "adaptive_semantic_boundary"
                    and row[f"{run_id}_rescued_by_scales"]
                    else f"indirect_{reason}"
                )
        rescue_rows.append(row)
    _write_jsonl(target / "high-fn-rescue-analysis.jsonl", rescue_rows)

    b0_hashes = {
        name: sha256_file(target / "b0" / name) for name in _CORE_FILES
    }
    source_hashes = {
        name: sha256_file(target.parent / "baseline" / "v3" / name)
        if (target.parent / "baseline" / "v3" / name).exists()
        else b0_hashes[name]
        for name in _CORE_FILES
    }
    b2_promising = (
        runs["b2"]["plus_minus_one"]["f1"]
        >= runs["b0"]["plus_minus_one"]["f1"]
        and runs["b2"]["semantic_fp"] <= runs["b0"]["semantic_fp"]
        and any(
            row.get("b2_rescue_mechanism")
            == "calibrated_semantic_evidence"
            for row in rescue_rows
            if row["b0_multi_scale_suppression"]
        )
    )
    b3_promising = (
        runs["b3"]["plus_minus_one"]["f1"]
        >= runs["b0"]["plus_minus_one"]["f1"]
        and runs["b3"]["semantic_fp"] <= runs["b0"]["semantic_fp"]
        and any(
            row.get("b3_rescue_mechanism")
            == "calibrated_semantic_evidence"
            for row in rescue_rows
            if row["b0_multi_scale_suppression"]
        )
    )
    return {
        "schema_version": "1.0",
        "status": "research_complete_on_development_checkpoint",
        "outcome": (
            "promising_on_development_checkpoint"
            if b2_promising or b3_promising
            else "hypothesis_not_supported_on_development_checkpoint"
        ),
        "hypothesis_supported": b2_promising or b3_promising,
        "validation_claim": "not_validated_requires_second_document_holdout",
        "canonical_sha256": AUTHORITATIVE_CANONICAL_SHA256,
        "research_hypothesis": (
            "Per-scale local adaptive calibration can preserve strong topic "
            "shifts without gold-fitted parameters."
        ),
        "calibration_formula": (
            "max(0, (shift_k - adaptive_threshold_k) / "
            "(1 - adaptive_threshold_k)); available-scale weighted mean; "
            "candidate if any scale is an adaptive candidate"
        ),
        "gold_fitting": False,
        "b0_byte_identical": b0_hashes == source_hashes,
        "b0_hashes": b0_hashes,
        "per_scale_diagnostics": _per_scale_summary(calibrations),
        "runs": runs,
        "original_high_fn_analysis": rescue_rows,
        "suppression_case_count": sum(
            bool(row["b0_multi_scale_suppression"]) for row in rescue_rows
        ),
        "suppression_rescued_b2": sum(
            bool(row["b0_multi_scale_suppression"] and row["b2_rescued"])
            for row in rescue_rows
        ),
        "suppression_rescued_b3": sum(
            bool(row["b0_multi_scale_suppression"] and row["b3_rescued"])
            for row in rescue_rows
        ),
        "suppression_semantic_rescued_b2": sum(
            row.get("b2_rescue_mechanism")
            == "calibrated_semantic_evidence"
            for row in rescue_rows
            if row["b0_multi_scale_suppression"]
        ),
        "suppression_semantic_rescued_b3": sum(
            row.get("b3_rescue_mechanism")
            == "calibrated_semantic_evidence"
            for row in rescue_rows
            if row["b0_multi_scale_suppression"]
        ),
    }


def _render_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# V5 Scale Calibration Research — KKB Development Checkpoint",
        "",
        f"> Outcome: {summary['outcome'].replace('_', ' ')}. This is a development "
        "checkpoint only; V5 is not validated.",
        "",
        "No KKB gold annotation was used to fit weights, thresholds, or constants. "
        "B1 is diagnostic-only; B2 uses the frozen per-scale estimator, frozen V3 "
        "scale weights, and threshold-relative excess. B3 adds the unchanged "
        "post-conformance semantic-safe merge.",
        "",
        "## B0–B3 results",
        "",
        "| Run | Exact P/R/F1 | ±1 P/R/F1 | Sem TP/FP | Size TP/FP | Hard TP/FP | FN | Suppression FN | Chunks | <160 | Size fallback | Hard fallback |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for run_id in ("b0", "b1", "b2", "b3"):
        run = summary["runs"][run_id]
        exact = run["exact"]
        primary = run["plus_minus_one"]
        lines.append(
            f"| {run_id.upper()} | {exact['precision']:.4f}/{exact['recall']:.4f}/{exact['f1']:.4f} | "
            f"{primary['precision']:.4f}/{primary['recall']:.4f}/{primary['f1']:.4f} | "
            f"{run['semantic_tp']}/{run['semantic_fp']} | "
            f"{run['size_tp']}/{run['size_fp']} | "
            f"{run['hard_tp']}/{run['hard_fp']} | {run['fn']} | "
            f"{run['multi_scale_suppression_fn']} | {run['chunk_count']} | "
            f"{run['below_160_ratio']:.2%} | {run['size_fallback_count']} | "
            f"{run['hard_fallback_count']} |"
        )
    lines.extend(
        [
            "",
            "## Original seven HIGH false negatives",
            "",
        "| Annotation | Suppression | B1 candidate scales at gold | B0 | B1 | B2 | B2 mechanism/scales | B3 | B3 mechanism/scales |",
        "|---|---:|---|---|---|---|---|---|---|",
        ]
    )
    for row in summary["original_high_fn_analysis"]:
        lines.append(
            f"| {row['annotation_id']} | {str(row['b0_multi_scale_suppression']).lower()} | "
            f"{','.join(map(str, row['b1_candidate_scales_at_gold'])) or 'none'} | "
            f"{row['b0_status']} | {row['b1_status']} | {row['b2_status']} | "
            f"{row.get('b2_rescue_mechanism', '-')}/"
            f"{','.join(map(str, row.get('b2_rescued_by_scales', []))) or '-'} | "
            f"{row['b3_status']} | {row.get('b3_rescue_mechanism', '-')}/"
            f"{','.join(map(str, row.get('b3_rescued_by_scales', []))) or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Guardrail",
            "",
            "KKB is a development checkpoint. Better B2/B3 scores are evidence for "
            "a holdout experiment, not evidence that V5 is validated.",
            "",
        ]
    )
    return "\n".join(lines)


def _assert_frozen_shared_config(v3: V3Config, v4: V4Config) -> None:
    for field in (
        "token_counter",
        "boundary_embedding",
        "semantic",
        "multi_scale",
        "tokens",
    ):
        if getattr(v3, field) != getattr(v4, field):
            raise ValueError(f"Frozen V3/V4 shared config diverges at {field}")


def _assert_authoritative_v3(metrics: Mapping[str, Any]) -> None:
    boundary = metrics["boundary_metrics"]
    exact = boundary["secondary_exact"]["f1"]
    primary = boundary["primary_plus_minus_one"]["f1"]
    if exact != AUTHORITATIVE_V3_EXACT_F1 or primary != AUTHORITATIVE_V3_PLUS_MINUS_ONE_F1:
        raise ValueError("B0 does not match the authoritative V3 metric freeze")


def _assert_boundary_unit_alignment(
    boundaries: Sequence[BoundaryEvidence],
    units_by_id: Mapping[str, ContentUnit],
) -> None:
    for boundary in boundaries:
        if boundary.left_unit_id not in units_by_id:
            raise ValueError(f"Unknown left prepared unit: {boundary.left_unit_id}")
        if boundary.right_unit_id not in units_by_id:
            raise ValueError(f"Unknown right prepared unit: {boundary.right_unit_id}")


def _copy_byte_identical_baseline(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in _CORE_FILES:
        shutil.copyfile(source / name, destination / name)
        if sha256_file(source / name) != sha256_file(destination / name):
            raise AssertionError(f"Byte-identical B0 copy failed for {name}")


def _write_calibration_sidecar(
    directory: Path,
    calibrations: Mapping[int, ScaleCalibrationProvenance],
) -> None:
    rows = [
        {
            "boundary_index": index,
            **calibrations[index].model_dump(exclude_none=True),
        }
        for index in sorted(calibrations)
    ]
    _write_jsonl(directory / "scale-calibration.jsonl", rows)


def _write_research_manifest(
    directory: Path,
    *,
    research_id: str,
    description: str,
    units_sha: str,
    source_dir: Path | None,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "research_id": research_id,
        "description": description,
        "canonical_sha256": units_sha,
        "development_checkpoint": True,
        "gold_parameter_fitting": False,
        "validated": False,
    }
    if source_dir is not None:
        payload["source_artifact_hashes"] = {
            name: sha256_file(source_dir / name) for name in _CORE_FILES
        }
    _write_json(directory / "research-manifest.json", payload)


def _resolved_research_config(
    v3: V3Config,
    v4: V4Config,
    research_id: str,
) -> dict[str, Any]:
    payload = v3.model_dump(mode="json")
    payload["algorithm"] = {
        "version": "v5-research",
        "tuning_status": "no_gold_parameter_fitting",
    }
    payload["research"] = {
        "ablation": research_id,
        "calibration": "per_scale_adaptive_threshold_relative_excess",
        "fusion": "available_scale_weighted_mean",
        "candidate_policy": "any_per_scale_adaptive_candidate",
        "development_checkpoint": True,
        "validated": False,
    }
    if research_id == "b3":
        payload["merge"] = v4.merge.model_dump(mode="json")
    return payload


def _research_config_hash(v3: V3Config, v4: V4Config, research_id: str) -> str:
    canonical = json.dumps(
        _resolved_research_config(v3, v4, research_id),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _embedding_provenance_by_unit(
    chunks: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        for item in chunk.get("semantic_embeddings") or []:
            result[str(item["unit_id"])] = dict(item)
    return result


def _base_chunk_metadata(chunks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not chunks:
        raise ValueError("Authoritative V3 baseline has no chunks")
    first = chunks[0]
    return {
        key: first[key]
        for key in (
            "boundary_embedding_model",
            "boundary_prefix_policy",
            "boundary_model_input_limit",
        )
    }


def _load_retained_embeddings(
    prepared: Sequence[ContentUnit],
    config: V3Config,
    metadata: Mapping[str, Any],
) -> dict[str, np.ndarray]:
    namespace = "|".join(
        [
            "semantic-boundary",
            str(metadata["boundary_embedding_model"]),
            str(metadata["boundary_prefix_policy"]),
            config.boundary_embedding.prefix,
            str(metadata["boundary_model_input_limit"]),
            SemanticFragmentPooler.POLICY_VERSION,
        ]
    )
    cache = FileEmbeddingCache(config.boundary_embedding.cache_dir)
    retained: dict[str, np.ndarray] = {}
    for unit in prepared:
        text = unit.text_for_embedding
        if text is None:
            continue
        key = hashlib.sha256((namespace + "\0" + text).encode("utf-8")).hexdigest()
        entry = cache.get(key)
        if entry is None:
            raise ValueError(
                "Frozen boundary embedding cache is incomplete for prepared unit "
                f"{unit.unit_id}; V5 research does not silently re-embed"
            )
        retained[unit.unit_id] = np.asarray(entry.vector, dtype=np.float64)
    return retained


def _boundary_row(
    boundary: BoundaryEvidence,
    calibration: ScaleCalibrationProvenance,
    research_id: str,
) -> dict[str, Any]:
    row = boundary.model_dump(exclude_none=True)
    row["research_ablation"] = research_id
    row["semantic_candidate_strategy"] = "any_per_scale_adaptive_candidate"
    row["scale_calibration"] = calibration.model_dump(exclude_none=True)
    return row


def _chunk_boundary_row(
    boundary: ChunkBoundary,
    calibrations: Mapping[int, ScaleCalibrationProvenance],
    research_id: str,
) -> dict[str, Any]:
    row = boundary.model_dump(exclude_none=True)
    if boundary.boundary_index is not None:
        row["research_ablation"] = research_id
        row["semantic_candidate_strategy"] = (
            "any_per_scale_adaptive_candidate"
        )
        row["scale_calibration"] = calibrations[
            boundary.boundary_index
        ].model_dump(exclude_none=True)
    return row


def _boundary_index_by_raw_gap(
    boundaries: Sequence[BoundaryEvidence],
    units: Sequence[RawDocumentUnit],
) -> dict[int, int]:
    content = [unit for unit in units if unit.type.value != "heading"]
    content_index = {unit.unit_id: index for index, unit in enumerate(content)}
    result: dict[int, int] = {}
    for boundary in boundaries:
        left = _FRAGMENT_SUFFIX.sub("", boundary.left_unit_id)
        right = _FRAGMENT_SUFFIX.sub("", boundary.right_unit_id)
        if left not in content_index or right not in content_index:
            continue
        if content_index[right] == content_index[left] + 1:
            result[content_index[left]] = boundary.boundary_index
    return result


def _candidate_scales(
    calibration: ScaleCalibrationProvenance,
) -> list[int]:
    return [
        scale
        for scale in calibration.available_scales
        if getattr(calibration, f"candidate_{scale}") is True
    ]


def _scale_diagnostic_rows(
    calibration: ScaleCalibrationProvenance,
) -> list[dict[str, Any]]:
    return [
        {
            "scale": scale,
            "shift": getattr(calibration, f"shift_{scale}"),
            "threshold": getattr(calibration, f"threshold_{scale}"),
            "candidate": getattr(calibration, f"candidate_{scale}"),
            "calibrated_evidence": getattr(
                calibration, f"calibrated_evidence_{scale}"
            ),
        }
        for scale in calibration.available_scales
    ]


def _per_scale_summary(
    calibrations: Mapping[int, ScaleCalibrationProvenance],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for scale in (1, 2, 3):
        available = [
            item
            for item in calibrations.values()
            if scale in item.available_scales
        ]
        scope_counts: dict[str, int] = {}
        method_counts: dict[str, int] = {}
        for item in available:
            threshold = getattr(item, f"threshold_provenance_{scale}")
            if threshold is None:
                raise AssertionError("Available scale lacks threshold provenance")
            scope_counts[threshold.threshold_scope_kind] = (
                scope_counts.get(threshold.threshold_scope_kind, 0) + 1
            )
            method_counts[threshold.method] = method_counts.get(threshold.method, 0) + 1
        result[str(scale)] = {
            "available_boundary_count": len(available),
            "candidate_count": sum(
                getattr(item, f"candidate_{scale}") is True for item in available
            ),
            "threshold_scope_distribution": dict(sorted(scope_counts.items())),
            "threshold_method_distribution": dict(sorted(method_counts.items())),
        }
    return result


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _unique_dicts(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _unique_lists(values: Iterable[list[str]]) -> list[list[str]]:
    result: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for value in values:
        key = tuple(value)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for row in rows
    )
    path.write_text(payload, encoding="utf-8", newline="\n")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m amsc.v5_research")
    parser.add_argument("--units", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--v3-output", required=True, type=Path)
    parser.add_argument("--v3-config", required=True, type=Path)
    parser.add_argument("--v4-config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = run_scale_calibration_research(
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
                "output": str(args.output),
                "b0_byte_identical": summary["b0_byte_identical"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
