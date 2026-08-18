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


class V2AlgorithmConfig(StrictConfigModel):
    version: Literal["v2"] = "v2"
    tuning_status: Literal["poc_initial_not_optimized"] = (
        "poc_initial_not_optimized"
    )


class V3AlgorithmConfig(StrictConfigModel):
    version: Literal["v3"] = "v3"
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


class AdaptiveSemanticConfig(StrictConfigModel):
    strategy: Literal["hierarchical_adaptive"] = "hierarchical_adaptive"
    mad_lambda: float = Field(default=1.5, ge=0.0)
    quantile_floor: float = Field(default=0.75, ge=0.0, le=1.0)
    quantile_ceiling: float = Field(default=0.90, ge=0.0, le=1.0)
    min_section_boundaries: int = Field(default=20, ge=1)
    min_document_boundaries: int = Field(default=8, ge=1)
    short_document_fallback_threshold: float = Field(
        default=0.20, ge=0.0, le=1.0
    )
    dispersion_epsilon: float = Field(default=1.0e-8, gt=0.0)

    @model_validator(mode="after")
    def validate_quantile_order(self) -> "AdaptiveSemanticConfig":
        if self.quantile_floor > self.quantile_ceiling:
            raise ValueError("quantile_floor must be <= quantile_ceiling")
        return self


class MultiScaleConfig(StrictConfigModel):
    shift_1_weight: float = Field(gt=0.0)
    shift_2_weight: float = Field(gt=0.0)
    shift_3_weight: float = Field(gt=0.0)
    unit_weighting: Literal["configured_token_counter_sqrt"]
    window_pooling: Literal["weighted_mean_l2_normalized"]
    edge_policy: Literal["full_symmetric_available_scales"]

    @property
    def shift_weights(self) -> dict[int, float]:
        return {
            1: self.shift_1_weight,
            2: self.shift_2_weight,
            3: self.shift_3_weight,
        }


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


class V2Config(StrictConfigModel):
    algorithm: V2AlgorithmConfig = V2AlgorithmConfig()
    token_counter: TokenCounterConfig = TokenCounterConfig()
    boundary_embedding: BoundaryEmbeddingConfig = BoundaryEmbeddingConfig()
    semantic: AdaptiveSemanticConfig = AdaptiveSemanticConfig()
    tokens: TokenLimitsConfig = TokenLimitsConfig()
    selection: SelectionConfig = SelectionConfig()

    @classmethod
    def from_yaml(cls, path: str | Path) -> "V2Config":
        with Path(path).open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        return cls.model_validate(data)

    @property
    def config_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class V3Config(StrictConfigModel):
    algorithm: V3AlgorithmConfig = V3AlgorithmConfig()
    token_counter: TokenCounterConfig = TokenCounterConfig()
    boundary_embedding: BoundaryEmbeddingConfig = BoundaryEmbeddingConfig()
    semantic: AdaptiveSemanticConfig = AdaptiveSemanticConfig()
    multi_scale: MultiScaleConfig
    tokens: TokenLimitsConfig = TokenLimitsConfig()
    selection: SelectionConfig = SelectionConfig()

    @classmethod
    def from_yaml(cls, path: str | Path) -> "V3Config":
        with Path(path).open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        return cls.model_validate(data)

    @property
    def config_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def load_config(path: str | Path) -> V1Config | V2Config | V3Config:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    version = (data or {}).get("algorithm", {}).get("version")
    if version == "v1":
        return V1Config.model_validate(data)
    if version == "v2":
        return V2Config.model_validate(data)
    if version == "v3":
        return V3Config.model_validate(data)
    raise ValueError(f"Unsupported algorithm.version: {version!r}")
