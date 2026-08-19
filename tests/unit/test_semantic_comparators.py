from __future__ import annotations

import numpy as np
import pytest

from amsc.config import AdaptiveSemanticConfig, MultiScaleConfig
from amsc.models import (
    BoundaryEvidence,
    ContentUnit,
    MultiScaleSemanticProvenance,
    SourceSpan,
    UnitType,
)
from amsc.semantic_comparators import (
    CosineKernelChangePointComparator,
    LocalSemanticProminenceComparator,
)
from conftest import WordTokenCounter


def _config() -> MultiScaleConfig:
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


def _boundary(
    index: int,
    shifts: tuple[float, ...],
) -> BoundaryEvidence:
    available = list(range(1, len(shifts) + 1))
    base = {1: 0.35, 2: 0.26, 3: 0.39}
    total = sum(base[scale] for scale in available)
    weights = {scale: base[scale] / total for scale in available}
    combined = sum(
        weights[scale] * shifts[scale - 1] for scale in available
    )
    return BoundaryEvidence(
        boundary_index=index,
        left_unit_id=f"u{index}",
        right_unit_id=f"u{index + 1}",
        cosine_similarity=1.0 - 2.0 * shifts[0],
        semantic_shift=combined,
        semantic_candidate=False,
        multi_scale=MultiScaleSemanticProvenance(
            shift_1=shifts[0],
            shift_2=shifts[1] if len(shifts) >= 2 else None,
            shift_3=shifts[2] if len(shifts) >= 3 else None,
            available_scales=available,
            scale_count=len(available),
            effective_weight_1=weights[1],
            effective_weight_2=weights.get(2),
            effective_weight_3=weights.get(3),
            unit_weighting="configured_token_counter_sqrt",
            window_pooling="weighted_mean_l2_normalized",
            token_counter_id="test:words",
        ),
    )


def test_local_prominence_detects_isolated_shift_without_new_threshold() -> None:
    units = [_unit(index) for index in range(11)]
    boundaries = [
        _boundary(index, (0.20, 0.05, 0.05))
        if index == 5
        else _boundary(index, (0.05, 0.05, 0.05))
        for index in range(10)
    ]
    result = LocalSemanticProminenceComparator(
        AdaptiveSemanticConfig(min_document_boundaries=8),
        _config(),
    ).compute(boundaries, {unit.unit_id: unit for unit in units})

    assert result[5].raw_local_prominence == pytest.approx(0.15)
    assert result[5].score == pytest.approx(0.15)
    assert result[5].adaptive_threshold is not None
    assert result[5].adaptive_threshold.method == "positive_tail"
    assert result[5].semantic_candidate is True
    assert sum(item.semantic_candidate for item in result.values()) == 1


def test_local_prominence_does_not_invent_context_at_scale_one_edge() -> None:
    units = [_unit(0), _unit(1)]
    boundary = _boundary(0, (0.8,))

    result = LocalSemanticProminenceComparator(
        AdaptiveSemanticConfig(),
        _config(),
    ).compute([boundary], {unit.unit_id: unit for unit in units})[0]

    assert result.broad_context_shift is None
    assert result.adaptive_threshold is None
    assert result.semantic_candidate is False
    assert result.threshold_relative_evidence == 0.0


def test_kernel_change_score_equals_shift_one_for_one_to_one_window() -> None:
    units = [_unit(0), _unit(1)]
    boundary = _boundary(0, (0.5,))
    result = CosineKernelChangePointComparator(
        AdaptiveSemanticConfig(short_document_fallback_threshold=0.20)
    ).compute(
        prepared=units,
        boundaries=[boundary],
        units_by_id={unit.unit_id: unit for unit in units},
        retained_embeddings={
            "u0": np.asarray([1.0, 0.0]),
            "u1": np.asarray([0.0, 1.0]),
        },
        token_counter=WordTokenCounter(),
    )[0]

    assert result.window_size == 1
    assert result.score == pytest.approx(boundary.multi_scale.shift_1)  # type: ignore[union-attr]
    assert result.semantic_candidate is True


def test_kernel_change_point_uses_largest_full_symmetric_window() -> None:
    units = [_unit(index) for index in range(4)]
    boundary = _boundary(1, (0.5, 0.5))
    result = CosineKernelChangePointComparator(
        AdaptiveSemanticConfig(short_document_fallback_threshold=0.20)
    ).compute(
        prepared=units,
        boundaries=[boundary],
        units_by_id={unit.unit_id: unit for unit in units},
        retained_embeddings={
            "u0": np.asarray([1.0, 0.0]),
            "u1": np.asarray([1.0, 0.0]),
            "u2": np.asarray([0.0, 1.0]),
            "u3": np.asarray([0.0, 1.0]),
        },
        token_counter=WordTokenCounter(),
    )[1]

    assert result.window_size == 2
    assert result.score == pytest.approx(0.5)
    assert result.kernel == "normalized_cosine_linear"
    assert result.change_statistic == "token_sqrt_weighted_mmd2_over_2"
