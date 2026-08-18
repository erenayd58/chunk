from __future__ import annotations

from dataclasses import replace
import math

import numpy as np
import pytest
from pydantic import ValidationError

from amsc.config import MultiScaleConfig
from amsc.features import (
    MultiScaleSemanticFeatureExtractor,
    TokenSqrtWindowPooler,
)
from amsc.models import (
    ContentUnit,
    EmbeddingBatch,
    HeadingAttachment,
    MultiScaleSemanticProvenance,
    SemanticEmbeddingProvenance,
    SourceSpan,
    UnitType,
)
from conftest import WordTokenCounter


def multi_scale_config() -> MultiScaleConfig:
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


def unit(
    index: int,
    *,
    words: int = 1,
    unit_type: UnitType = UnitType.PARAGRAPH,
    semantic: bool = True,
) -> ContentUnit:
    text = " ".join(f"u{index}_{part}" for part in range(words))
    return ContentUnit(
        document_id="d",
        unit_id=f"u{index}",
        source_unit_id=f"u{index}",
        order=index,
        text=text,
        type=unit_type,
        section_path=(),
        source=SourceSpan(page=1, block=index),
        semantic_text=text if semantic else None,
    )


def batch(vectors: list[list[float]]) -> EmbeddingBatch:
    provenance = SemanticEmbeddingProvenance(
        model_id="m",
        prefix_policy="symmetric_query",
        prefix="query: ",
        model_input_limit=512,
        semantic_fragment_count=1,
        semantic_pooling="token_weighted_mean",
    )
    return EmbeddingBatch(
        vectors=np.asarray(vectors, dtype=np.float32),
        provenance=tuple(provenance for _ in vectors),
    )


def extractor() -> MultiScaleSemanticFeatureExtractor:
    return MultiScaleSemanticFeatureExtractor(
        multi_scale_config(), WordTokenCounter()
    )


def test_known_topic_transition_has_expected_1_2_3_shifts() -> None:
    units = [unit(index) for index in range(6)]
    vectors = [[1.0, 0.0]] * 3 + [[0.0, 1.0]] * 3
    boundary = extractor().compute_raw(units, batch(vectors))[2]
    provenance = boundary.multi_scale
    assert provenance is not None
    assert provenance.available_scales == [1, 2, 3]
    assert provenance.scale_count == 3
    assert provenance.shift_1 == pytest.approx(0.5)
    assert provenance.shift_2 == pytest.approx(0.5)
    assert provenance.shift_3 == pytest.approx(0.5)
    assert boundary.cosine_similarity == pytest.approx(0.0)
    assert boundary.semantic_shift == pytest.approx(0.5)


def test_token_sqrt_pooling_and_l2_normalization() -> None:
    pooled = TokenSqrtWindowPooler().pool(
        [[1.0, 0.0], [0.0, 1.0]], [1, 4]
    )
    assert pooled == pytest.approx(np.asarray([1.0, 2.0]) / math.sqrt(5.0))
    assert np.linalg.norm(pooled) == pytest.approx(1.0)


def test_full_symmetric_edges_and_weight_renormalization() -> None:
    units = [unit(index) for index in range(6)]
    vectors = [[1.0, float(index + 1)] for index in range(6)]
    boundaries = extractor().compute_raw(units, batch(vectors))

    first = boundaries[0].multi_scale
    second = boundaries[1].multi_scale
    middle = boundaries[2].multi_scale
    last = boundaries[-1].multi_scale
    assert first is not None and second is not None
    assert middle is not None and last is not None
    assert first.available_scales == [1]
    assert first.scale_count == 1
    assert first.effective_weight_1 == pytest.approx(1.0)
    assert first.shift_2 is None and first.shift_3 is None
    assert second.available_scales == [1, 2]
    assert second.effective_weight_1 == pytest.approx(0.35 / 0.61)
    assert second.effective_weight_2 == pytest.approx(0.26 / 0.61)
    assert second.effective_weight_3 is None
    assert middle.available_scales == [1, 2, 3]
    assert last.available_scales == [1]

    for boundary in boundaries:
        provenance = boundary.multi_scale
        assert provenance is not None
        weights = [
            provenance.effective_weight_1,
            provenance.effective_weight_2,
            provenance.effective_weight_3,
        ]
        assert sum(weight for weight in weights if weight is not None) == pytest.approx(
            1.0
        )


def test_unavailable_scale_fields_are_omitted_from_json() -> None:
    units = [unit(0), unit(1)]
    boundary = extractor().compute_raw(
        units, batch([[1.0, 0.0], [0.0, 1.0]])
    )[0]
    payload = boundary.model_dump(mode="json", exclude_none=True)["multi_scale"]
    assert payload["available_scales"] == [1]
    assert payload["scale_count"] == 1
    assert "shift_2" not in payload
    assert "shift_3" not in payload
    assert "effective_weight_2" not in payload
    assert "effective_weight_3" not in payload


