from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from amsc.chunker import V1Chunker, V2Chunker
from amsc.cli import main
from amsc.config import V1Config, V2Config
from amsc.io import load_jsonl_units, write_chunking_result
from amsc.models import RawDocumentUnit
from amsc.tokenization import TiktokenTokenCounter
from conftest import StaticBoundaryEmbedder, WordTokenCounter


def small_v2_config(**semantic_changes: object) -> V2Config:
    semantic: dict[str, object] = {
        "strategy": "hierarchical_adaptive",
        "mad_lambda": 1.5,
        "quantile_floor": 0.75,
        "quantile_ceiling": 0.90,
        "min_section_boundaries": 20,
        "min_document_boundaries": 8,
        "short_document_fallback_threshold": 0.20,
        "dispersion_epsilon": 1.0e-8,
    }
    semantic.update(semantic_changes)
    return V2Config.model_validate(
        {
            "algorithm": {
                "version": "v2",
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
                "overlength_strategy": (
                    "sentence_fragment_token_weighted_pooling"
                ),
                "normalize_embeddings": True,
                "cache_dir": ".cache/test-v2",
            },
            "semantic": semantic,
            "tokens": {
                "min_tokens": 2,
                "target_tokens": 7,
                "soft_max_tokens": 10,
                "hard_max_tokens": 12,
            },
            "selection": {"semantic_weight": 0.8, "size_weight": 0.2},
        }
    )


def small_v1_config() -> V1Config:
    payload = small_v2_config().model_dump(mode="json")
    payload["algorithm"]["version"] = "v1"
    payload["semantic"] = {"fixed_threshold": 0.20}
    return V1Config.model_validate(payload)


def test_v2_short_document_provenance_heading_exclusion_and_cap(tmp_path) -> None:
    units = load_jsonl_units("tests/fixtures/sample.units.jsonl")
    embedder = StaticBoundaryEmbedder(
        {units[1].text: [1.0, 0.0], units[3].text: [0.0, 1.0]}
    )
    result = V2Chunker(
        config=small_v2_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=embedder,
    ).chunk(units)

    assert embedder.calls == [[units[1].text, units[3].text]]
    assert result.algorithm_version == "amsc-v2"
    assert all(chunk.algorithm_version == "amsc-v2" for chunk in result.chunks)
    assert all(chunk.token_count <= 12 for chunk in result.chunks)
    assert result.chunks[0].end_boundary.reason == "adaptive_semantic_boundary"
    assert result.boundaries[0].fixed_threshold is None
    provenance = result.boundaries[0].adaptive_threshold
    assert provenance is not None
    assert provenance.method == "short_document_fixed_fallback"
    assert provenance.low_confidence is True
    assert provenance.threshold_scope_kind == "document"
    assert provenance.sample_count == 1

    write_chunking_result(result, tmp_path)
    boundary_row = json.loads(
        (tmp_path / "boundaries.jsonl").read_text(encoding="utf-8").strip()
    )
    assert "fixed_threshold" not in boundary_row
    assert boundary_row["adaptive_threshold"]["threshold_scope_kind"] == "document"
    scope_counts: dict[str, int] = {}
    kind = boundary_row["adaptive_threshold"]["threshold_scope_kind"]
    scope_counts[kind] = scope_counts.get(kind, 0) + 1
    assert scope_counts == {"document": 1}


def test_v2_jsonl_is_deterministic() -> None:
    units = load_jsonl_units("tests/fixtures/sample.units.jsonl")
    vectors = {units[1].text: [1.0, 0.0], units[3].text: [0.0, 1.0]}
    first = V2Chunker(
        config=small_v2_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=StaticBoundaryEmbedder(vectors),
    ).chunk(units)
    second = V2Chunker(
        config=small_v2_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=StaticBoundaryEmbedder(vectors),
    ).chunk(units)
    assert first.model_dump_json() == second.model_dump_json()


def test_v2_persisted_jsonl_is_byte_for_byte_golden(tmp_path: Path) -> None:
    units = load_jsonl_units("tests/fixtures/sample.units.jsonl")
    embedder = StaticBoundaryEmbedder(
        {units[1].text: [1.0, 0.0], units[3].text: [0.0, 1.0]}
    )
    result = V2Chunker(
        config=small_v2_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=embedder,
    ).chunk(units)
    write_chunking_result(result, tmp_path)

    golden = Path("tests/fixtures/v2-golden")
    assert (tmp_path / "chunks.jsonl").read_bytes() == (
        golden / "chunks.jsonl"
    ).read_bytes()
    assert (tmp_path / "boundaries.jsonl").read_bytes() == (
        golden / "boundaries.jsonl"
    ).read_bytes()


