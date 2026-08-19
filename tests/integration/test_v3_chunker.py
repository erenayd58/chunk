from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from amsc.chunker import V2Chunker, V3Chunker
from amsc.cli import main
from amsc.config import V2Config, V3Config
from amsc.io import load_jsonl_units, write_chunking_result
from amsc.models import RawDocumentUnit
from amsc.tokenization import TiktokenTokenCounter
from conftest import StaticBoundaryEmbedder, WordTokenCounter


def common_payload() -> dict[str, object]:
    return {
        "algorithm": {
            "version": "v3",
            "tuning_status": "poc_initial_not_optimized",
        },
        "token_counter": {
            "provider": "tiktoken",
            "encoding": "cl100k_base",
            "cap_semantics": "configured_poc_counter_only",
        },
        "boundary_embedding": {
            "model": "test",
            "device": "cpu",
            "prefix_policy": "symmetric_query",
            "prefix": "query: ",
            "overlength_strategy": "sentence_fragment_token_weighted_pooling",
            "normalize_embeddings": True,
            "cache_dir": ".cache/test-v3",
        },
        "semantic": {
            "strategy": "hierarchical_adaptive",
            "mad_lambda": 1.5,
            "quantile_floor": 0.75,
            "quantile_ceiling": 0.90,
            "min_section_boundaries": 20,
            "min_document_boundaries": 8,
            "short_document_fallback_threshold": 0.20,
            "dispersion_epsilon": 1.0e-8,
        },
        "multi_scale": {
            "shift_1_weight": 0.35,
            "shift_2_weight": 0.26,
            "shift_3_weight": 0.39,
            "unit_weighting": "configured_token_counter_sqrt",
            "window_pooling": "weighted_mean_l2_normalized",
            "edge_policy": "full_symmetric_available_scales",
        },
        "tokens": {
            "min_tokens": 2,
            "target_tokens": 7,
            "soft_max_tokens": 10,
            "hard_max_tokens": 12,
        },
        "selection": {"semantic_weight": 0.8, "size_weight": 0.2},
    }


def small_v3_config() -> V3Config:
    return V3Config.model_validate(common_payload())


def matching_v2_config() -> V2Config:
    payload = common_payload()
    payload["algorithm"] = {
        "version": "v2",
        "tuning_status": "poc_initial_not_optimized",
    }
    payload.pop("multi_scale")
    return V2Config.model_validate(payload)


def paragraphs(count: int) -> list[RawDocumentUnit]:
    return [
        RawDocumentUnit.model_validate(
            {
                "document_id": "multi",
                "unit_id": f"p-{index}",
                "order": index,
                "text": f"paragraph-{index}",
                "type": "paragraph",
                "section_path": [],
            }
        )
        for index in range(count)
    ]


def test_v3_end_to_end_provenance_heading_exclusion_and_threshold(tmp_path) -> None:
    units = load_jsonl_units("tests/fixtures/sample.units.jsonl")
    embedder = StaticBoundaryEmbedder(
        {units[1].text: [1.0, 0.0], units[3].text: [0.0, 1.0]}
    )
    result = V3Chunker(
        config=small_v3_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=embedder,
    ).chunk(units)

    assert embedder.calls == [[units[1].text, units[3].text]]
    assert result.algorithm_version == "amsc-v3"
    assert all(chunk.algorithm_version == "amsc-v3" for chunk in result.chunks)
    assert result.chunks[0].end_boundary.reason == "adaptive_semantic_boundary"
    assert result.chunks[0].end_boundary.multi_scale is not None
    boundary = result.boundaries[0]
    assert boundary.multi_scale is not None
    assert boundary.multi_scale.available_scales == [1]
    assert boundary.multi_scale.scale_count == 1
    assert boundary.multi_scale.token_counter_id == "test:whitespace@1"
    assert boundary.adaptive_threshold is not None
    assert boundary.adaptive_threshold.method == "short_document_fixed_fallback"

    write_chunking_result(result, tmp_path)
    row = json.loads(
        (tmp_path / "boundaries.jsonl").read_text(encoding="utf-8").strip()
    )
    assert row["multi_scale"]["available_scales"] == [1]
    assert row["multi_scale"]["scale_count"] == 1
    assert "shift_2" not in row["multi_scale"]


