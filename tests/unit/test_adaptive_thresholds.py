from __future__ import annotations

import numpy as np
import pytest

from amsc.config import AdaptiveSemanticConfig
from amsc.models import BoundaryEvidence, ContentUnit, SourceSpan, UnitType
from amsc.thresholds import (
    HierarchicalAdaptiveThresholdEstimator,
    longest_common_prefix,
)


def adaptive_config(**changes: object) -> AdaptiveSemanticConfig:
    values: dict[str, object] = {
        "strategy": "hierarchical_adaptive",
        "mad_lambda": 1.5,
        "quantile_floor": 0.75,
        "quantile_ceiling": 0.90,
        "min_section_boundaries": 2,
        "min_document_boundaries": 3,
        "short_document_fallback_threshold": 0.20,
        "dispersion_epsilon": 1.0e-8,
    }
    values.update(changes)
    return AdaptiveSemanticConfig.model_validate(values)


def unit(unit_id: str, path: tuple[str, ...]) -> ContentUnit:
    return ContentUnit(
        document_id="d",
        unit_id=unit_id,
        source_unit_id=unit_id,
        order=0,
        text=unit_id,
        type=UnitType.PARAGRAPH,
        section_path=path,
        source=SourceSpan(page=1),
        semantic_text=unit_id,
    )


def dataset(
    shifts_and_paths: list[tuple[float, tuple[str, ...], tuple[str, ...]]],
) -> tuple[list[BoundaryEvidence], dict[str, ContentUnit]]:
    boundaries: list[BoundaryEvidence] = []
    units: dict[str, ContentUnit] = {}
    for index, (shift, left_path, right_path) in enumerate(shifts_and_paths):
        left_id = f"left-{index}"
        right_id = f"right-{index}"
        units[left_id] = unit(left_id, left_path)
        units[right_id] = unit(right_id, right_path)
        boundaries.append(
            BoundaryEvidence(
                boundary_index=index,
                left_unit_id=left_id,
                right_unit_id=right_id,
                cosine_similarity=1.0 - 2.0 * shift,
                semantic_shift=shift,
                semantic_candidate=False,
            )
        )
    return boundaries, units


def apply(
    values: list[tuple[float, tuple[str, ...], tuple[str, ...]]],
    config: AdaptiveSemanticConfig | None = None,
) -> list[BoundaryEvidence]:
    boundaries, units = dataset(values)
    return HierarchicalAdaptiveThresholdEstimator(
        config or adaptive_config()
    ).apply(boundaries, units)


def test_longest_common_prefix_scope() -> None:
    assert longest_common_prefix(
        ("Risk", "Kredi", "Kurumsal"),
        ("Risk", "Kredi", "Bireysel"),
    ) == ("Risk", "Kredi")
    assert longest_common_prefix(("Risk",), ("Finans",)) == ()


def test_median_mad_quantile_clamp_and_section_scope() -> None:
    shifts = [0.05, 0.10, 0.20, 0.40]
    result = apply([(shift, ("A",), ("A",)) for shift in shifts])
    provenance = result[0].adaptive_threshold
    assert provenance is not None

    values = np.asarray(shifts)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    q75 = float(np.quantile(values, 0.75))
    q90 = float(np.quantile(values, 0.90))
    expected = min(q90, max(q75, median + 1.5 * 1.4826 * mad))
    assert provenance.value == pytest.approx(expected)
    assert provenance.median == pytest.approx(median)
    assert provenance.mad == pytest.approx(mad)
    assert provenance.robust_scale == pytest.approx(1.4826 * mad)
    assert provenance.method == "mad_quantile"
    assert provenance.threshold_scope_kind == "section"
    assert provenance.scope == ["A"]
    assert provenance.sample_count == 4


def test_zero_mad_uses_iqr_scale() -> None:
    shifts = [0.1, 0.1, 0.1, 0.2, 0.3]
    result = apply([(shift, ("A",), ("A",)) for shift in shifts])
    provenance = result[0].adaptive_threshold
    assert provenance is not None
    assert provenance.mad == pytest.approx(0.0)
    assert provenance.robust_scale == pytest.approx((0.2 - 0.1) / 1.349)
    assert provenance.method == "iqr_quantile"
    assert provenance.degenerate is False


def test_iqr_uses_fixed_q75_when_clamp_floor_is_q70() -> None:
    shifts = [0.1, 0.1, 0.1, 0.2, 0.3]
    result = apply(
        [(shift, ("A",), ("A",)) for shift in shifts],
        adaptive_config(quantile_floor=0.70),
    )
    provenance = result[0].adaptive_threshold
    assert provenance is not None
    q25 = float(np.quantile(np.asarray(shifts), 0.25))
    q75 = float(np.quantile(np.asarray(shifts), 0.75))
    assert provenance.q75 == pytest.approx(q75)
    assert provenance.robust_scale == pytest.approx((q75 - q25) / 1.349)
    assert provenance.method == "iqr_quantile"