def test_v2_preserves_configured_cl100k_hard_cap() -> None:
    units = load_jsonl_units("tests/fixtures/sample.units.jsonl")
    vectors = {units[1].text: [1.0, 0.0], units[3].text: [0.0, 1.0]}
    config = V2Config.from_yaml("configs/v2.yaml")
    counter = TiktokenTokenCounter(config.token_counter.encoding)
    result = V2Chunker(
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


def test_v1_v2_share_raw_features_and_differ_in_candidate_thresholding() -> None:
    shifts = [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.40]
    angles = [0.0]
    for shift in shifts:
        angles.append(angles[-1] + math.acos(1.0 - 2.0 * shift))
    raw_units = [
        RawDocumentUnit.model_validate(
            {
                "document_id": "adaptive",
                "unit_id": f"p-{index}",
                "order": index,
                "text": f"paragraph-{index}",
                "type": "paragraph",
                "section_path": [],
            }
        )
        for index in range(len(angles))
    ]
    vectors = {
        raw.text: [math.cos(angle), math.sin(angle)]
        for raw, angle in zip(raw_units, angles, strict=True)
    }

    v1 = V1Chunker(
        config=small_v1_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=StaticBoundaryEmbedder(vectors),
    ).chunk(raw_units)
    v2 = V2Chunker(
        config=small_v2_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=StaticBoundaryEmbedder(vectors),
    ).chunk(raw_units)

    assert [item.semantic_shift for item in v1.boundaries] == pytest.approx(
        [item.semantic_shift for item in v2.boundaries]
    )
    assert [item.semantic_candidate for item in v1.boundaries] != [
        item.semantic_candidate for item in v2.boundaries
    ]
    assert all(item.fixed_threshold == 0.20 for item in v1.boundaries)
    assert all(item.adaptive_threshold is not None for item in v2.boundaries)
    assert all(chunk.token_count <= 12 for chunk in v2.chunks)


def test_v2_config_rejects_v1_and_future_algorithm_fields() -> None:
    payload = small_v2_config().model_dump(mode="json")
    payload["semantic"]["fixed_threshold"] = 0.20
    with pytest.raises(ValidationError):
        V2Config.model_validate(payload)

    payload = small_v2_config().model_dump(mode="json")
    payload["semantic"]["heading_boost"] = 0.10
    with pytest.raises(ValidationError):
        V2Config.model_validate(payload)


def test_v2_default_config_marks_parameters_as_unoptimized() -> None:
    config = V2Config.from_yaml("configs/v2.yaml")
    assert config.algorithm.tuning_status == "poc_initial_not_optimized"
    assert config.semantic.min_section_boundaries == 20
    assert config.semantic.short_document_fallback_threshold == 0.20


def test_cli_routes_v2_config(monkeypatch, tmp_path: Path) -> None:
    units = load_jsonl_units("tests/fixtures/sample.units.jsonl")
    embedder = StaticBoundaryEmbedder(
        {units[1].text: [1.0, 0.0], units[3].text: [0.0, 1.0]}
    )
    monkeypatch.setattr(
        "amsc.cli.SentenceTransformerBoundaryEmbedder.from_pretrained",
        lambda *args, **kwargs: embedder,
    )
    config_payload = small_v2_config().model_dump(mode="json")
    config_payload["tokens"] = {
        "min_tokens": 2,
        "target_tokens": 50,
        "soft_max_tokens": 80,
        "hard_max_tokens": 100,
    }
    config_payload["boundary_embedding"]["cache_dir"] = str(tmp_path / "cache")
    config_path = tmp_path / "v2.yaml"
    config_path.write_text(
        yaml.safe_dump(config_payload, allow_unicode=True), encoding="utf-8"
    )
    output_path = tmp_path / "output"

    exit_code = main(
        [
            "chunk",
            "--input",
            "tests/fixtures/sample.units.jsonl",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ]
    )
    assert exit_code == 0
    rows = [
        json.loads(line)
        for line in (output_path / "chunks.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert rows[0]["algorithm_version"] == "amsc-v2"
