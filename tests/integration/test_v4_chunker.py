from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pytest
import yaml
from pydantic import ValidationError

from amsc.cli import main
from amsc.config import V4Config
from amsc.io import write_chunking_result
from amsc.models import (
    EmbeddingBatch,
    RawDocumentUnit,
    SemanticEmbeddingProvenance,
)
from amsc.v4_chunker import V4Chunker, V4Composition
from conftest import WordTokenCounter


class DeterministicEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    model_id = "test:v4-deterministic@1"
    prefix_policy = "symmetric_query"
    model_input_limit = 512
    cache_namespace = "semantic-boundary|test-v4|query|512|v1"

    def embed_units(self, texts: Sequence[str]) -> EmbeddingBatch:
        self.calls.append(list(texts))
        vectors = []
        for text in texts:
            checksum = sum(ord(character) for character in text)
            vectors.append([1.0, 0.1 + (checksum % 17) / 20.0])
        provenance = tuple(
            SemanticEmbeddingProvenance(
                model_id=self.model_id,
                prefix_policy=self.prefix_policy,
                prefix="query: ",
                model_input_limit=self.model_input_limit,
                semantic_fragment_count=1,
                semantic_pooling="token_weighted_mean",
            )
            for _ in texts
        )
        return EmbeddingBatch(
            vectors=np.asarray(vectors, dtype=np.float32),
            provenance=provenance,
        )


def _config(
    *,
    composition: str = "a4",
    hard_max: int = 10,
) -> V4Config:
    payload = V4Config.from_yaml("configs/v4.yaml").model_dump(mode="python")
    payload["algorithm"]["version"] = "v4"
    payload["boundary_embedding"]["model"] = "test"
    payload["tokens"] = {
        "min_tokens": 2,
        "target_tokens": 5,
        "soft_max_tokens": min(8, hard_max),
        "hard_max_tokens": hard_max,
    }
    payload["ablation"]["composition"] = composition
    return V4Config.model_validate(payload)


def _paragraphs(count: int) -> list[RawDocumentUnit]:
    return [
        RawDocumentUnit.model_validate(
            {
                "document_id": "v4",
                "unit_id": f"p-{index}",
                "order": index,
                "text": f"topic word {index}",
                "type": "paragraph",
                "section_path": ["Root"],
                "source": {"page": 1, "block": index + 1},
            }
        )
        for index in range(count)
    ]


def test_v4_compositions_are_explicit_and_non_overlapping() -> None:
    assert V4Composition.from_id("a1") == V4Composition(
        "a1", False, True, False
    )
    assert V4Composition.from_id("a2") == V4Composition(
        "a2", True, False, False
    )
    assert V4Composition.from_id("a3") == V4Composition(
        "a3", False, False, True
    )
    assert V4Composition.from_id("a4") == V4Composition(
        "a4", True, True, True
    )


def test_v4_retains_embeddings_for_merge_without_reembedding() -> None:
    embedder = DeterministicEmbedder()
    result = V4Chunker(
        config=_config(composition="a4"),
        token_counter=WordTokenCounter(),
        boundary_embedder=embedder,
    ).chunk(_paragraphs(8))

    assert len(embedder.calls) == 1
    assert embedder.calls[0] == [f"topic word {index}" for index in range(8)]
    assert result.algorithm_version == "amsc-v4"
    assert result.ablation_id == "a4"
    assert all(chunk.ablation_id == "a4" for chunk in result.chunks)


