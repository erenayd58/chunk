from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any, Sequence

from .evaluation import (
    CheckpointAnnotations,
    EvaluationRegion,
    evaluate_checkpoint,
    extract_predictions,
    load_annotations,
    load_jsonl_objects,
    match_boundaries,
    sha256_file,
    validate_annotations,
)
from .io import load_jsonl_units
from .models import RawDocumentUnit, UnitType


_FRAGMENT_SUFFIX = re.compile(r"#(?:heading-)?fragment-\d+$")
_SEMANTIC_REASONS = {
    "adaptive_semantic_boundary",
    "fixed_semantic_boundary",
}


@dataclass(frozen=True)
class DiagnosticRun:
    run_id: str
    chunks: tuple[dict[str, Any], ...]
    boundaries: tuple[dict[str, Any], ...]
    resolved_config: dict[str, Any]
    authoritative_metrics: dict[str, Any]


@dataclass(frozen=True)
class RunDiagnostics:
    run_id: str
    prediction_rows: tuple[dict[str, Any], ...]
    gold_rows: tuple[dict[str, Any], ...]
    merge_rows: tuple[dict[str, Any], ...]
    summary: dict[str, Any]


def analyze_run(
    *,
    run: DiagnosticRun,
    units: Sequence[RawDocumentUnit],
    annotations: CheckpointAnnotations,
    units_sha256: str,
) -> RunDiagnostics:
    """Build diagnostics without changing the authoritative metric path."""

    validate_annotations(annotations, units, units_sha256=units_sha256)
    recomputed = evaluate_checkpoint(
        units=units,
        annotations=annotations,
        chunks=run.chunks,
        boundaries=run.boundaries,
        resolved_config=run.resolved_config,
        units_sha256=units_sha256,
    )
    if recomputed != run.authoritative_metrics:
        raise ValueError(
            f"Authoritative metrics changed for {run.run_id}; "
            "failure analysis aborted"
        )

    content = [unit for unit in units if unit.type != UnitType.HEADING]
    content_index = {unit.unit_id: index for index, unit in enumerate(content)}
    raw_by_id = {unit.unit_id: unit for unit in units}
    prediction_details = _prediction_details(run.chunks, units)
    authoritative_predictions = extract_predictions(run.chunks, units)
    if frozenset(prediction_details) != authoritative_predictions.gap_indices:
        raise AssertionError("Diagnostic predictions diverged from evaluator")
    boundary_by_gap = _boundary_rows_by_raw_gap(
        run.boundaries, content_index
    )

    prediction_rows: list[dict[str, Any]] = []
    gold_rows: list[dict[str, Any]] = []
    tp_groups = Counter()
    fp_reasons = Counter()
    ignored_review_count = 0
    matched_primary_count = 0
    matched_exact_count = 0

    proximity = review_high_proximity(annotations, content_index)
    proximity_by_high: dict[str, list[dict[str, Any]]] = {}
    for item in proximity:
        proximity_by_high.setdefault(
            str(item["high_annotation_id"]), []
        ).append(item)

    for region in annotations.regions:
        start = content_index[region.start_unit_id]
        end = content_index[region.end_unit_id]
        region_predictions = sorted(
            gap for gap in prediction_details if start <= gap < end
        )
        high_annotations = sorted(
            (
                (content_index[item.left_unit_id], item)
                for item in region.gold_boundaries
                if item.confidence == "high"
            ),
            key=lambda pair: (pair[0], pair[1].annotation_id),
        )
        review_annotations = sorted(
            (
                (content_index[item.left_unit_id], item)
                for item in region.gold_boundaries
                if item.confidence == "review"
            ),
            key=lambda pair: (pair[0], pair[1].annotation_id),
        )
        high_by_gap = {gap: item for gap, item in high_annotations}

        primary = match_boundaries(
            region_predictions,
            [gap for gap, _ in high_annotations],
            tolerance=annotations.tolerance_content_units,
        )
        exact = match_boundaries(
            region_predictions,
            [gap for gap, _ in high_annotations],
            tolerance=0,
        )
        primary_pred_to_gold = dict(primary.pairs)
        primary_gold_to_pred = {
            gold: prediction for prediction, gold in primary.pairs
        }
        exact_gold_to_pred = {
            gold: prediction for prediction, gold in exact.pairs
        }
        matched_primary_count += primary.count
        matched_exact_count += exact.count

        for gap in region_predictions:
            detail = prediction_details[gap]
            if gap in primary_pred_to_gold:
                gold_gap = primary_pred_to_gold[gap]
                gold = high_by_gap[gold_gap]
                classification = "TP"
                matched_annotation_id = gold.annotation_id
                match_distance = abs(gap - gold_gap)
                tp_groups[_tp_group(detail["selected_reason"])] += 1
            else:
                review_match = _nearest_review(
                    gap,
                    review_annotations,
                    tolerance=annotations.tolerance_content_units,
                )
                if review_match is not None:
                    gold_gap, gold = review_match
                    classification = "IGNORED_REVIEW"
                    matched_annotation_id = gold.annotation_id
                    match_distance = abs(gap - gold_gap)
                    ignored_review_count += 1
                else:
                    gold_gap = None
                    classification = "FP"
                    matched_annotation_id = None
                    match_distance = None
                    fp_reasons[str(detail["selected_reason"])] += 1

            prediction_rows.append(
                {
                    "algorithm_id": run.run_id,
                    "region_id": region.region_id,
                    "predicted_gap_index": gap,
                    "left_raw_unit_id": content[gap].unit_id,
                    "right_raw_unit_id": content[gap + 1].unit_id,
                    "classification": classification,
                    "matched_gold_annotation_id": matched_annotation_id,
                    "matched_gold_gap_index": gold_gap,
                    "match_distance": match_distance,
                    **_prediction_provenance(detail["end_boundary"]),
                }
            )

        for gold_gap, gold in high_annotations:
            if gold_gap in exact_gold_to_pred:
                status = "MATCHED_EXACT"
                matched_prediction = exact_gold_to_pred[gold_gap]
            elif gold_gap in primary_gold_to_pred:
                status = "MATCHED_PLUS_MINUS_ONE"
                matched_prediction = primary_gold_to_pred[gold_gap]
            else:
                status = "MISSED"
                matched_prediction = None
            boundary = boundary_by_gap.get(gold_gap)
            features = _semantic_features(boundary)
            suppression = _multi_scale_suppression(features)
            prediction_reason = (
                prediction_details[matched_prediction]["selected_reason"]
                if matched_prediction is not None
                else None
            )
            gold_rows.append(
                {
                    "algorithm_id": run.run_id,
                    "annotation_id": gold.annotation_id,
                    "region_id": region.region_id,
                    "left_unit_id": gold.left_unit_id,
                    "right_unit_id": gold.right_unit_id,
                    "gold_gap_index": gold_gap,
                    "status": status,
                    "matched_prediction_gap": matched_prediction,
                    "match_distance": (
                        abs(matched_prediction - gold_gap)
                        if matched_prediction is not None
                        else None
                    ),
                    "prediction_selected_reason": prediction_reason,
                    "intervening_heading": bool(
                        gold.intervening_heading_unit_ids
                    ),
                    "intervening_heading_unit_ids": list(
                        gold.intervening_heading_unit_ids
                    ),
                    "parser_section_transition": (
                        raw_by_id[gold.left_unit_id].section_path
                        != raw_by_id[gold.right_unit_id].section_path
                    ),
                    "review_proximity": proximity_by_high.get(
                        gold.annotation_id, []
                    ),
                    "multi_scale_suppression": suppression,
                    **_gold_semantic_features(features),
                }
            )

    high_total = sum(
        item.confidence == "high"
        for region in annotations.regions
        for item in region.gold_boundaries
    )
    missed_rows = [row for row in gold_rows if row["status"] == "MISSED"]
    summary = {
        "algorithm_id": run.run_id,
        "authoritative_metrics_verified": True,
        "high_gold_total": high_total,
        "matched_plus_minus_one": matched_primary_count,
        "matched_exact": matched_exact_count,
        "missed": high_total - matched_primary_count,
        "tp_by_reason": {
            key: tp_groups.get(key, 0)
            for key in (
                "semantic_tp",
                "size_fallback_tp",
                "hard_fallback_tp",
                "other_tp",
            )
        },
        "fp_by_reason": dict(sorted(fp_reasons.items())),
        "ignored_review_predictions": ignored_review_count,
        "multi_scale_suppression_high_fn": sum(
            bool(row["multi_scale_suppression"]) for row in missed_rows
        ),
        "authoritative_exact_f1": run.authoritative_metrics[
            "boundary_metrics"
        ]["secondary_exact"]["f1"],
        "authoritative_plus_minus_one_f1": run.authoritative_metrics[
            "boundary_metrics"
        ]["primary_plus_minus_one"]["f1"],
    }
    merge_rows = _merge_analysis(run)
    return RunDiagnostics(
        run_id=run.run_id,
        prediction_rows=tuple(prediction_rows),
        gold_rows=tuple(gold_rows),
        merge_rows=tuple(merge_rows),
        summary=summary,
    )


