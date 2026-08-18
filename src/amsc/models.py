from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UnitType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"


class SourceSpan(BaseModel):
    model_config = ConfigDict(extra="allow")

    page: int | None = Field(default=None, ge=1)
    block: int | str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_character_range(self) -> "SourceSpan":
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ValueError("char_end must be greater than or equal to char_start")
        return self


class RawDocumentUnit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    document_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1)
    order: int = Field(ge=0)
    text: str = Field(min_length=1)
    type: UnitType
    heading_level: int | None = Field(default=None, ge=1, le=6)
    section_path: list[str] = Field(default_factory=list)
    source: SourceSpan = Field(default_factory=SourceSpan)

    @model_validator(mode="after")
    def validate_heading_level(self) -> "RawDocumentUnit":
        if self.type == UnitType.HEADING and self.heading_level is None:
            raise ValueError("heading_level is required for heading units")
        if self.type != UnitType.HEADING and self.heading_level is not None:
            raise ValueError("heading_level is only valid for heading units")
        return self


@dataclass(frozen=True)
class HeadingAttachment:
    unit_id: str
    text: str
    heading_level: int
    source: SourceSpan


@dataclass(frozen=True)
class ContentUnit:
    document_id: str
    unit_id: str
    source_unit_id: str
    order: int
    text: str
    type: UnitType
    section_path: tuple[str, ...]
    source: SourceSpan
    leading_headings: tuple[HeadingAttachment, ...] = ()
    fragment_index: int = 0
    fragment_count: int = 1
    forced_split_reason: str | None = None
    semantic_text: str | None = None

    @property
    def heading_text(self) -> str:
        return "\n".join(heading.text for heading in self.leading_headings)

    @property
    def rendered_text(self) -> str:
        if self.heading_text and self.text:
            return f"{self.heading_text}\n\n{self.text}"
        return self.heading_text or self.text

    @property
    def text_for_embedding(self) -> str | None:
        if self.semantic_text is not None:
            return self.semantic_text
        if self.type == UnitType.HEADING:
            return None
        return self.text

    @property
    def raw_unit_ids(self) -> tuple[str, ...]:
        if self.type == UnitType.HEADING and self.leading_headings and not self.text:
            return tuple(heading.unit_id for heading in self.leading_headings)
        return tuple(heading.unit_id for heading in self.leading_headings) + (
            self.source_unit_id,
        )

    @property
    def source_spans(self) -> tuple[SourceSpan, ...]:
        if self.type == UnitType.HEADING and self.leading_headings and not self.text:
            return tuple(heading.source for heading in self.leading_headings)
        return tuple(heading.source for heading in self.leading_headings) + (self.source,)


@dataclass(frozen=True)
class SemanticEmbeddingProvenance:
    model_id: str
    prefix_policy: str
    prefix: str
    model_input_limit: int
    semantic_fragment_count: int
    semantic_pooling: str
    cache_hit: bool = False


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: Any
    provenance: tuple[SemanticEmbeddingProvenance, ...]


class BoundaryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    boundary_index: int
    left_unit_id: str
    right_unit_id: str
    cosine_similarity: float
    semantic_shift: float
    fixed_threshold: float
    semantic_candidate: bool
    candidate_chunk_tokens: int | None = None
    target_distance: float | None = None
    selection_score: float | None = None
    selected_reason: str | None = None


class ChunkBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    boundary_index: int | None = None
    left_unit_id: str | None = None
    right_unit_id: str | None = None
    cosine_similarity: float | None = None
    semantic_shift: float | None = None
    fixed_threshold: float | None = None
    selection_score: float | None = None


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    text: str
    token_count: int
    unit_ids: list[str]
    content_unit_ids: list[str]
    section_paths: list[list[str]]
    source_spans: list[dict[str, Any]]
    start_boundary: ChunkBoundary
    end_boundary: ChunkBoundary
    unmerged_short_tail_reason: str | None = None
    tail_coalesced: bool = False
    removed_tail_boundary_reason: str | None = None
    semantic_embeddings: list[dict[str, Any]]
    algorithm_version: str
    boundary_embedding_model: str
    boundary_prefix_policy: str
    boundary_model_input_limit: int
    token_counter_id: str
    hard_cap_semantics: str
    config_hash: str


class ChunkingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    chunks: list[Chunk]
    boundaries: list[BoundaryEvidence]
    algorithm_version: str = "amsc-v1"
    parameter_status: str = "poc_initial_not_optimized"


@dataclass
class SelectedSegment:
    start: int
    end: int
    end_boundary: ChunkBoundary
    selected_evidence: BoundaryEvidence | None = None
    unmerged_short_tail_reason: str | None = None
    tail_coalesced: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