def test_atomic_table_list_and_visual_forced_splits_have_provenance() -> None:
    long_text = " ".join(f"token-{index}" for index in range(13))
    units = [
        RawDocumentUnit.model_validate(
            {
                "document_id": "atomic",
                "unit_id": "t-1",
                "order": 1,
                "text": long_text,
                "type": "table",
            }
        ),
        RawDocumentUnit.model_validate(
            {
                "document_id": "atomic",
                "unit_id": "l-2",
                "order": 2,
                "text": long_text,
                "type": "list",
            }
        ),
        RawDocumentUnit.model_validate(
            {
                "document_id": "atomic",
                "unit_id": "v-3",
                "order": 3,
                "text": long_text,
                "type": "paragraph",
                "source": {"content_origin": "visual"},
            }
        ),
    ]
    config = _config(composition="a1", hard_max=6).model_copy(
        update={
            "tokens": _config(composition="a1", hard_max=6).tokens.model_copy(
                update={"min_tokens": 1, "target_tokens": 3, "soft_max_tokens": 5}
            )
        }
    )
    result = V4Chunker(
        config=config,
        token_counter=WordTokenCounter(),
        boundary_embedder=DeterministicEmbedder(),
    ).chunk(units)

    provenance = [
        split
        for chunk in result.chunks
        for split in chunk.atomic_splits or []
    ]
    assert {item.atomic_kind for item in provenance} == {
        "table",
        "list",
        "visual",
    }
    assert all(item.fragment_count == 3 for item in provenance)
    assert all(chunk.token_count <= 6 for chunk in result.chunks)


def test_v4_config_is_strict_and_contextualization_remains_unimplemented() -> None:
    payload = V4Config.from_yaml("configs/v4.yaml").model_dump(mode="python")
    payload["structure"]["protected_heading_levels"] = [1, 2]
    with pytest.raises(ValidationError):
        V4Config.model_validate(payload)

    payload = V4Config.from_yaml("configs/v4.yaml").model_dump(mode="python")
    payload["contextualization"]["enabled"] = True
    with pytest.raises(ValidationError):
        V4Config.model_validate(payload)

    payload = V4Config.from_yaml("configs/v4.yaml").model_dump(mode="python")
    payload["selection"]["semantic_weight"] = 0.70
    with pytest.raises(ValidationError, match="sum to 1.0"):
        V4Config.model_validate(payload)


def test_ablation_composition_changes_config_hash() -> None:
    hashes = {_config(composition=value).config_hash for value in ("a1", "a2", "a3", "a4")}
    assert len(hashes) == 4


def test_v4_persisted_jsonl_is_deterministic(tmp_path: Path) -> None:
    units = _paragraphs(8)
    config = _config(composition="a4")
    first = V4Chunker(
        config=config,
        token_counter=WordTokenCounter(),
        boundary_embedder=DeterministicEmbedder(),
    ).chunk(units)
    second = V4Chunker(
        config=config,
        token_counter=WordTokenCounter(),
        boundary_embedder=DeterministicEmbedder(),
    ).chunk(units)
    first_path = tmp_path / "first"
    second_path = tmp_path / "second"
    write_chunking_result(first, first_path)
    write_chunking_result(second, second_path)

    assert (first_path / "chunks.jsonl").read_bytes() == (
        second_path / "chunks.jsonl"
    ).read_bytes()
    assert (first_path / "boundaries.jsonl").read_bytes() == (
        second_path / "boundaries.jsonl"
    ).read_bytes()


def test_cli_routes_v4_and_ablation_override(monkeypatch, tmp_path: Path) -> None:
    embedder = DeterministicEmbedder()
    monkeypatch.setattr(
        "amsc.cli.SentenceTransformerBoundaryEmbedder.from_pretrained",
        lambda *args, **kwargs: embedder,
    )
    units_path = tmp_path / "units.jsonl"
    units_path.write_text(
        "\n".join(
            unit.model_dump_json(exclude_none=True) for unit in _paragraphs(8)
        )
        + "\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "v4.yaml"
    config_path.write_text(
        yaml.safe_dump(
            _config(composition="a4").model_dump(mode="json"),
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "out"

    assert main(
        [
            "chunk",
            "--input",
            str(units_path),
            "--config",
            str(config_path),
            "--output",
            str(output),
            "--ablation",
            "a1",
        ]
    ) == 0
    chunk = json.loads(
        (output / "chunks.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    resolved = json.loads(
        (output / "resolved-config.json").read_text(encoding="utf-8")
    )
    assert chunk["algorithm_version"] == "amsc-v4"
    assert chunk["ablation_id"] == "a1"
    assert resolved["ablation"]["composition"] == "a1"