def test_wide_windows_suppress_a_single_outlier_spike() -> None:
    units = [unit(index) for index in range(6)]
    vectors = [
        [1.0, 0.0],
        [1.0, 0.0],
        [1.0, 0.0],
        [0.0, 1.0],
        [1.0, 0.0],
        [1.0, 0.0],
    ]
    boundary = extractor().compute_raw(units, batch(vectors))[2]
    provenance = boundary.multi_scale
    assert provenance is not None
    assert provenance.shift_2 is not None and provenance.shift_3 is not None
    assert provenance.shift_2 < provenance.shift_1
    assert provenance.shift_3 < provenance.shift_2
    assert boundary.semantic_shift < provenance.shift_1
    assert boundary.semantic_shift == pytest.approx(
        provenance.effective_weight_1 * provenance.shift_1
        + (provenance.effective_weight_2 or 0.0) * provenance.shift_2
        + (provenance.effective_weight_3 or 0.0) * provenance.shift_3
    )


def test_real_transition_is_supported_by_multiple_scales() -> None:
    units = [unit(index) for index in range(6)]
    vectors = [[1.0, 0.0]] * 3 + [[0.0, 1.0]] * 3
    provenance = extractor().compute_raw(units, batch(vectors))[2].multi_scale
    assert provenance is not None
    assert provenance.scale_count == 3
    assert min(provenance.shift_1, provenance.shift_2 or 0, provenance.shift_3 or 0) >= 0.49


def test_heading_only_unit_cannot_enter_semantic_window() -> None:
    heading = unit(0, unit_type=UnitType.HEADING, semantic=False)
    with pytest.raises(ValueError, match="Heading-only unit"):
        extractor().compute_raw([heading], batch([[1.0, 0.0]]))


def test_attached_heading_is_not_counted_for_window_weighting() -> None:
    class RecordingCounter(WordTokenCounter):
        def __init__(self) -> None:
            self.calls: list[str] = []

        def count(self, text: str) -> int:
            self.calls.append(text)
            return super().count(text)

    first = replace(
        unit(0, words=2),
        leading_headings=(
            HeadingAttachment(
                unit_id="h",
                text="very long attached heading text",
                heading_level=1,
                source=SourceSpan(page=1, block="h"),
            ),
        ),
    )
    second = unit(1, words=3)
    counter = RecordingCounter()
    feature_extractor = MultiScaleSemanticFeatureExtractor(
        multi_scale_config(), counter
    )
    feature_extractor.compute_raw(
        [first, second], batch([[1.0, 0.0], [0.0, 1.0]])
    )
    assert counter.calls == [first.text_for_embedding, second.text_for_embedding]


def test_separate_semantic_runs_never_create_cross_run_boundary() -> None:
    first_units = [unit(index) for index in range(3)]
    second_units = [unit(index + 3) for index in range(3)]
    first = extractor().compute_raw(
        first_units,
        batch([[1.0, 0.0], [0.9, 0.1], [0.8, 0.2]]),
    )
    second = extractor().compute_raw(
        second_units,
        batch([[0.2, 0.8], [0.1, 0.9], [0.0, 1.0]]),
        boundary_index_offset=len(first),
    )
    assert len(first + second) == 4
    assert all(boundary.multi_scale is not None for boundary in first + second)
    assert all(
        boundary.multi_scale.available_scales == [1]  # type: ignore[union-attr]
        for boundary in first + second
    )
    assert not any(
        boundary.left_unit_id == "u2" and boundary.right_unit_id == "u3"
        for boundary in first + second
    )


def test_zero_token_and_zero_vector_fail_fast() -> None:
    with pytest.raises(ValueError, match="token counts must be positive"):
        TokenSqrtWindowPooler().pool([[1.0, 0.0]], [0])
    with pytest.raises(ValueError, match="zero semantic unit vector"):
        TokenSqrtWindowPooler().pool([[0.0, 0.0]], [1])


def test_multi_scale_provenance_is_deterministic() -> None:
    units = [unit(index) for index in range(6)]
    vectors = [[1.0, float(index + 1)] for index in range(6)]
    first = extractor().compute_raw(units, batch(vectors))
    second = extractor().compute_raw(units, batch(vectors))
    assert [item.model_dump_json() for item in first] == [
        item.model_dump_json() for item in second
    ]


def test_provenance_rejects_noncontiguous_available_scales() -> None:
    with pytest.raises(ValidationError, match="contiguous prefix"):
        MultiScaleSemanticProvenance(
            shift_1=0.1,
            shift_3=0.3,
            available_scales=[1, 3],
            scale_count=2,
            effective_weight_1=0.5,
            effective_weight_3=0.5,
            unit_weighting="configured_token_counter_sqrt",
            window_pooling="weighted_mean_l2_normalized",
            token_counter_id="test",
        )