def review_high_proximity(
    annotations: CheckpointAnnotations,
    content_index: dict[str, int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for region in annotations.regions:
        high = [
            item
            for item in region.gold_boundaries
            if item.confidence == "high"
        ]
        review = [
            item
            for item in region.gold_boundaries
            if item.confidence == "review"
        ]
        for high_item in high:
            high_gap = content_index[high_item.left_unit_id]
            for review_item in review:
                review_gap = content_index[review_item.left_unit_id]
                distance = abs(high_gap - review_gap)
                if distance <= 1:
                    rows.append(
                        {
                            "region_id": region.region_id,
                            "high_annotation_id": high_item.annotation_id,
                            "high_gap_index": high_gap,
                            "review_annotation_id": review_item.annotation_id,
                            "review_gap_index": review_gap,
                            "distance": distance,
                        }
                    )
    return sorted(
        rows,
        key=lambda row: (
            row["region_id"],
            row["high_gap_index"],
            row["review_gap_index"],
            row["high_annotation_id"],
            row["review_annotation_id"],
        ),
    )


def write_failure_analysis(
    *,
    output_dir: str | Path,
    diagnostics: Sequence[RunDiagnostics],
    annotations: CheckpointAnnotations,
    units: Sequence[RawDocumentUnit],
) -> None:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    for diagnostic in diagnostics:
        _write_jsonl(
            target / f"{diagnostic.run_id}-predictions.jsonl",
            diagnostic.prediction_rows,
        )
    gold_rows = [row for item in diagnostics for row in item.gold_rows]
    merge_rows = [row for item in diagnostics for row in item.merge_rows]
    _write_jsonl(target / "gold-boundary-analysis.jsonl", gold_rows)
    _write_jsonl(target / "merge-analysis.jsonl", merge_rows)
    content = [unit for unit in units if unit.type != UnitType.HEADING]
    proximity = review_high_proximity(
        annotations,
        {unit.unit_id: index for index, unit in enumerate(content)},
    )
    markdown = render_failure_analysis_markdown(diagnostics, proximity)
    (target / "failure-analysis.md").write_text(
        markdown, encoding="utf-8", newline="\n"
    )


def render_failure_analysis_markdown(
    diagnostics: Sequence[RunDiagnostics],
    proximity: Sequence[dict[str, Any]],
) -> str:
    lines = [
        "# KKB 2024 Prediction-Level Failure Analysis",
        "",
        "Authoritative exact/±1 metrics are read-only invariants. Diagnostics do not "
        "alter matching, REVIEW-ignore, region filtering, or same-source fragment "
        "exclusion.",
        "",
        "## Evaluation attribution",
        "",
        "| Run | HIGH | Matched ±1 | Exact | Missed | Semantic TP | Size TP | Hard TP | Other TP | Ignored REVIEW |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for diagnostic in diagnostics:
        summary = diagnostic.summary
        tp = summary["tp_by_reason"]
        lines.append(
            f"| {diagnostic.run_id} | {summary['high_gold_total']} | "
            f"{summary['matched_plus_minus_one']} | {summary['matched_exact']} | "
            f"{summary['missed']} | {tp['semantic_tp']} | "
            f"{tp['size_fallback_tp']} | {tp['hard_fallback_tp']} | "
            f"{tp['other_tp']} | {summary['ignored_review_predictions']} |"
        )
    lines.extend(["", "### FP by selected reason", ""])
    for diagnostic in diagnostics:
        reasons = diagnostic.summary["fp_by_reason"]
        rendered = ", ".join(
            f"`{key}`={value}" for key, value in reasons.items()
        ) or "none"
        lines.append(f"- {diagnostic.run_id}: {rendered}")

    lines.extend(
        [
            "",
            "## Missed HIGH boundaries",
            "",
            "| Run | Annotation | Region | shift 1/2/3 | Combined | Threshold | Heading | Section transition | Suppression |",
            "|---|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for diagnostic in diagnostics:
        for row in diagnostic.gold_rows:
            if row["status"] != "MISSED":
                continue
            shifts = "/".join(
                _format_float(row.get(f"shift_{scale}"))
                for scale in (1, 2, 3)
            )
            lines.append(
                f"| {diagnostic.run_id} | {row['annotation_id']} | "
                f"{row['region_id']} | {shifts} | "
                f"{_format_float(row['semantic_shift'])} | "
                f"{_format_float(row['threshold'])} | "
                f"{str(row['intervening_heading']).lower()} | "
                f"{str(row['parser_section_transition']).lower()} | "
                f"{str(row['multi_scale_suppression']).lower()} |"
            )
    lines.extend(["", "### Multi-scale suppression", ""])
    for diagnostic in diagnostics:
        lines.append(
            f"- {diagnostic.run_id}: "
            f"{diagnostic.summary['multi_scale_suppression_high_fn']} HIGH FN"
        )

    lines.extend(["", "## Accepted merge diagnostics", ""])
    accepted = [
        row
        for diagnostic in diagnostics
        for row in diagnostic.merge_rows
        if row["record_type"] == "accepted_merge"
    ]
    if accepted:
        lines.extend(
            [
                "| Run | Boundary | Original reason | Shift | Threshold | Strength | Pair shift | Margin | Structure compatible |",
                "|---|---:|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in accepted:
            lines.append(
                f"| {row['algorithm_id']} | {row['removed_boundary_index']} | "
                f"{row['original_reason']} | "
                f"{_format_float(row['original_semantic_shift'])} | "
                f"{_format_float(row['original_threshold'])} | "
                f"{_format_float(row['original_strength'])} | "
                f"{_format_float(row['pooled_pair_shift'])} | "
                f"{_format_float(row['cohesion_margin'])} | "
                f"{row['structure_compatibility']} |"
            )
    else:
        lines.append("No accepted merges.")

    distributions = [
        row
        for diagnostic in diagnostics
        for row in diagnostic.merge_rows
        if row["record_type"] == "semantic_candidate_strength_distribution"
    ]
    lines.extend(["", "## Original boundary strength distribution", ""])
    if distributions:
        lines.extend(
            [
                "| Run | N | Min | Median | P75 | P90 | P95 | Max | Guard | At/above guard |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in distributions:
            lines.append(
                f"| {row['algorithm_id']} | {row['sample_count']} | "
                f"{_format_float(row['min'])} | {_format_float(row['median'])} | "
                f"{_format_float(row['p75'])} | {_format_float(row['p90'])} | "
                f"{_format_float(row['p95'])} | {_format_float(row['max'])} | "
                f"{_format_float(row['configured_high_confidence_threshold'])} | "
                f"{row['count_at_or_above_guard']} |"
            )

    lines.extend(["", "### Boundary 1327 case study", ""])
    case_rows = [
        row
        for row in accepted
        if row["removed_boundary_index"] == 1327
    ]
    if case_rows:
        for row in case_rows:
            lines.append(
                f"- {row['algorithm_id']}: original reason "
                f"`{row['original_reason']}`, original shift "
                f"{_format_float(row['original_semantic_shift'])}, threshold "
                f"{_format_float(row['original_threshold'])}, strength "
                f"{_format_float(row['original_strength'])}, pooled pair shift "
                f"{_format_float(row['pooled_pair_shift'])}, margin "
                f"{_format_float(row['cohesion_margin'])}, structure compatibility "
                f"`{row['structure_compatibility']}`."
            )
    else:
        lines.append("Boundary 1327 was not accepted by the analyzed runs.")

    lines.extend(["", "## HIGH/REVIEW proximity (distance <= 1)", ""])
    if proximity:
        lines.extend(
            [
                "| Region | HIGH | REVIEW | Gaps | Distance |",
                "|---|---|---|---|---:|",
            ]
        )
        for row in proximity:
            lines.append(
                f"| {row['region_id']} | {row['high_annotation_id']} | "
                f"{row['review_annotation_id']} | {row['high_gap_index']} / "
                f"{row['review_gap_index']} | {row['distance']} |"
            )
    else:
        lines.append("No HIGH/REVIEW pair is within one content-unit gap.")

    lines.extend(_render_failure_patterns(diagnostics))
    return "\n".join(lines).rstrip() + "\n"


def _render_failure_patterns(
    diagnostics: Sequence[RunDiagnostics],
) -> list[str]:
    focus = next(
        (item for item in diagnostics if item.run_id == "a4"),
        diagnostics[-1],
    )
    missed = [row for row in focus.gold_rows if row["status"] == "MISSED"]
    suppression = sum(bool(row["multi_scale_suppression"]) for row in missed)
    below_all = sum(
        row["threshold"] is not None
        and all(
            value is None or value <= row["threshold"]
            for value in (row["shift_1"], row["shift_2"], row["shift_3"])
        )
        for row in missed
    )
    semantic_candidate_not_selected = sum(
        row["semantic_shift"] is not None
        and row["threshold"] is not None
        and row["semantic_shift"] >= row["threshold"]
        for row in missed
    )
    heading_missed = sum(bool(row["intervening_heading"]) for row in missed)
    section_missed = sum(bool(row["parser_section_transition"]) for row in missed)
    fallback_fp = sum(
        value
        for reason, value in focus.summary["fp_by_reason"].items()
        if reason in {"size_fallback", "hard_limit_fallback"}
    )
    return [
        "",
        "## Five observed failure patterns (A4 focus)",
        "",
        f"1. Multi-scale suppression affects {suppression} of {len(missed)} HIGH FN.",
        f"2. All available individual scales are at/below threshold for {below_all} HIGH FN.",
        f"3. Combined shift is already an adaptive semantic candidate but the interval selector does not cut within ±1 for {semantic_candidate_not_selected} HIGH FN.",
        f"4. {heading_missed} HIGH FN have an intervening heading; {section_missed} have a parser section transition.",
        f"5. {fallback_fp} primary FP are produced by size/hard fallback boundaries rather than semantic boundaries.",
    ]


def _prediction_details(
    chunks: Sequence[dict[str, Any]],
    units: Sequence[RawDocumentUnit],
) -> dict[int, dict[str, Any]]:
    raw_by_id = {unit.unit_id: unit for unit in units}
    content = [unit for unit in units if unit.type != UnitType.HEADING]
    content_index = {unit.unit_id: index for index, unit in enumerate(content)}
    chunk_sources: list[list[str]] = []
    for chunk in chunks:
        sources: list[str] = []
        for prepared_id in chunk.get("content_unit_ids", []):
            source_id = _FRAGMENT_SUFFIX.sub("", str(prepared_id))
            raw = raw_by_id.get(source_id)
            if raw is None or raw.type == UnitType.HEADING:
                continue
            if not sources or sources[-1] != source_id:
                sources.append(source_id)
        chunk_sources.append(sources)

    details: dict[int, dict[str, Any]] = {}
    for index in range(max(0, len(chunk_sources) - 1)):
        left = _last_source(chunk_sources, index)
        right = _first_source(chunk_sources, index + 1)
        if left is None or right is None or left == right:
            continue
        left_index = content_index[left]
        if content_index[right] != left_index + 1:
            raise ValueError(
                f"Diagnostic chunk edge is not an adjacent raw gap: {left}->{right}"
            )
        candidate = {
            "selected_reason": chunks[index]
            .get("end_boundary", {})
            .get("reason"),
            "end_boundary": chunks[index].get("end_boundary", {}),
        }
        if left_index in details and details[left_index] != candidate:
            raise ValueError(f"Ambiguous diagnostic provenance for gap {left_index}")
        details[left_index] = candidate
    return details


def _boundary_rows_by_raw_gap(
    boundaries: Sequence[dict[str, Any]],
    content_index: dict[str, int],
) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for boundary in boundaries:
        left = _FRAGMENT_SUFFIX.sub("", str(boundary.get("left_unit_id", "")))
        right = _FRAGMENT_SUFFIX.sub("", str(boundary.get("right_unit_id", "")))
        if left == right or left not in content_index or right not in content_index:
            continue
        gap = content_index[left]
        if content_index[right] != gap + 1:
            continue
        previous = result.get(gap)
        if previous is not None and previous != boundary:
            raise ValueError(f"Multiple semantic evidence rows for raw gap {gap}")
        result[gap] = boundary
    return result


def _prediction_provenance(boundary: dict[str, Any]) -> dict[str, Any]:
    features = _semantic_features(boundary)
    return {
        "selected_reason": boundary.get("reason"),
        "semantic_shift": features["semantic_shift"],
        "shift_1": features["shift_1"],
        "shift_2": features["shift_2"],
        "shift_3": features["shift_3"],
        "available_scales": features["available_scales"],
        "adaptive_threshold": features["threshold"],
        "threshold_scope_kind": features["threshold_scope_kind"],
        "original_boundary_strength": features["original_boundary_strength"],
        "effective_boundary_strength": features["effective_boundary_strength"],
        "structural_evidence_types": features["structural_evidence_types"],
        "structural_assisted_candidate": features[
            "structural_assisted_candidate"
        ],
    }


def _semantic_features(boundary: dict[str, Any] | None) -> dict[str, Any]:
    if boundary is None:
        return {
            "semantic_shift": None,
            "shift_1": None,
            "shift_2": None,
            "shift_3": None,
            "available_scales": [],
            "threshold": None,
            "threshold_scope_kind": None,
            "original_boundary_strength": None,
            "effective_boundary_strength": None,
            "structural_evidence_types": [],
            "structural_assisted_candidate": None,
        }
    multi = boundary.get("multi_scale") or {}
    adaptive = boundary.get("adaptive_threshold") or {}
    structural = boundary.get("structural") or {}
    return {
        "semantic_shift": boundary.get("semantic_shift"),
        "shift_1": multi.get("shift_1"),
        "shift_2": multi.get("shift_2"),
        "shift_3": multi.get("shift_3"),
        "available_scales": list(multi.get("available_scales") or []),
        "threshold": adaptive.get("value"),
        "threshold_scope_kind": adaptive.get("threshold_scope_kind"),
        "original_boundary_strength": boundary.get(
            "original_boundary_strength"
        ),
        "effective_boundary_strength": boundary.get(
            "effective_boundary_strength"
        ),
        "structural_evidence_types": list(
            structural.get("evidence_types") or []
        ),
        "structural_assisted_candidate": structural.get(
            "structural_assisted_candidate"
        ),
    }


def _gold_semantic_features(features: dict[str, Any]) -> dict[str, Any]:
    return {
        "semantic_shift": features["semantic_shift"],
        "combined_semantic_shift": features["semantic_shift"],
        "shift_1": features["shift_1"],
        "shift_2": features["shift_2"],
        "shift_3": features["shift_3"],
        "available_scales": features["available_scales"],
        "threshold": features["threshold"],
        "threshold_scope_kind": features["threshold_scope_kind"],
        "original_boundary_strength": features["original_boundary_strength"],
        "effective_boundary_strength": features["effective_boundary_strength"],
        "structural_evidence_types": features["structural_evidence_types"],
        "structural_assisted_candidate": features[
            "structural_assisted_candidate"
        ],
    }


def _multi_scale_suppression(features: dict[str, Any]) -> bool:
    threshold = features["threshold"]
    combined = features["semantic_shift"]
    if threshold is None or combined is None or combined >= threshold:
        return False
    return any(
        value is not None and value > threshold
        for value in (
            features["shift_1"],
            features["shift_2"],
            features["shift_3"],
        )
    )


def _merge_analysis(run: DiagnosticRun) -> list[dict[str, Any]]:
    boundary_by_index = {
        int(row["boundary_index"]): row
        for row in run.boundaries
        if row.get("boundary_index") is not None
    }
    rows: list[dict[str, Any]] = []
    seen_proposals: set[str] = set()
    for chunk in run.chunks:
        accepted = chunk.get("accepted_merge")
        if not accepted:
            continue
        proposal_id = str(accepted["proposal_id"])
        if proposal_id in seen_proposals:
            continue
        seen_proposals.add(proposal_id)
        decision = next(
            (
                item
                for item in chunk.get("merge_decisions") or []
                if item.get("proposal_id") == proposal_id
                and item.get("accepted")
            ),
            None,
        )
        boundary_index = int(accepted["removed_boundary_index"])
        boundary = boundary_by_index.get(boundary_index, {})
        threshold = float(accepted["original_adaptive_threshold"])
        pair_shift = float(accepted["pair_shift"])
        rows.append(
            {
                "record_type": "accepted_merge",
                "algorithm_id": run.run_id,
                "proposal_id": proposal_id,
                "removed_boundary_index": boundary_index,
                "original_reason": (
                    decision.get("boundary_original_reason")
                    if decision
                    else None
                ),
                "original_semantic_shift": boundary.get("semantic_shift"),
                "original_threshold": threshold,
                "original_strength": accepted.get(
                    "original_boundary_strength"
                ),
                "pooled_pair_shift": pair_shift,
                "cohesion_margin": threshold - pair_shift,
                "structure_compatibility": (
                    decision.get("structural_compatibility")
                    if decision
                    else None
                ),
            }
        )

    strengths = sorted(
        float(row["original_boundary_strength"])
        for row in run.boundaries
        if row.get("semantic_candidate")
        and row.get("original_boundary_strength") is not None
    )
    merge_config = run.resolved_config.get("merge") or {}
    guard = merge_config.get("high_confidence_strength_threshold")
    if strengths and guard is not None:
        guard_value = float(guard)
        rows.append(
            {
                "record_type": "semantic_candidate_strength_distribution",
                "algorithm_id": run.run_id,
                "sample_count": len(strengths),
                "quantile_method": "linear_r7",
                "min": strengths[0],
                "median": _quantile(strengths, 0.50),
                "p75": _quantile(strengths, 0.75),
                "p90": _quantile(strengths, 0.90),
                "p95": _quantile(strengths, 0.95),
                "max": strengths[-1],
                "configured_high_confidence_threshold": guard_value,
                "count_at_or_above_guard": sum(
                    value >= guard_value for value in strengths
                ),
                "ratio_at_or_above_guard": sum(
                    value >= guard_value for value in strengths
                )
                / len(strengths),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            0 if row["record_type"] == "accepted_merge" else 1,
            row.get("removed_boundary_index", math.inf),
            row["algorithm_id"],
        ),
    )


def _nearest_review(
    prediction_gap: int,
    review_annotations: Sequence[tuple[int, Any]],
    *,
    tolerance: int,
) -> tuple[int, Any] | None:
    candidates = [
        (gap, item)
        for gap, item in review_annotations
        if abs(prediction_gap - gap) <= tolerance
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda pair: (
            abs(prediction_gap - pair[0]),
            pair[0],
            pair[1].annotation_id,
        ),
    )


def _tp_group(reason: Any) -> str:
    if reason in _SEMANTIC_REASONS:
        return "semantic_tp"
    if reason == "size_fallback":
        return "size_fallback_tp"
    if reason == "hard_limit_fallback":
        return "hard_fallback_tp"
    return "other_tp"


def _quantile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("Quantile requires at least one value")
    position = (len(values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(values[lower])
    fraction = position - lower
    return float(values[lower] + fraction * (values[upper] - values[lower]))


def _last_source(chunks: Sequence[Sequence[str]], end_index: int) -> str | None:
    for index in range(end_index, -1, -1):
        if chunks[index]:
            return chunks[index][-1]
    return None


def _first_source(chunks: Sequence[Sequence[str]], start_index: int) -> str | None:
    for index in range(start_index, len(chunks)):
        if chunks[index]:
            return chunks[index][0]
    return None


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for row in rows
    )
    path.write_text(payload, encoding="utf-8", newline="\n")


def _format_float(value: Any) -> str:
    return "-" if value is None else f"{float(value):.6f}"


def _parse_run(value: str) -> tuple[str, Path]:
    run_id, separator, raw_path = value.partition("=")
    if not separator or not run_id or not raw_path:
        raise argparse.ArgumentTypeError("--run must use ID=OUTPUT_DIR")
    return run_id, Path(raw_path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m amsc.failure_analysis")
    parser.add_argument("--units", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        type=_parse_run,
        metavar="ID=OUTPUT_DIR",
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    units = load_jsonl_units(args.units)
    annotations = load_annotations(args.annotations)
    units_hash = sha256_file(args.units)
    diagnostics: list[RunDiagnostics] = []
    seen_ids: set[str] = set()
    for run_id, directory in args.run:
        if run_id in seen_ids:
            raise ValueError(f"Duplicate diagnostic run ID: {run_id}")
        seen_ids.add(run_id)
        run = DiagnosticRun(
            run_id=run_id,
            chunks=tuple(load_jsonl_objects(directory / "chunks.jsonl")),
            boundaries=tuple(
                load_jsonl_objects(directory / "boundaries.jsonl")
            ),
            resolved_config=json.loads(
                (directory / "resolved-config.json").read_text(
                    encoding="utf-8"
                )
            ),
            authoritative_metrics=json.loads(
                (directory / "metrics.json").read_text(encoding="utf-8")
            ),
        )
        diagnostics.append(
            analyze_run(
                run=run,
                units=units,
                annotations=annotations,
                units_sha256=units_hash,
            )
        )
    write_failure_analysis(
        output_dir=args.output,
        diagnostics=diagnostics,
        annotations=annotations,
        units=units,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(args.output),
                "runs": [item.run_id for item in diagnostics],
                "authoritative_metrics_verified": True,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
