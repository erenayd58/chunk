from __future__ import annotations

from pathlib import Path

import pytest

from amsc.config import (
    AdaptiveSemanticConfig,
    MultiScaleConfig,
    SelectionConfig,
    TokenLimitsConfig,
)
from amsc.models import (
    AdaptiveThresholdProvenance,
    BoundaryEvidence,
    ContentUnit,
    MultiScaleSemanticProvenance,
    SourceSpan,
    UnitType,
)
from amsc.scale_calibration import (
    PerScaleAdaptiveCalibrator,
    ScaleCalibratedIntervalBoundarySelector,
    ScaleCalibrationProvenance,
)
from amsc.selection import V2TailResolver
from amsc.units import RenderedTokenBudgeter
from amsc.v5_research import _copy_byte_identical_baseline
from conftest import WordTokenCounter


def _multi_scale_config() -> MultiScaleConfig:
    return MultiScaleConfig.model_validate(
        {
            "shift_1_weight": 0.35,
            "shift_2_weight": 0.26,
            "shift_3_weight": 0.39,
            "unit_weighting": "configured_token_counter_sqrt",
            "window_pooling": "weighted_mean_l2_normalized",
            "edge_policy": "full_symmetric_available_scales",
        }
    )


def _unit(index: int) -> ContentUnit:
    return ContentUnit(
        document_id="d",
        unit_id=f"u{index}",
        source_unit_id=f"u{index}",
        order=index,
        text=f"unit {index}",
        type=UnitType.PARAGRAPH,
        section_path=(),
        source=SourceSpan(page=1, block=index + 1),
    )


def _boundary(index: int, shifts: tuple[float, float, float]) -> BoundaryEvidence:
    weights = (0.35, 0.26, 0.39)
    combined = sum(weight * shift for weight, shift in zip(weights, shifts))
    return BoundaryEvidence(
        boundary_index=index,
        left_unit_id=f"u{index}",
        right_unit_id=f"u{index + 1}",
        cosine_similarity=1.0 - 2.0 * shifts[0],
        semantic_shift=combined,
        semantic_candidate=False,
        multi_scale=MultiScaleSemanticProvenance(
            shift_1=shifts[0],
            shift_2=shifts[1],
            shift_3=shifts[2],
            available_scales=[1, 2, 3],
            scale_count=3,
            effective_weight_1=weights[0],
            effective_weight_2=weights[1],
            effective_weight_3=weights[2],
            unit_weighting="configured_token_counter_sqrt",
            window_pooling="weighted_mean_l2_normalized",
            token_counter_id="test:words",
        ),
    )


def _threshold(value: float) -> AdaptiveThresholdProvenance:
    return AdaptiveThresholdProvenance(
        value=value,
        scope=[],
        threshold_scope_kind="document",
        sample_count=10,
        method="mad_quantile",
        median=0.03,
        mad=0.01,
        robust_scale=0.014826,
        q25=0.02,
        q75=0.05,
        q90=value,
        mad_lambda=1.5,
        low_confidence=False,
        degenerate=False,
    )


def _calibration(
    index: int,
    *,
    fused: float,
    candidate: bool,
) -> ScaleCalibrationProvenance:
    del index
    threshold = _threshold(0.05)
    return ScaleCalibrationProvenance(
        available_scales=[1, 2, 3],
        shift_1=0.08,
        shift_2=0.03,
        shift_3=0.02,
        threshold_1=0.05,
        threshold_2=0.05,
        threshold_3=0.05,
        candidate_1=candidate,
        candidate_2=False,
        candidate_3=False,
        threshold_provenance_1=threshold,
        threshold_provenance_2=threshold,
        threshold_provenance_3=threshold,
        calibrated_evidence_1=fused / 0.35 if fused else 0.0,
        calibrated_evidence_2=0.0,
        calibrated_evidence_3=0.0,
        effective_weight_1=0.35,
        effective_weight_2=0.26,
        effective_weight_3=0.39,
        fused_evidence=fused,
        fused_candidate=candidate,
    )


def test_per_scale_thresholds_use_independent_observed_distributions() -> None:
    units = [_unit(index) for index in range(11)]
    boundaries = [
        _boundary(
            index,
            (
                0.01 * (index + 1),
                0.005 * (index + 1),
                0.0025 * (index + 1),
            ),
        )
        for index in range(10)
    ]
    semantic = AdaptiveSemanticConfig(
        min_section_boundaries=20,
        min_document_boundaries=8,
    )
    result = PerScaleAdaptiveCalibrator(
        semantic,
        _multi_scale_config(),
    ).apply(boundaries, {unit.unit_id: unit for unit in units})

    final = result[9]
    assert final.threshold_1 != final.threshold_2
    assert final.threshold_2 != final.threshold_3
    assert final.candidate_1 is True
    assert final.candidate_2 is True
    assert final.candidate_3 is True
    expected_1 = (final.shift_1 - final.threshold_1) / (1.0 - final.threshold_1)
    assert final.calibrated_evidence_1 == pytest.approx(expected_1)
    assert final.fused_evidence == pytest.approx(
        0.35 * final.calibrated_evidence_1
        + 0.26 * final.calibrated_evidence_2
        + 0.39 * final.calibrated_evidence_3
    )


def test_calibrated_selector_ranks_with_fused_evidence_not_raw_combined_shift() -> None:
    units = [_unit(index) for index in range(4)]
    threshold = _threshold(0.05)
    boundaries = [
        _boundary(0, (0.20, 0.20, 0.20)).model_copy(
            update={"adaptive_threshold": threshold, "semantic_candidate": True}
        ),
        _boundary(1, (0.08, 0.03, 0.02)).model_copy(
            update={"adaptive_threshold": threshold, "semantic_candidate": True}
        ),
        _boundary(2, (0.01, 0.01, 0.01)).model_copy(
            update={"adaptive_threshold": threshold, "semantic_candidate": False}
        ),
    ]
    calibrations = {
        0: _calibration(0, fused=0.01, candidate=True),
        1: _calibration(1, fused=0.10, candidate=True),
        2: _calibration(2, fused=0.0, candidate=False),
    }
    counter = WordTokenCounter()
    limits = TokenLimitsConfig(
        min_tokens=1,
        target_tokens=4,
        soft_max_tokens=7,
        hard_max_tokens=9,
    )
    budgeter = RenderedTokenBudgeter(counter, limits.hard_max_tokens)
    selector = ScaleCalibratedIntervalBoundarySelector(
        budgeter=budgeter,
        token_limits=limits,
        semantic=None,
        selection=SelectionConfig(semantic_weight=0.8, size_weight=0.2),
        semantic_boundary_reason="adaptive_semantic_boundary",
        tail_resolver=V2TailResolver(budgeter, limits),
        calibration_by_boundary=calibrations,
    )

    segments, _ = selector.select(units, boundaries)

    assert segments[0].end_boundary.boundary_index == 1
    assert segments[0].end_boundary.semantic_shift < boundaries[0].semantic_shift
    assert segments[0].end_boundary.selection_signal == pytest.approx(0.10)


def test_b0_copy_is_byte_identical(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    for index, name in enumerate(
        ("chunks.jsonl", "boundaries.jsonl", "metrics.json", "resolved-config.json")
    ):
        (source / name).write_bytes(f"payload-{index}\r\n".encode())

    _copy_byte_identical_baseline(source, destination)

    for name in (
        "chunks.jsonl",
        "boundaries.jsonl",
        "metrics.json",
        "resolved-config.json",
    ):
        assert (destination / name).read_bytes() == (source / name).read_bytes()
