from __future__ import annotations

import json

from amsc.chunker import V1Chunker
from amsc.config import V1Config
from amsc.io import load_jsonl_units, write_chunking_result
from amsc.tokenization import TiktokenTokenCounter
from conftest import StaticBoundaryEmbedder, WordTokenCounter


def small_config() -> V1Config:
    return V1Config.model_validate(
        {
            "algorithm": {
                "version": "v1",
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
                "cache_dir": ".cache/test",
            },
            "semantic": {"fixed_threshold": 0.2},
            "tokens": {
                "min_tokens": 2,
                "target_tokens": 7,
                "soft_max_tokens": 10,
                "hard_max_tokens": 12,
            },
            "selection": {"semantic_weight": 0.8, "size_weight": 0.2},
        }
    )


def test_end_to_end_provenance_and_configured_cap(tmp_path) -> None:
    units = load_jsonl_units("tests/fixtures/sample.units.jsonl")
    embedder = StaticBoundaryEmbedder(
        {
            "Net kâr ve aktif büyüklüğü arttı.": [1.0, 0.0],
            "Çalışan eğitimleri yıl boyunca sürdü.": [0.0, 1.0],
        }
    )
    result = V1Chunker(
        config=small_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=embedder,
    ).chunk(units)

    assert embedder.calls == [
        [
            "Net kâr ve aktif büyüklüğü arttı.",
            "Çalışan eğitimleri yıl boyunca sürdü.",
        ]
    ]
    assert len(result.chunks) == 2
    assert result.chunks[0].text.startswith("Finansal Sonuçlar\n\n")
    assert result.chunks[1].text.startswith("İnsan Kaynakları\n\n")
    assert all(chunk.token_count <= 12 for chunk in result.chunks)
    assert all(
        chunk.hard_cap_semantics == "configured_poc_counter_only"
        for chunk in result.chunks
    )
    assert result.chunks[0].end_boundary.reason == "fixed_semantic_boundary"
    assert result.chunks[0].semantic_embeddings[0]["prefix"] == "query: "

    write_chunking_result(result, tmp_path)
    rows = [
        json.loads(line)
        for line in (tmp_path / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["token_counter_id"] == "test:whitespace@1"
    assert rows[0]["unit_ids"] == ["h-1", "p-1"]


def test_long_heading_and_content_never_exceed_configured_cap() -> None:
    from amsc.models import RawDocumentUnit

    raw = [
        RawDocumentUnit.model_validate(
            {
                "document_id": "long",
                "unit_id": "h",
                "order": 1,
                "text": "one two three",
                "type": "heading",
                "heading_level": 1,
            }
        ),
        RawDocumentUnit.model_validate(
            {
                "document_id": "long",
                "unit_id": "p",
                "order": 2,
                "text": " ".join(f"w{i}" for i in range(30)),
                "type": "paragraph",
            }
        ),
    ]
    split_texts = [" ".join(f"w{i}" for i in range(start, min(start + 9, 30))) for start in range(0, 30, 9)]
    embedder = StaticBoundaryEmbedder(
        {text: [1.0, float(index + 1)] for index, text in enumerate(split_texts)}
    )
    result = V1Chunker(
        config=small_config(),
        token_counter=WordTokenCounter(),
        boundary_embedder=embedder,
    ).chunk(raw)
    assert all(chunk.token_count <= 12 for chunk in result.chunks)


def test_configured_cl100k_cap_and_deterministic_output() -> None:
    units = load_jsonl_units("tests/fixtures/sample.units.jsonl")
    vectors = {
        "Net kâr ve aktif büyüklüğü arttı.": [1.0, 0.0],
        "Çalışan eğitimleri yıl boyunca sürdü.": [0.0, 1.0],
    }
    config = V1Config.from_yaml("configs/v1.yaml")
    counter = TiktokenTokenCounter(config.token_counter.encoding)

    first = V1Chunker(
        config=config,
        token_counter=counter,
        boundary_embedder=StaticBoundaryEmbedder(vectors),
    ).chunk(units)
    second = V1Chunker(
        config=config,
        token_counter=counter,
        boundary_embedder=StaticBoundaryEmbedder(vectors),
    ).chunk(units)

    assert first.model_dump_json() == second.model_dump_json()
    assert all(
        counter.count(chunk.text) <= config.tokens.hard_max_tokens
        for chunk in first.chunks
    )
    assert all(
        chunk.hard_cap_semantics == "configured_poc_counter_only"
        for chunk in first.chunks
    )
