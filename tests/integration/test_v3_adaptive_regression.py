from __future__ import annotations

import math

import numpy as np
import pytest

from amsc.chunker import V3Chunker
from amsc.config import V3Config
from amsc.models import RawDocumentUnit
from conftest import StaticBoundaryEmbedder, WordTokenCounter


@pytest.fixture
def ten_unit_adaptive_document() -> tuple[
    list[RawDocumentUnit], StaticBoundaryEmbedder
]:
    units = [
        RawDocumentUnit.model_validate(
            {
                "document_id": "v3-adaptive-regression",
                "unit_id": f"p-{index}",
                "order": index,
                "text": f"paragraph-{index}",
                "type": "paragraph",
                "section_path": [],
            }
        )
        for index in range(10)
    ]
    angles = [0.00, 0.04, 0.09, 0.15, 0.22, 0.95, 1.04, 1.14, 1.25, 1.37]
    vectors = {
        unit.text: [math.cos(angle), math.sin(angle)]
        for unit, angle in zip(units, angles, strict=True)
    }
    return units, StaticBoundaryEmbedder(vectors)


def test_v3_combined_shifts_drive_document_adaptive_threshold(
    ten_unit_adaptive_document: tuple[
        list[RawDocumentUnit], StaticBoundaryEmbedder
    ],
) -> None:
    units, embedder = ten_unit_adaptive_document
    config = V3Config.from_yaml("configs/v3.yaml")
    result = V3Chunker(
        config=config,
        token_counter=WordTokenCounter(),
        boundary_embedder=embedder,
    ).chunk(units)

    assert len(units) == 10
    assert len(result.boundaries) == 9
    assert len(result.boundaries) >= config.semantic.min_document_boundaries

    combined_shifts = np.asarray(
        [boundary.semantic_shift for boundary in result.boundaries],
        dtype=np.float64,
    )
    median = float(np.median(combined_shifts))
    mad = float(np.median(np.abs(combined_shifts - median)))
    assert mad > config.semantic.dispersion_epsilon

    robust_scale = 1.4826 * mad
    raw_threshold = median + config.semantic.mad_lambda * robust_scale
    clamp_floor = float(
        np.quantile(
            combined_shifts,
            config.semantic.quantile_floor,
            method="linear",
        )
    )
    clamp_ceiling = float(
        np.quantile(
            combined_shifts,
            config.semantic.quantile_ceiling,
            method="linear",
        )
    )
    independently_calculated_threshold = min(
        clamp_ceiling,
        max(clamp_floor, raw_threshold),
    )

    for boundary in result.boundaries:
        provenance = boundary.adaptive_threshold
        assert provenance is not None
        assert provenance.sample_count == 9
        assert provenance.threshold_scope_kind == "document"
        assert provenance.method == "mad_quantile"
        assert provenance.method != "short_document_fixed_fallback"
        assert provenance.value == pytest.approx(
            independently_calculated_threshold
        )
        assert boundary.semantic_candidate is (
            boundary.semantic_shift >= provenance.value
        )

    # Boundary 3 is intentionally a plumbing/regression assertion: the
    # multi-scale windows spread context from the p-4 -> p-5 transition into
    # its neighbor. It must not be interpreted as the fixture's ground-truth
    # transition boundary.
    interior = result.boundaries[3]
    assert interior.multi_scale is not None
    assert interior.multi_scale.available_scales == [1, 2, 3]
    assert interior.semantic_shift != pytest.approx(interior.multi_scale.shift_1)
    assert interior.multi_scale.shift_1 < interior.adaptive_threshold.value
    assert interior.semantic_shift >= interior.adaptive_threshold.value
    assert interior.semantic_candidate is True

    transition = result.boundaries[4]
    assert (transition.left_unit_id, transition.right_unit_id) == ("p-4", "p-5")
    assert transition.multi_scale is not None
    assert transition.multi_scale.available_scales == [1, 2, 3]
    assert transition.semantic_candidate is True
    assert transition.semantic_shift > interior.semantic_shift
    assert transition.semantic_shift == max(
        boundary.semantic_shift for boundary in result.boundaries
    )
