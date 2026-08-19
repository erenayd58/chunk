from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from amsc.evaluation import CheckpointAnnotations, evaluate_checkpoint
from amsc.failure_analysis import (
    DiagnosticRun,
    analyze_run,
    review_high_proximity,
    write_failure_analysis,
)
from amsc.models import RawDocumentUnit


UNITS_SHA = "a" * 64


def _fixture():
    units: list[RawDocumentUnit] = []
    for index in range(8):
        order = index + 1 if index < 5 else index + 2
        section = ["A"] if index <= 4 else ["B"]
        units.append(
            RawDocumentUnit.model_validate(
                {
                    "document_id": "doc",
                    "unit_id": f"p{index}",
                    "order": order,
                    "text": f"Paragraph {index}",
                    "type": "paragraph",
                    "section_path": section,
                    "source": {"page": 1, "block": order},
                }
            )
        )
    units.insert(
        5,
        RawDocumentUnit.model_validate(
            {
                "document_id": "doc",
                "unit_id": "h1",
                "order": 6,
                "text": "Section B",
                "type": "heading",
                "heading_level": 2,
                "section_path": ["B"],
                "source": {"page": 1, "block": 6},
            }
        ),
    )
    annotations = CheckpointAnnotations.model_validate(
        {
            "document_id": "doc",
            "source_units_file": "units.jsonl",
            "source_units_sha256": UNITS_SHA,
            "annotation_status": "in_review",
            "regions": [
                {
                    "region_id": "region",
                    "start_unit_id": "p0",
                    "end_unit_id": "p7",
                    "gold_boundaries": [
                        {
                            "annotation_id": "high-exact",
                            "left_unit_id": "p1",
                            "right_unit_id": "p2",
                            "confidence": "high",
                        },
                        {
                            "annotation_id": "high-missed",
                            "left_unit_id": "p4",
                            "right_unit_id": "p5",
                            "intervening_heading_unit_ids": ["h1"],
                            "confidence": "high",
                        },
                        {
                            "annotation_id": "review-near",
                            "left_unit_id": "p5",
                            "right_unit_id": "p6",
                            "confidence": "review",
                        },
                    ],
                }
            ],
        }
    )
    boundaries = [_boundary(index) for index in range(7)]
    boundaries[0]["semantic_candidate"] = True
    boundaries[0]["original_boundary_strength"] = 0.40
    boundaries[1]["semantic_candidate"] = True
    boundaries[1]["original_boundary_strength"] = 0.10
    boundaries[4].update(
        {
            "semantic_shift": 0.14,
            "semantic_candidate": False,
            "original_boundary_strength": 0.0,
            "multi_scale": {
                "shift_1": 0.20,
                "shift_2": 0.10,
                "shift_3": 0.12,
                "available_scales": [1, 2, 3],
            },
            "structural": {
                "evidence_types": [
                    "heading_presence",
                    "section_path_transition",
                ],
                "structural_assisted_candidate": False,
            },
        }
    )
    chunks = [
        _chunk(["p0", "p1"], boundaries[1], "adaptive_semantic_boundary"),
        _chunk(["p2"], boundaries[2], "hard_limit_fallback"),
        _chunk(["p3", "p4", "p5", "p6"], boundaries[6], "size_fallback"),
        _chunk(["p7"], {}, "document_end"),
    ]
    chunks[0]["merge_decisions"] = [
        {
            "proposal_id": "merge-case",
            "accepted": True,
            "boundary_original_reason": "size_fallback",
            "structural_compatibility": False,
            "removed_boundary": True,
        }
    ]
    chunks[0]["accepted_merge"] = {
        "proposal_id": "merge-case",
        "removed_boundary_index": 4,
        "original_adaptive_threshold": 0.15,
        "original_boundary_strength": 0.0,
        "pair_shift": 0.10,
    }
    config = {
        "tokens": {"min_tokens": 160},
        "merge": {"high_confidence_strength_threshold": 0.50},
    }
    metrics = evaluate_checkpoint(
        units=units,
        annotations=annotations,
        chunks=chunks,
        boundaries=boundaries,
        resolved_config=config,
        units_sha256=UNITS_SHA,
    )
    run = DiagnosticRun(
        run_id="a4",
        chunks=tuple(deepcopy(chunks)),
        boundaries=tuple(deepcopy(boundaries)),
        resolved_config=deepcopy(config),
        authoritative_metrics=deepcopy(metrics),
    )
    return units, annotations, run


def _boundary(index: int) -> dict[str, object]:
    return {
        "boundary_index": index,
        "left_unit_id": f"p{index}",
        "right_unit_id": f"p{index + 1}",
        "semantic_shift": 0.10,
        "semantic_candidate": False,
        "original_boundary_strength": 0.0,
        "effective_boundary_strength": 0.0,
        "adaptive_threshold": {
            "value": 0.15,
            "threshold_scope_kind": "document",
        },
        "multi_scale": {
            "shift_1": 0.10,
            "shift_2": 0.10,
            "shift_3": 0.10,
            "available_scales": [1, 2, 3],
        },
    }


