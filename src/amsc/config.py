from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AlgorithmConfig(StrictConfigModel):
    version: Literal["v1"] = "v1"
    tuning_status: Literal["poc_initial_not_optimized"] = (
        "poc_initial_not_optimized"
    )


class TokenCounterConfig(StrictConfigModel):
    provider: Literal["tiktoken"] = "tiktoken"
    encoding: str = "cl100k_base"
    cap_semantics: Literal["configured_poc_counter_only"] = (
        "configured_poc_counter_only"
    )


class BoundaryEmbeddingConfig(StrictConfigModel):
    model: str = "intfloat/multilingual-e5-base"
    revision: str | None = None
    device: str = "auto"
    prefix_policy: Literal["symmetric_query"] = "symmetric_query"
    prefix: str = "query: "
    max_input_tokens_override: int | None = Field(default=None, ge=8)
    overlength_strategy: Literal[
        "sentence_fragment_token_weighted_pooling"
    ] = "sentence_fragment_token_weighted_pooling"
    normalize_embeddings: bool = True
    cache_dir: Path = Path(".cache/boundary-embeddings")


class SemanticConfig(StrictConfigModel):
    fixed_threshold: float = Field(default=0.20, ge=0.0, le=1.0)


class TokenLimitsConfig(StrictConfigModel):
    min_tokens: int = Field(default=160, ge=1)
    target_tokens: int = Field(default=700, ge=1)
    soft_max_tokens: int = Field(default=900, ge=1)
    hard_max_tokens: int = Field(default=1126, ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> "TokenLimitsConfig":
        if not (
            self.min_tokens
            < self.target_tokens
            < self.soft_max_tokens
            <= self.hard_max_tokens
        ):
            raise ValueError(
                "token limits must satisfy min < target < soft_max <= hard_max"
            )
        return self


class SelectionConfig(StrictConfigModel):
    semantic_weight: float = Field(default=0.80, ge=0.0)
    size_weight: float = Field(default=0.20, ge=0.0)

    @model_validator(mode="after")
    def validate_weights(self) -> "SelectionConfig":
        if self.semantic_weight + self.size_weight <= 0:
            raise ValueError("at least one selection weight must be positive")
        return self


class V1Config(StrictConfigModel):
    algorithm: AlgorithmConfig = AlgorithmConfig()
    token_counter: TokenCounterConfig = TokenCounterConfig()
    boundary_embedding: BoundaryEmbeddingConfig = BoundaryEmbeddingConfig()
    semantic: SemanticConfig = SemanticConfig()
    tokens: TokenLimitsConfig = TokenLimitsConfig()
    selection: SelectionConfig = SelectionConfig()

    @classmethod
    def from_yaml(cls, path: str | Path) -> "V1Config":
        with Path(path).open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        return cls.model_validate(data)

    @property
    def config_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