def test_v2_shift_1_is_preserved_while_v3_combines_available_scales() -> None:
    units = paragraphs(6)
    vectors = {
        unit.text: vector
        for unit, vector in zip(
            units,
            [
                [1.0, 0.0],
                [1.0, 0.0],
                [1.0, 0.0],
                [0.0, 1.0],
                [1.0, 0.0],
                [1.0, 0.0],
            ],
            strict=True,
        )
    }
    v2 = V2Chunker(
        config=matching_v2_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=StaticBoundaryEmbedder(vectors),
    ).chunk(units)
    v3_embedder = StaticBoundaryEmbedder(vectors)
    v3 = V3Chunker(
        config=small_v3_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=v3_embedder,
    ).chunk(units)

    assert v3_embedder.calls == [[unit.text for unit in units]]
    for v2_boundary, v3_boundary in zip(v2.boundaries, v3.boundaries, strict=True):
        assert v3_boundary.multi_scale is not None
        assert v3_boundary.multi_scale.shift_1 == pytest.approx(
            v2_boundary.semantic_shift
        )
    assert v3.boundaries[2].semantic_shift != pytest.approx(
        v2.boundaries[2].semantic_shift
    )
    assert v3.boundaries[2].adaptive_threshold is not None
    assert v3.boundaries[2].adaptive_threshold.sample_count == 5


def test_different_scale_compositions_share_v3_threshold_distribution() -> None:
    units = paragraphs(6)
    vectors = {
        unit.text: [1.0, float(index + 1)]
        for index, unit in enumerate(units)
    }
    result = V3Chunker(
        config=small_v3_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=StaticBoundaryEmbedder(vectors),
    ).chunk(units)
    compositions = [
        boundary.multi_scale.available_scales  # type: ignore[union-attr]
        for boundary in result.boundaries
    ]
    assert compositions == [[1], [1, 2], [1, 2, 3], [1, 2], [1]]
    assert {
        boundary.adaptive_threshold.sample_count  # type: ignore[union-attr]
        for boundary in result.boundaries
    } == {5}


def test_heading_only_flush_splits_semantic_runs() -> None:
    raw = [
        RawDocumentUnit.model_validate(
            {
                "document_id": "runs",
                "unit_id": "before",
                "order": 1,
                "text": "before",
                "type": "paragraph",
            }
        ),
        RawDocumentUnit.model_validate(
            {
                "document_id": "runs",
                "unit_id": "heading",
                "order": 2,
                "text": " ".join(f"heading-{index}" for index in range(15)),
                "type": "heading",
                "heading_level": 1,
            }
        ),
        RawDocumentUnit.model_validate(
            {
                "document_id": "runs",
                "unit_id": "after-1",
                "order": 3,
                "text": "after-one",
                "type": "paragraph",
            }
        ),
        RawDocumentUnit.model_validate(
            {
                "document_id": "runs",
                "unit_id": "after-2",
                "order": 4,
                "text": "after-two",
                "type": "paragraph",
            }
        ),
    ]
    embedder = StaticBoundaryEmbedder(
        {
            "before": [1.0, 0.0],
            "after-one": [0.0, 1.0],
            "after-two": [0.1, 0.9],
        }
    )
    result = V3Chunker(
        config=small_v3_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=embedder,
    ).chunk(raw)
    assert embedder.calls == [["before"], ["after-one", "after-two"]]
    assert [(item.left_unit_id, item.right_unit_id) for item in result.boundaries] == [
        ("after-1", "after-2")
    ]


def test_v3_jsonl_is_deterministic() -> None:
    units = load_jsonl_units("tests/fixtures/sample.units.jsonl")
    vectors = {units[1].text: [1.0, 0.0], units[3].text: [0.0, 1.0]}
    first = V3Chunker(
        config=small_v3_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=StaticBoundaryEmbedder(vectors),
    ).chunk(units)
    second = V3Chunker(
        config=small_v3_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=StaticBoundaryEmbedder(vectors),
    ).chunk(units)
    assert first.model_dump_json() == second.model_dump_json()


