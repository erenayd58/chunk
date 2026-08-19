from __future__ import annotations

from amsc.evaluation import (
    CheckpointAnnotations,
    evaluate_checkpoint,
    extract_predictions,
    match_boundaries,
)
from amsc.models import RawDocumentUnit


def _unit(
    unit_id: str,
    order: int,
    unit_type: str = "paragraph",
    *,
    visual: bool = False,
) -> RawDocumentUnit:
    source = {"page": 1, "block": order}
    if visual:
        source["content_origin"] = "visual"
    return RawDocumentUnit.model_validate(
        {
            "document_id": "doc",
            "unit_id": unit_id,
            "order": order,
            "text": f"Text {unit_id}",
            "type": unit_type,
            "heading_level": 2 if unit_type == "heading" else None,
            "source": source,
        }
    )


def _annotations(
    *,
    gold: list[dict[str, object]] | None = None,
) -> CheckpointAnnotations:
    return CheckpointAnnotations.model_validate(
        {
            "schema_version": "1.0",
            "document_id": "doc",
            "source_units_file": "units.jsonl",
            "source_units_sha256": "a" * 64,
            "tolerance_content_units": 1,
            "annotation_status": "in_review",
            "regions": [
                {
                    "region_id": "r1",
                    "start_unit_id": "p1",
                    "end_unit_id": "t4",
                    "gold_boundaries": gold or [],
                }
            ],
        }
    )


def test_matching_maximizes_count_then_distance_then_earlier_prediction() -> None:
    result = match_boundaries([1, 3, 5], [2, 4], tolerance=1)

    assert result.count == 2
    assert result.total_distance == 2
    assert result.pairs == ((1, 2), (3, 4))


def test_visual_list_and_table_are_content_and_same_source_split_is_excluded() -> None:
    units = [
        _unit("p1", 1),
        _unit("h1", 2, "heading"),
        _unit("v2", 3, visual=True),
        _unit("l3", 4, "list"),
        _unit("t4", 5, "table"),
    ]
    chunks = [
        {"content_unit_ids": ["p1#fragment-1"]},
        {"content_unit_ids": ["p1#fragment-2"]},
        {"content_unit_ids": ["v2"]},
        {"content_unit_ids": ["l3"]},
        {"content_unit_ids": ["t4"]},
    ]

    result = extract_predictions(chunks, units)

    assert result.gap_indices == frozenset({0, 1, 2})
    assert result.forced_same_source_chunk_boundaries == 1
    assert result.forced_split_fragment_count == 2


def test_empty_gold_reports_pending_without_inventing_f1() -> None:
    units = [
        _unit("p1", 1),
        _unit("v2", 2, visual=True),
        _unit("l3", 3, "list"),
        _unit("t4", 4, "table"),
    ]
    chunks = [
        {
            "algorithm_version": "amsc-v3",
            "token_count": 100,
            "content_unit_ids": ["p1", "v2"],
            "end_boundary": {"reason": "size_fallback"},
        },
        {
            "algorithm_version": "amsc-v3",
            "token_count": 200,
            "content_unit_ids": ["l3", "t4"],
            "end_boundary": {"reason": "document_end"},
        },
    ]

    result = evaluate_checkpoint(
        units=units,
        annotations=_annotations(),
        chunks=chunks,
        boundaries=[],
        resolved_config={"tokens": {"min_tokens": 160}},
        units_sha256="a" * 64,
    )

    primary = result["boundary_metrics"]["primary_plus_minus_one"]
    exact = result["boundary_metrics"]["secondary_exact"]
    assert primary["status"] == exact["status"] == "pending_gold_annotations"
    assert primary["f1"] is exact["f1"] is None
    assert result["chunk_metrics"]["chunk_count"] == 2
    assert result["chunk_metrics"]["below_min_token_chunk_ratio"] == 0.5
    assert result["chunk_metrics"]["size_fallback_ratio"] == 1.0