def test_default_q75_clamp_retains_previous_threshold_result() -> None:
    shifts = [0.1, 0.1, 0.1, 0.2, 0.3]
    result = apply([(shift, ("A",), ("A",)) for shift in shifts])
    provenance = result[0].adaptive_threshold
    assert provenance is not None
    expected_scale = (0.2 - 0.1) / 1.349
    expected_threshold = min(0.26, max(0.2, 0.1 + 1.5 * expected_scale))
    assert provenance.robust_scale == pytest.approx(expected_scale)
    assert provenance.value == pytest.approx(expected_threshold)


def test_zero_mad_and_iqr_uses_smallest_positive_tail() -> None:
    shifts = [0.1] * 8 + [0.5]
    result = apply([(shift, ("A",), ("A",)) for shift in shifts])
    provenance = result[0].adaptive_threshold
    assert provenance is not None
    assert provenance.value == pytest.approx(0.5)
    assert provenance.method == "positive_tail"
    assert provenance.degenerate is False


def test_uniform_sufficient_document_is_degenerate_and_has_no_candidates() -> None:
    result = apply(
        [(0.1, (), ()) for _ in range(8)],
        adaptive_config(min_document_boundaries=8),
    )
    assert all(item.semantic_candidate is False for item in result)
    for item in result:
        provenance = item.adaptive_threshold
        assert provenance is not None
        assert provenance.method == "uniform_document_no_candidate"
        assert provenance.degenerate is True
        assert provenance.threshold_scope_kind == "document"


def test_short_document_uses_fixed_fallback_not_q75() -> None:
    shifts = [0.01, 0.10, 0.30, 0.90]
    result = apply(
        [(shift, (), ()) for shift in shifts],
        adaptive_config(min_document_boundaries=8),
    )
    assert [item.semantic_candidate for item in result] == [False, False, True, True]
    for item in result:
        provenance = item.adaptive_threshold
        assert provenance is not None
        assert provenance.value == pytest.approx(0.20)
        assert provenance.method == "short_document_fixed_fallback"
        assert provenance.low_confidence is True
        assert provenance.threshold_scope_kind == "document"
        assert provenance.sample_count == 4
        assert provenance.q75 is None


def test_child_falls_back_to_parent_and_parent_includes_descendants() -> None:
    values = [
        (0.10, ("A", "B"), ("A", "B")),
        (0.20, ("A", "C"), ("A", "C")),
        (0.40, ("A", "D"), ("A", "D")),
    ]
    result = apply(values, adaptive_config(min_section_boundaries=3))
    provenance = result[0].adaptive_threshold
    assert provenance is not None
    assert provenance.scope == ["A"]
    assert provenance.sample_count == 3
    assert provenance.threshold_scope_kind == "parent_section"


def test_degenerate_child_distribution_falls_back_to_parent() -> None:
    values = [
        (0.10, ("A", "B"), ("A", "B")),
        (0.10, ("A", "B"), ("A", "B")),
        (0.20, ("A", "C"), ("A", "C")),
        (0.40, ("A", "D"), ("A", "D")),
    ]
    result = apply(values, adaptive_config(min_section_boundaries=2))
    provenance = result[0].adaptive_threshold
    assert provenance is not None
    assert provenance.scope == ["A"]
    assert provenance.sample_count == 4
    assert provenance.threshold_scope_kind == "parent_section"


def test_parent_shortage_falls_back_to_document() -> None:
    values = [
        (0.10, ("A", "B"), ("A", "B")),
        (0.20, ("X",), ("X",)),
        (0.40, ("Y",), ("Y",)),
    ]
    result = apply(
        values,
        adaptive_config(min_section_boundaries=3, min_document_boundaries=3),
    )
    provenance = result[0].adaptive_threshold
    assert provenance is not None
    assert provenance.scope == []
    assert provenance.threshold_scope_kind == "document"
    assert provenance.sample_count == 3


def test_parent_scope_sample_set_contains_descendant_boundaries() -> None:
    values = [
        (0.10, ("A",), ("A",)),
        (0.20, ("A", "B"), ("A", "B")),
        (0.40, ("A", "C"), ("A", "C")),
    ]
    result = apply(values, adaptive_config(min_section_boundaries=3))
    provenance = result[0].adaptive_threshold
    assert provenance is not None
    assert provenance.threshold_scope_kind == "section"
    assert provenance.scope == ["A"]
    assert provenance.sample_count == 3


def test_each_boundary_uses_its_own_local_threshold() -> None:
    values = [
        *[(shift, ("A",), ("A",)) for shift in [0.01, 0.02, 0.03, 0.04]],
        *[(shift, ("B",), ("B",)) for shift in [0.40, 0.50, 0.60, 0.70]],
    ]
    result = apply(
        values,
        adaptive_config(min_section_boundaries=4, min_document_boundaries=8),
    )
    assert result[3].semantic_candidate is True
    assert result[4].semantic_candidate is False
    assert result[3].semantic_shift < result[4].semantic_shift
    assert result[3].adaptive_threshold is not None
    assert result[4].adaptive_threshold is not None
    assert result[3].adaptive_threshold.scope == ["A"]
    assert result[4].adaptive_threshold.scope == ["B"]


def test_threshold_provenance_is_deterministic() -> None:
    values = [(shift, ("A",), ("A",)) for shift in [0.02, 0.1, 0.2, 0.4]]
    first = apply(values)
    second = apply(values)
    assert [item.model_dump_json() for item in first] == [
        item.model_dump_json() for item in second
    ]
