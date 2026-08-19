from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .io import load_jsonl_units
from .models import RawDocumentUnit, UnitType


_FRAGMENT_SUFFIX = re.compile(r"#(?:heading-)?fragment-\d+$")


class GoldBoundaryAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    annotation_id: str = Field(min_length=1)
    left_unit_id: str = Field(min_length=1)
    right_unit_id: str = Field(min_length=1)
    intervening_heading_unit_ids: list[str] = Field(default_factory=list)
    confidence: Literal["high", "review"]
    topic_before: str = ""
    topic_after: str = ""
    rationale: str = ""
    pages: list[int] = Field(default_factory=list)


class EvaluationRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region_id: str = Field(min_length=1)
    start_unit_id: str = Field(min_length=1)
    end_unit_id: str = Field(min_length=1)
    section_path_hint: list[str] = Field(default_factory=list)
    pages: list[int] = Field(default_factory=list)
    coverage_tags: list[str] = Field(default_factory=list)
    selection_rationale: str = ""
    gold_boundaries: list[GoldBoundaryAnnotation] = Field(default_factory=list)


class CheckpointAnnotations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    document_id: str = Field(min_length=1)
    source_units_file: str = Field(min_length=1)
    source_units_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tolerance_content_units: Literal[1] = 1
    annotation_status: Literal[
        "awaiting_manual_annotation", "in_review", "adjudicated"
    ] = "awaiting_manual_annotation"
    regions: list[EvaluationRegion]

    @model_validator(mode="after")
    def validate_ids(self) -> "CheckpointAnnotations":
        region_ids = [region.region_id for region in self.regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("region_id values must be unique")
        annotation_ids = [
            boundary.annotation_id
            for region in self.regions
            for boundary in region.gold_boundaries
        ]
        if len(annotation_ids) != len(set(annotation_ids)):
            raise ValueError("annotation_id values must be unique")
        return self


@dataclass(frozen=True)
class MatchResult:
    pairs: tuple[tuple[int, int], ...]
    total_distance: int

    @property
    def count(self) -> int:
        return len(self.pairs)


@dataclass(frozen=True)
class PredictionExtraction:
    gap_indices: frozenset[int]
    forced_same_source_chunk_boundaries: int
    forced_split_fragment_count: int


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_annotations(path: str | Path) -> CheckpointAnnotations:
    return CheckpointAnnotations.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_jsonl_objects(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except Exception as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"JSONL line {line_number} must be an object")
            rows.append(payload)
    return rows


def match_boundaries(
    predicted_gap_indices: Sequence[int],
    gold_gap_indices: Sequence[int],
    *,
    tolerance: int,
) -> MatchResult:
    predictions = tuple(sorted(set(predicted_gap_indices)))
    gold = tuple(sorted(set(gold_gap_indices)))
    memo: dict[tuple[int, int], MatchResult] = {}

    def solve(pred_index: int, gold_index: int) -> MatchResult:
        key = (pred_index, gold_index)
        if key in memo:
            return memo[key]
        if pred_index >= len(predictions) or gold_index >= len(gold):
            result = MatchResult((), 0)
            memo[key] = result
            return result

        choices = [
            solve(pred_index + 1, gold_index),
            solve(pred_index, gold_index + 1),
        ]
        distance = abs(predictions[pred_index] - gold[gold_index])
        if distance <= tolerance:
            tail = solve(pred_index + 1, gold_index + 1)
            choices.append(
                MatchResult(
                    pairs=(
                        (predictions[pred_index], gold[gold_index]),
                        *tail.pairs,
                    ),
                    total_distance=distance + tail.total_distance,
                )
            )
        result = min(choices, key=_match_sort_key)
        memo[key] = result
        return result

    return solve(0, 0)


def _match_sort_key(result: MatchResult) -> tuple[Any, ...]:
    prediction_signature = tuple(pair[0] for pair in result.pairs)
    gold_signature = tuple(pair[1] for pair in result.pairs)
    return (
        -result.count,
        result.total_distance,
        prediction_signature,
        gold_signature,
    )


def validate_annotations(
    annotations: CheckpointAnnotations,
    units: Sequence[RawDocumentUnit],
    *,
    units_sha256: str,
) -> None:
    if not units:
        raise ValueError("Evaluation requires at least one canonical unit")
    if annotations.document_id != units[0].document_id:
        raise ValueError("Annotation document_id does not match canonical input")
    if annotations.source_units_sha256 != units_sha256:
        raise ValueError("Annotation source_units_sha256 does not match input")

    raw_by_id = {unit.unit_id: unit for unit in units}
    content = [unit for unit in units if unit.type != UnitType.HEADING]
    content_index = {unit.unit_id: index for index, unit in enumerate(content)}
    occupied: list[tuple[int, int, str]] = []

    for region in annotations.regions:
        if region.start_unit_id not in content_index:
            raise ValueError(
                f"Region {region.region_id} start_unit_id is not a content unit"
            )
        if region.end_unit_id not in content_index:
            raise ValueError(
                f"Region {region.region_id} end_unit_id is not a content unit"
            )
        start = content_index[region.start_unit_id]
        end = content_index[region.end_unit_id]
        if end <= start:
            raise ValueError(
                f"Region {region.region_id} must contain at least one content gap"
            )
        for other_start, other_end, other_id in occupied:
            if max(start, other_start) <= min(end, other_end):
                raise ValueError(
                    f"Evaluation regions overlap: {other_id} and {region.region_id}"
                )
        occupied.append((start, end, region.region_id))

        for boundary in region.gold_boundaries:
            if boundary.left_unit_id not in content_index:
                raise ValueError(
                    f"Gold {boundary.annotation_id} left_unit_id is not content"
                )
            if boundary.right_unit_id not in content_index:
                raise ValueError(
                    f"Gold {boundary.annotation_id} right_unit_id is not content"
                )
            left = content_index[boundary.left_unit_id]
            right = content_index[boundary.right_unit_id]
            if right != left + 1:
                raise ValueError(
                    f"Gold {boundary.annotation_id} must reference adjacent content"
                )
            if not start <= left < end:
                raise ValueError(
                    f"Gold {boundary.annotation_id} falls outside its region"
                )
            left_order = raw_by_id[boundary.left_unit_id].order
            right_order = raw_by_id[boundary.right_unit_id].order
            actual_headings = {
                unit.unit_id
                for unit in units
                if unit.type == UnitType.HEADING
                and left_order < unit.order < right_order
            }
            declared = set(boundary.intervening_heading_unit_ids)
            if not declared <= actual_headings:
                raise ValueError(
                    f"Gold {boundary.annotation_id} declares a non-intervening heading"
                )


def extract_predictions(
    chunks: Sequence[dict[str, Any]],
    units: Sequence[RawDocumentUnit],
) -> PredictionExtraction:
    raw_by_id = {unit.unit_id: unit for unit in units}
    content = [unit for unit in units if unit.type != UnitType.HEADING]
    content_index = {unit.unit_id: index for index, unit in enumerate(content)}
    chunk_sources: list[list[str]] = []
    fragment_ids: set[str] = set()

    for chunk in chunks:
        sources: list[str] = []
        for prepared_id in chunk.get("content_unit_ids", []):
            if "#fragment-" in prepared_id or "#heading-fragment-" in prepared_id:
                fragment_ids.add(prepared_id)
            source_id = _FRAGMENT_SUFFIX.sub("", prepared_id)
            raw = raw_by_id.get(source_id)
            if raw is None or raw.type == UnitType.HEADING:
                continue
            if not sources or sources[-1] != source_id:
                sources.append(source_id)
        chunk_sources.append(sources)

    predictions: set[int] = set()
    forced_same_source = 0
    for boundary_index in range(max(0, len(chunk_sources) - 1)):
        left_source = _last_source(chunk_sources, boundary_index)
        right_source = _first_source(chunk_sources, boundary_index + 1)
        if left_source is None or right_source is None:
            continue
        if left_source == right_source:
            forced_same_source += 1
            continue
        left_index = content_index[left_source]
        right_index = content_index[right_source]
        if right_index != left_index + 1:
            raise ValueError(
                "Chunk boundary does not align with adjacent raw content units: "
                f"{left_source} -> {right_source}"
            )
        predictions.add(left_index)

    return PredictionExtraction(
        gap_indices=frozenset(predictions),
        forced_same_source_chunk_boundaries=forced_same_source,
        forced_split_fragment_count=len(fragment_ids),
    )


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


def evaluate_checkpoint(
    *,
    units: Sequence[RawDocumentUnit],
    annotations: CheckpointAnnotations,
    chunks: Sequence[dict[str, Any]],
    boundaries: Sequence[dict[str, Any]],
    resolved_config: dict[str, Any],
    units_sha256: str,
) -> dict[str, Any]:
    validate_annotations(annotations, units, units_sha256=units_sha256)
    content = [unit for unit in units if unit.type != UnitType.HEADING]
    content_index = {unit.unit_id: index for index, unit in enumerate(content)}
    predictions = extract_predictions(chunks, units)

    primary = _evaluate_tolerance(
        annotations,
        content_index,
        predictions.gap_indices,
        tolerance=annotations.tolerance_content_units,
    )
    exact = _evaluate_tolerance(
        annotations,
        content_index,
        predictions.gap_indices,
        tolerance=0,
    )
    chunk_metrics = _chunk_metrics(
        chunks,
        boundaries,
        resolved_config,
        predictions,
    )
    algorithm_version = (
        chunks[0].get("algorithm_version") if chunks else "unknown"
    )
    result = {
        "schema_version": "1.0",
        "document_id": annotations.document_id,
        "source_units_sha256": units_sha256,
        "algorithm_version": algorithm_version,
        "annotation_status": annotations.annotation_status,
        "boundary_metrics": {
            "primary_plus_minus_one": primary,
            "secondary_exact": exact,
        },
        "chunk_metrics": chunk_metrics,
    }
    ablation_id = chunks[0].get("ablation_id") if chunks else None
    if ablation_id is not None:
        result["ablation_id"] = ablation_id
    return result


def _evaluate_tolerance(
    annotations: CheckpointAnnotations,
    content_index: dict[str, int],
    predicted_gaps: frozenset[int],
    *,
    tolerance: int,
) -> dict[str, Any]:
    high_count = sum(
        boundary.confidence == "high"
        for region in annotations.regions
        for boundary in region.gold_boundaries
    )
    if high_count == 0:
        return {
            "status": "pending_gold_annotations",
            "tolerance_content_units": tolerance,
            "precision": None,
            "recall": None,
            "f1": None,
            "true_positive": None,
            "false_positive": None,
            "false_negative": None,
        }

    totals = Counter()
    region_rows = []
    for region in annotations.regions:
        start = content_index[region.start_unit_id]
        end = content_index[region.end_unit_id]
        region_predictions = sorted(gap for gap in predicted_gaps if start <= gap < end)
        high_gold = sorted(
            content_index[item.left_unit_id]
            for item in region.gold_boundaries
            if item.confidence == "high"
        )
        review_gold = sorted(
            content_index[item.left_unit_id]
            for item in region.gold_boundaries
            if item.confidence == "review"
        )
        matches = match_boundaries(
            region_predictions,
            high_gold,
            tolerance=tolerance,
        )
        matched_predictions = {pair[0] for pair in matches.pairs}
        ignored_review_predictions = {
            prediction
            for prediction in region_predictions
            if prediction not in matched_predictions
            and any(abs(prediction - review) <= tolerance for review in review_gold)
        }
        tp = matches.count
        fp = len(region_predictions) - tp - len(ignored_review_predictions)
        fn = len(high_gold) - tp
        totals.update(tp=tp, fp=fp, fn=fn)
        region_rows.append(
            {
                "region_id": region.region_id,
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "ignored_review_predictions": len(ignored_review_predictions),
                "total_match_distance": matches.total_distance,
            }
        )

    precision = _safe_ratio(totals["tp"], totals["tp"] + totals["fp"])
    recall = _safe_ratio(totals["tp"], totals["tp"] + totals["fn"])
    f1 = (
        0.0
        if precision + recall == 0.0
        else 2.0 * precision * recall / (precision + recall)
    )
    return {
        "status": "ok",
        "tolerance_content_units": tolerance,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positive": totals["tp"],
        "false_positive": totals["fp"],
        "false_negative": totals["fn"],
        "regions": region_rows,
    }


def _safe_ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _chunk_metrics(
    chunks: Sequence[dict[str, Any]],
    boundaries: Sequence[dict[str, Any]],
    resolved_config: dict[str, Any],
    predictions: PredictionExtraction,
) -> dict[str, Any]:
    token_counts = sorted(int(chunk["token_count"]) for chunk in chunks)
    min_tokens = int(resolved_config["tokens"]["min_tokens"])
    selected_reasons = [
        chunk.get("end_boundary", {}).get("reason")
        for chunk in chunks[:-1]
    ]
    selected_boundary_count = len(selected_reasons)
    size_count = selected_reasons.count("size_fallback")
    hard_count = selected_reasons.count("hard_limit_fallback")
    semantic_count = sum(
        reason in {"fixed_semantic_boundary", "adaptive_semantic_boundary"}
        for reason in selected_reasons
    )
    structural_assisted_count = sum(
        bool(
            chunk.get("end_boundary", {})
            .get("structural", {})
            .get("structural_assisted_candidate")
        )
        for chunk in chunks[:-1]
    )

    merge_decisions: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        for decision in chunk.get("merge_decisions") or []:
            proposal_id = decision.get("proposal_id")
            if proposal_id:
                merge_decisions[str(proposal_id)] = decision
    accepted_merges = sum(
        bool(decision.get("accepted"))
        for decision in merge_decisions.values()
    )
    rejected_merges = Counter(
        str(decision.get("rejection_reason"))
        for decision in merge_decisions.values()
        if not decision.get("accepted") and decision.get("rejection_reason")
    )
    removed_boundaries = sum(
        bool(decision.get("removed_boundary"))
        for decision in merge_decisions.values()
    )

    scope_distribution = Counter()
    scale_distribution = Counter()
    for boundary in boundaries:
        adaptive = boundary.get("adaptive_threshold")
        if isinstance(adaptive, dict):
            kind = adaptive.get("threshold_scope_kind")
            if kind:
                scope_distribution[str(kind)] += 1
        multi_scale = boundary.get("multi_scale")
        if isinstance(multi_scale, dict):
            scales = multi_scale.get("available_scales")
            if isinstance(scales, list):
                scale_distribution[",".join(str(value) for value in scales)] += 1

    return {
        "chunk_count": len(chunks),
        "token_count": {
            "min": token_counts[0] if token_counts else None,
            "median": _median(token_counts),
            "p90_nearest_rank": _nearest_rank(token_counts, 0.90),
            "max": token_counts[-1] if token_counts else None,
        },
        "below_min_token_chunk_count": sum(
            count < min_tokens for count in token_counts
        ),
        "below_min_token_chunk_ratio": _safe_ratio(
            sum(count < min_tokens for count in token_counts),
            len(token_counts),
        ),
        "selected_inter_chunk_boundary_count": selected_boundary_count,
        "size_fallback_count": size_count,
        "size_fallback_ratio": _safe_ratio(size_count, selected_boundary_count),
        "hard_fallback_count": hard_count,
        "hard_fallback_ratio": _safe_ratio(hard_count, selected_boundary_count),
        "fallback_count": size_count + hard_count,
        "fallback_ratio": _safe_ratio(
            size_count + hard_count, selected_boundary_count
        ),
        "semantic_boundary_count": semantic_count,
        "structural_assisted_boundary_count": structural_assisted_count,
        "merge_proposal_count": len(merge_decisions),
        "accepted_merge_count": accepted_merges,
        "rejected_merge_count": len(merge_decisions) - accepted_merges,
        "rejected_merges_by_reason": dict(sorted(rejected_merges.items())),
        "removed_boundary_count": removed_boundaries,
        "threshold_scope_distribution": dict(sorted(scope_distribution.items())),
        "available_scale_composition": dict(sorted(scale_distribution.items())),
        "forced_split_fragment_count": predictions.forced_split_fragment_count,
        "forced_same_source_chunk_boundary_count": (
            predictions.forced_same_source_chunk_boundaries
        ),
    }


def _median(values: Sequence[int]) -> float | None:
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return float(values[middle])
    return (values[middle - 1] + values[middle]) / 2.0


def _nearest_rank(values: Sequence[int], quantile: float) -> int | None:
    if not values:
        return None
    index = max(0, math.ceil(quantile * len(values)) - 1)
    return values[index]


def render_annotation_worksheet(
    units: Sequence[RawDocumentUnit],
    annotations: CheckpointAnnotations,
) -> str:
    validate_annotations(
        annotations,
        units,
        units_sha256=annotations.source_units_sha256,
    )
    content = [unit for unit in units if unit.type != UnitType.HEADING]
    content_index = {unit.unit_id: index for index, unit in enumerate(content)}
    raw_by_order = sorted(units, key=lambda unit: unit.order)
    lines = [
        "# KKB 2024 Checkpoint Boundary Annotation Worksheet",
        "",
        "Gold boundary otomatik üretilmemiştir. Her gap için yalnız manuel "
        "karar verin: HIGH, REVIEW veya NO BOUNDARY.",
        "",
        f"Canonical SHA256: `{annotations.source_units_sha256}`",
        "",
    ]
    for region in annotations.regions:
        start = content_index[region.start_unit_id]
        end = content_index[region.end_unit_id]
        lines.extend(
            [
                f"## {region.region_id}",
                "",
                f"Coverage: {', '.join(region.coverage_tags)}",
                "",
                region.selection_rationale,
                "",
            ]
        )
        for gap_number, left_index in enumerate(range(start, end), start=1):
            left = content[left_index]
            right = content[left_index + 1]
            intervening = [
                unit
                for unit in raw_by_order
                if unit.type == UnitType.HEADING
                and left.order < unit.order < right.order
            ]
            heading_text = (
                ", ".join(f"{unit.unit_id}: {unit.text}" for unit in intervening)
                if intervening
                else "none"
            )
            lines.extend(
                [
                    f"### {region.region_id}-gap-{gap_number:03d}",
                    "",
                    f"Pages: {left.source.page} -> {right.source.page}",
                    "",
                    f"Intervening headings: {heading_text}",
                    "",
                    f"[LEFT {left.type.value.upper()} {left.unit_id}]",
                    "",
                    left.text,
                    "",
                    "----- POSSIBLE BOUNDARY -----",
                    "",
                    f"[RIGHT {right.type.value.upper()} {right.unit_id}]",
                    "",
                    right.text,
                    "",
                    "Decision: [ ] HIGH  [ ] REVIEW  [ ] NO BOUNDARY",
                    "",
                    "Topic before:",
                    "",
                    "Topic after:",
                    "",
                    "Rationale:",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m amsc.evaluation")
    commands = parser.add_subparsers(dest="command", required=True)

    worksheet = commands.add_parser("worksheet")
    worksheet.add_argument("--units", required=True, type=Path)
    worksheet.add_argument("--annotations", required=True, type=Path)
    worksheet.add_argument("--output", required=True, type=Path)

    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--units", required=True, type=Path)
    evaluate.add_argument("--annotations", required=True, type=Path)
    evaluate.add_argument("--chunks", required=True, type=Path)
    evaluate.add_argument("--boundaries", required=True, type=Path)
    evaluate.add_argument("--resolved-config", required=True, type=Path)
    evaluate.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    units = load_jsonl_units(args.units)
    annotations = load_annotations(args.annotations)
    units_hash = sha256_file(args.units)
    if args.command == "worksheet":
        if annotations.source_units_sha256 != units_hash:
            raise ValueError("Annotation SHA does not match worksheet input")
        payload = render_annotation_worksheet(units, annotations)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8", newline="\n")
        print(json.dumps({"status": "ok", "output": str(args.output)}))
        return 0

    result = evaluate_checkpoint(
        units=units,
        annotations=annotations,
        chunks=load_jsonl_objects(args.chunks),
        boundaries=load_jsonl_objects(args.boundaries),
        resolved_config=json.loads(args.resolved_config.read_text(encoding="utf-8")),
        units_sha256=units_hash,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"status": "ok", "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