def test_review_gold_and_region_edges_do_not_enter_primary_metrics() -> None:
    units = [
        _unit("p1", 1),
        _unit("v2", 2, visual=True),
        _unit("l3", 3, "list"),
        _unit("t4", 4, "table"),
    ]
    annotations = _annotations(
        gold=[
            {
                "annotation_id": "high-1",
                "left_unit_id": "p1",
                "right_unit_id": "v2",
                "confidence": "high",
            },
            {
                "annotation_id": "review-1",
                "left_unit_id": "l3",
                "right_unit_id": "t4",
                "confidence": "review",
            },
        ]
    )
    chunks = [
        {
            "algorithm_version": "amsc-v2",
            "token_count": 100,
            "content_unit_ids": ["p1"],
            "end_boundary": {"reason": "adaptive_semantic_boundary"},
        },
        {
            "algorithm_version": "amsc-v2",
            "token_count": 100,
            "content_unit_ids": ["v2", "l3"],
            "end_boundary": {"reason": "size_fallback"},
        },
        {
            "algorithm_version": "amsc-v2",
            "token_count": 100,
            "content_unit_ids": ["t4"],
            "end_boundary": {"reason": "document_end"},
        },
    ]

    result = evaluate_checkpoint(
        units=units,
        annotations=annotations,
        chunks=chunks,
        boundaries=[],
        resolved_config={"tokens": {"min_tokens": 160}},
        units_sha256="a" * 64,
    )

    exact = result["boundary_metrics"]["secondary_exact"]
    assert exact["true_positive"] == 1
    assert exact["false_positive"] == 0
    assert exact["false_negative"] == 0
    assert exact["precision"] == exact["recall"] == exact["f1"] == 1.0


def test_threshold_and_scale_distributions_are_annotation_independent() -> None:
    units = [_unit("p1", 1), _unit("v2", 2, visual=True), _unit("l3", 3, "list"), _unit("t4", 4, "table")]
    chunks = [
        {
            "algorithm_version": "amsc-v3",
            "token_count": 10,
            "content_unit_ids": ["p1", "v2", "l3", "t4"],
            "end_boundary": {"reason": "document_end"},
        }
    ]
    boundaries = [
        {
            "adaptive_threshold": {"threshold_scope_kind": "document"},
            "multi_scale": {"available_scales": [1, 2]},
        },
        {
            "adaptive_threshold": {"threshold_scope_kind": "section"},
            "multi_scale": {"available_scales": [1]},
        },
    ]

    result = evaluate_checkpoint(
        units=units,
        annotations=_annotations(),
        chunks=chunks,
        boundaries=boundaries,
        resolved_config={"tokens": {"min_tokens": 160}},
        units_sha256="a" * 64,
    )

    metrics = result["chunk_metrics"]
    assert metrics["threshold_scope_distribution"] == {
        "document": 1,
        "section": 1,
    }
    assert metrics["available_scale_composition"] == {"1": 1, "1,2": 1}


def test_v4_merge_and_selected_boundary_metrics_are_counted() -> None:
    units = [_unit("p1", 1), _unit("v2", 2, visual=True), _unit("t4", 3, "table")]
    chunks = [
        {
            "algorithm_version": "amsc-v4",
            "ablation_id": "a4",
            "token_count": 100,
            "content_unit_ids": ["p1", "v2"],
            "end_boundary": {
                "reason": "adaptive_semantic_boundary",
                "structural": {"structural_assisted_candidate": True},
            },
            "merge_decisions": [
                {
                    "proposal_id": "merge-1-left",
                    "accepted": True,
                    "removed_boundary": True,
                },
                {
                    "proposal_id": "merge-2-right",
                    "accepted": False,
                    "removed_boundary": False,
                    "rejection_reason": "semantic_cohesion_not_met",
                },
            ],
        },
        {
            "algorithm_version": "amsc-v4",
            "token_count": 200,
            "content_unit_ids": ["t4"],
            "end_boundary": {"reason": "document_end"},
        },
    ]

    result = evaluate_checkpoint(
        units=units,
        annotations=CheckpointAnnotations.model_validate(
            {
                "document_id": "doc",
                "source_units_file": "units.jsonl",
                "source_units_sha256": "a" * 64,
                "regions": [
                    {
                        "region_id": "r1",
                        "start_unit_id": "p1",
                        "end_unit_id": "t4",
                    }
                ],
            }
        ),
        chunks=chunks,
        boundaries=[],
        resolved_config={"tokens": {"min_tokens": 160}},
        units_sha256="a" * 64,
    )

    metrics = result["chunk_metrics"]
    assert metrics["semantic_boundary_count"] == 1
    assert metrics["structural_assisted_boundary_count"] == 1
    assert metrics["merge_proposal_count"] == 2
    assert metrics["accepted_merge_count"] == 1
    assert metrics["rejected_merges_by_reason"] == {
        "semantic_cohesion_not_met": 1
    }
    assert metrics["removed_boundary_count"] == 1