def test_v3_persisted_jsonl_is_byte_for_byte_golden(tmp_path: Path) -> None:
    units = load_jsonl_units("tests/fixtures/sample.units.jsonl")
    embedder = StaticBoundaryEmbedder(
        {units[1].text: [1.0, 0.0], units[3].text: [0.0, 1.0]}
    )
    result = V3Chunker(
        config=small_v3_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=embedder,
    ).chunk(units)
    write_chunking_result(result, tmp_path)

    golden = Path("tests/fixtures/v3-golden")
    assert (tmp_path / "chunks.jsonl").read_bytes() == (
        golden / "chunks.jsonl"
    ).read_bytes()
    assert (tmp_path / "boundaries.jsonl").read_bytes() == (
        golden / "boundaries.jsonl"
    ).read_bytes()


def test_v3_preserves_configured_cl100k_hard_cap() -> None:
    units = load_jsonl_units("tests/fixtures/sample.units.jsonl")
    vectors = {units[1].text: [1.0, 0.0], units[3].text: [0.0, 1.0]}
    config = V3Config.from_yaml("configs/v3.yaml")
    counter = TiktokenTokenCounter(config.token_counter.encoding)
    result = V3Chunker(
        config=config,
        token_counter=counter,
        boundary_embedder=StaticBoundaryEmbedder(vectors),
    ).chunk(units)
    assert all(
        counter.count(chunk.text) <= config.tokens.hard_max_tokens
        for chunk in result.chunks
    )
    assert all(
        chunk.hard_cap_semantics == "configured_poc_counter_only"
        for chunk in result.chunks
    )


def test_v3_config_rejects_missing_negative_and_future_fields() -> None:
    payload = common_payload()
    payload["multi_scale"].pop("shift_3_weight")  # type: ignore[union-attr]
    with pytest.raises(ValidationError):
        V3Config.model_validate(payload)

    payload = common_payload()
    payload["multi_scale"]["shift_2_weight"] = -0.1  # type: ignore[index]
    with pytest.raises(ValidationError):
        V3Config.model_validate(payload)

    payload = common_payload()
    payload["semantic"]["heading_boost"] = 0.1  # type: ignore[index]
    with pytest.raises(ValidationError):
        V3Config.model_validate(payload)


def test_v3_default_config_marks_scale_weights_as_unoptimized() -> None:
    config = V3Config.from_yaml("configs/v3.yaml")
    assert config.algorithm.tuning_status == "poc_initial_not_optimized"
    assert config.multi_scale.shift_weights == {1: 0.35, 2: 0.26, 3: 0.39}


def test_cli_routes_v3_config(monkeypatch, tmp_path: Path) -> None:
    units = load_jsonl_units("tests/fixtures/sample.units.jsonl")
    embedder = StaticBoundaryEmbedder(
        {units[1].text: [1.0, 0.0], units[3].text: [0.0, 1.0]}
    )
    monkeypatch.setattr(
        "amsc.cli.SentenceTransformerBoundaryEmbedder.from_pretrained",
        lambda *args, **kwargs: embedder,
    )
    payload = common_payload()
    payload["tokens"] = {
        "min_tokens": 2,
        "target_tokens": 50,
        "soft_max_tokens": 80,
        "hard_max_tokens": 100,
    }
    payload["boundary_embedding"]["cache_dir"] = str(  # type: ignore[index]
        tmp_path / "cache"
    )
    config_path = tmp_path / "v3.yaml"
    config_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8"
    )
    output_path = tmp_path / "output"
    assert main(
        [
            "chunk",
            "--input",
            "tests/fixtures/sample.units.jsonl",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ]
    ) == 0
    chunk_row = json.loads(
        (output_path / "chunks.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    boundary_row = json.loads(
        (output_path / "boundaries.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert chunk_row["algorithm_version"] == "amsc-v3"
    assert boundary_row["multi_scale"]["scale_count"] == 1