def _chunk(
    content_ids: list[str], boundary: dict[str, object], reason: str
) -> dict[str, object]:
    end_boundary = deepcopy(boundary)
    end_boundary["reason"] = reason
    return {
        "algorithm_version": "amsc-v4",
        "ablation_id": "a4",
        "token_count": 100,
        "content_unit_ids": content_ids,
        "end_boundary": end_boundary,
    }


def test_prediction_diagnostics_preserve_primary_classification() -> None:
    units, annotations, run = _fixture()
    before = deepcopy(run.authoritative_metrics)

    diagnostic = analyze_run(
        run=run,
        units=units,
        annotations=annotations,
        units_sha256=UNITS_SHA,
    )

    assert run.authoritative_metrics == before
    by_gap = {row["predicted_gap_index"]: row for row in diagnostic.prediction_rows}
    assert by_gap[1]["classification"] == "TP"
    assert by_gap[1]["matched_gold_annotation_id"] == "high-exact"
    assert by_gap[2]["classification"] == "FP"
    assert by_gap[2]["selected_reason"] == "hard_limit_fallback"
    assert by_gap[6]["classification"] == "IGNORED_REVIEW"
    assert by_gap[6]["matched_gold_annotation_id"] == "review-near"
    assert diagnostic.summary["tp_by_reason"] == {
        "semantic_tp": 1,
        "size_fallback_tp": 0,
        "hard_fallback_tp": 0,
        "other_tp": 0,
    }
    assert diagnostic.summary["fp_by_reason"] == {
        "hard_limit_fallback": 1
    }
    assert diagnostic.summary["ignored_review_predictions"] == 1


def test_gold_diagnostics_report_miss_suppression_and_proximity() -> None:
    units, annotations, run = _fixture()
    diagnostic = analyze_run(
        run=run,
        units=units,
        annotations=annotations,
        units_sha256=UNITS_SHA,
    )
    gold = {row["annotation_id"]: row for row in diagnostic.gold_rows}

    assert gold["high-exact"]["status"] == "MATCHED_EXACT"
    missed = gold["high-missed"]
    assert missed["status"] == "MISSED"
    assert missed["multi_scale_suppression"] is True
    assert missed["intervening_heading"] is True
    assert missed["parser_section_transition"] is True
    assert missed["structural_evidence_types"] == [
        "heading_presence",
        "section_path_transition",
    ]
    assert diagnostic.summary["multi_scale_suppression_high_fn"] == 1

    content = [unit for unit in units if unit.type.value != "heading"]
    proximity = review_high_proximity(
        annotations,
        {unit.unit_id: index for index, unit in enumerate(content)},
    )
    assert proximity == [
        {
            "region_id": "region",
            "high_annotation_id": "high-missed",
            "high_gap_index": 4,
            "review_annotation_id": "review-near",
            "review_gap_index": 5,
            "distance": 1,
        }
    ]


def test_merge_and_strength_diagnostics_are_deterministic() -> None:
    units, annotations, run = _fixture()
    diagnostic = analyze_run(
        run=run,
        units=units,
        annotations=annotations,
        units_sha256=UNITS_SHA,
    )
    accepted = next(
        row
        for row in diagnostic.merge_rows
        if row["record_type"] == "accepted_merge"
    )
    distribution = next(
        row
        for row in diagnostic.merge_rows
        if row["record_type"] == "semantic_candidate_strength_distribution"
    )

    assert accepted["removed_boundary_index"] == 4
    assert accepted["original_reason"] == "size_fallback"
    assert accepted["cohesion_margin"] == pytest.approx(0.05)
    assert accepted["structure_compatibility"] is False
    assert distribution["sample_count"] == 2
    assert distribution["min"] == 0.10
    assert distribution["median"] == pytest.approx(0.25)
    assert distribution["p75"] == pytest.approx(0.325)
    assert distribution["max"] == 0.40
    assert distribution["count_at_or_above_guard"] == 0


def test_failure_analysis_writer_emits_requested_stable_files(
    tmp_path: Path,
) -> None:
    units, annotations, run = _fixture()
    diagnostic = analyze_run(
        run=run,
        units=units,
        annotations=annotations,
        units_sha256=UNITS_SHA,
    )
    first = tmp_path / "first"
    second = tmp_path / "second"
    for target in (first, second):
        write_failure_analysis(
            output_dir=target,
            diagnostics=[diagnostic],
            annotations=annotations,
            units=units,
        )

    expected = {
        "a4-predictions.jsonl",
        "gold-boundary-analysis.jsonl",
        "merge-analysis.jsonl",
        "failure-analysis.md",
    }
    assert {path.name for path in first.iterdir()} == expected
    for name in expected:
        assert (first / name).read_bytes() == (second / name).read_bytes()
