from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UnitType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"


class SemanticRole(StrEnum):
    """What a heading is, as distinct from what it looks like.

    ``amsc.semantic_roles`` assigns these; the rules and their evidence live
    there. Only the mapping below is schema, because it is the contract every
    consumer of ``section_path`` depends on.
    """

    #: A title that owns the content under it.
    SECTION = "section"
    #: A key partitioning the section it sits in -- a year, an ordinal.
    GROUP = "group"
    #: One of a repeated run of labels, each naming a single list entry.
    ITEM = "item"
    #: Type set for the page rather than for the structure: a standfirst, a
    #: decorative phrase, a banner repeated as page furniture.
    DISPLAY = "display"


#: Looking like a heading and bearing hierarchy are different claims, and this
#: is where the second one is decided. Nothing else may open a section.
ROLE_OPENS_SECTION: dict[SemanticRole, bool] = {
    SemanticRole.SECTION: True,
    SemanticRole.GROUP: True,
    SemanticRole.ITEM: False,
    SemanticRole.DISPLAY: False,
}


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
    #: What this heading *is*, as opposed to what it looks like. Absent on a
    #: corpus extracted before the role pass existed, which is why it is
    #: optional: looking like a heading and bearing hierarchy are different
    #: claims, and only ``opens_section`` decides ``section_path``.
    semantic_role: SemanticRole | None = None
    opens_section: bool | None = None
    section_path: list[str] = Field(default_factory=list)
    source: SourceSpan = Field(default_factory=SourceSpan)

    @model_validator(mode="after")
    def validate_heading_level(self) -> "RawDocumentUnit":
        if self.type == UnitType.HEADING and self.heading_level is None:
            raise ValueError("heading_level is required for heading units")
        if self.type != UnitType.HEADING and self.heading_level is not None:
            raise ValueError("heading_level is only valid for heading units")
        return self

    @model_validator(mode="after")
    def validate_semantic_role(self) -> "RawDocumentUnit":
        if self.type != UnitType.HEADING:
            if self.semantic_role is not None or self.opens_section is not None:
                raise ValueError(
                    "semantic_role and opens_section are only valid for heading units"
                )
            return self
        if (self.semantic_role is None) != (self.opens_section is None):
            raise ValueError(
                "semantic_role and opens_section are recorded together or not at all"
            )
        if self.semantic_role is not None:
            expected = ROLE_OPENS_SECTION[self.semantic_role]
            if self.opens_section != expected:
                raise ValueError(
                    f"{self.semantic_role.value} opens_section is {expected}, "
                    f"not {self.opens_section}"
                )
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


class AdaptiveThresholdProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    scope: list[str]
    threshold_scope_kind: Literal["section", "parent_section", "document"]
    sample_count: int = Field(ge=0)
    method: str
    median: float | None = None
    mad: float | None = None
    robust_scale: float | None = None
    q25: float | None = None
    q75: float | None = None
    q90: float | None = None
    mad_lambda: float | None = None
    low_confidence: bool
    degenerate: bool


class MultiScaleSemanticProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shift_1: float = Field(ge=0.0, le=1.0)
    shift_2: float | None = Field(default=None, ge=0.0, le=1.0)
    shift_3: float | None = Field(default=None, ge=0.0, le=1.0)
    available_scales: list[Literal[1, 2, 3]]
    scale_count: int = Field(ge=1, le=3)
    effective_weight_1: float = Field(gt=0.0, le=1.0)
    effective_weight_2: float | None = Field(default=None, gt=0.0, le=1.0)
    effective_weight_3: float | None = Field(default=None, gt=0.0, le=1.0)
    unit_weighting: Literal["configured_token_counter_sqrt"]
    window_pooling: Literal["weighted_mean_l2_normalized"]
    token_counter_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scale_alignment(self) -> "MultiScaleSemanticProvenance":
        if self.available_scales != sorted(set(self.available_scales)):
            raise ValueError("available_scales must be unique and sorted")
        if not self.available_scales or self.available_scales[0] != 1:
            raise ValueError("scale 1 must be available for every boundary")
        if self.available_scales != list(
            range(1, self.available_scales[-1] + 1)
        ):
            raise ValueError("available_scales must be a contiguous prefix from 1")
        if self.scale_count != len(self.available_scales):
            raise ValueError("scale_count must equal len(available_scales)")

        shifts = {1: self.shift_1, 2: self.shift_2, 3: self.shift_3}
        weights = {
            1: self.effective_weight_1,
            2: self.effective_weight_2,
            3: self.effective_weight_3,
        }
        for scale in (1, 2, 3):
            expected = scale in self.available_scales
            if (shifts[scale] is not None) != expected:
                raise ValueError(
                    f"shift_{scale} availability must match available_scales"
                )
            if (weights[scale] is not None) != expected:
                raise ValueError(
                    f"effective_weight_{scale} availability must match "
                    "available_scales"
                )
        if not math.isclose(
            sum(weight for weight in weights.values() if weight is not None),
            1.0,
            rel_tol=1.0e-9,
            abs_tol=1.0e-9,
        ):
            raise ValueError("effective scale weights must sum to 1.0")
        return self


class StructuralBoundaryProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1)
    mode: Literal["soft"] = "soft"
    evidence_types: list[
        Literal[
            "heading_presence",
            "section_path_transition",
            "table_transition",
            "list_transition",
            "visual_transition",
        ]
    ]
    heading_unit_ids: list[str] = Field(default_factory=list)
    heading_levels: list[int] = Field(default_factory=list)
    left_section_path: list[str] = Field(default_factory=list)
    right_section_path: list[str] = Field(default_factory=list)
    common_section_prefix: list[str] = Field(default_factory=list)
    original_adaptive_threshold: float = Field(ge=0.0, le=1.0)
    effective_threshold: float = Field(ge=0.0, le=1.0)
    configured_max_relaxation: float = Field(ge=0.0, le=1.0)
    applied_relaxation: float = Field(ge=0.0, le=1.0)
    semantic_floor: float = Field(ge=0.0, le=1.0)
    original_semantic_candidate: bool
    effective_semantic_candidate: bool
    structural_assisted_candidate: bool
    boundary_candidate: bool
    adaptive_degenerate: bool

    @model_validator(mode="after")
    def validate_soft_support(self) -> "StructuralBoundaryProvenance":
        if self.effective_threshold > self.original_adaptive_threshold + 1.0e-12:
            raise ValueError("soft structure cannot raise the adaptive threshold")
        expected_relaxation = (
            self.original_adaptive_threshold - self.effective_threshold
        )
        if not math.isclose(
            self.applied_relaxation,
            expected_relaxation,
            rel_tol=1.0e-9,
            abs_tol=1.0e-9,
        ):
            raise ValueError("applied_relaxation must match threshold difference")
        expected_assisted = (
            not self.original_semantic_candidate
            and self.effective_semantic_candidate
            and self.applied_relaxation > 0.0
        )
        if self.structural_assisted_candidate is not expected_assisted:
            raise ValueError("structural_assisted_candidate is inconsistent")
        if self.boundary_candidate is not self.effective_semantic_candidate:
            raise ValueError("soft structure cannot create a non-semantic candidate")
        if self.adaptive_degenerate and self.boundary_candidate:
            raise ValueError("degenerate adaptive evidence cannot create a candidate")
        return self


class MergeDecisionProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(min_length=1)
    focus_chunk_index: int = Field(ge=0)
    left_chunk_index: int = Field(ge=0)
    right_chunk_index: int = Field(ge=0)
    direction: Literal["left", "right"]
    boundary_index: int | None = Field(default=None, ge=0)
    boundary_original_reason: str = Field(min_length=1)
    original_boundary_strength: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    pair_shift: float | None = Field(default=None, ge=0.0, le=1.0)
    original_adaptive_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    semantic_cohesion_passed: bool | None = None
    combined_token_count: int | None = Field(default=None, ge=0)
    hard_cap_passed: bool | None = None
    structural_compatibility: bool | None = None
    accepted: bool
    rejection_reason: str | None = None
    removed_boundary: bool = False

    @model_validator(mode="after")
    def validate_decision(self) -> "MergeDecisionProvenance":
        if self.accepted and self.rejection_reason is not None:
            raise ValueError("accepted merge cannot have a rejection reason")
        if not self.accepted and not self.rejection_reason:
            raise ValueError("rejected merge must have a rejection reason")
        if self.removed_boundary is not self.accepted:
            raise ValueError("removed_boundary must match accepted")
        return self


class AcceptedMergeProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(min_length=1)
    source_chunk_indices: list[int] = Field(min_length=2, max_length=2)
    removed_boundary_index: int = Field(ge=0)
    direction: Literal["left", "right"]
    pre_merge_token_counts: list[int] = Field(min_length=2, max_length=2)
    post_merge_token_count: int = Field(ge=0)
    pair_shift: float = Field(ge=0.0, le=1.0)
    original_adaptive_threshold: float = Field(ge=0.0, le=1.0)
    original_boundary_strength: float = Field(ge=0.0, le=1.0)
    removed_by_v4_semantic_safe_merge: Literal[True] = True


class AtomicSplitProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_unit_id: str = Field(min_length=1)
    atomic_kind: Literal["table", "list", "visual"]
    fragment_unit_id: str = Field(min_length=1)
    fragment_index: int = Field(ge=1)
    fragment_count: int = Field(ge=2)
    reason: Literal["configured_token_counter_hard_split"]
    policy: Literal[
        "preserve_atomic_unless_configured_hard_cap_forces_split"
    ] = "preserve_atomic_unless_configured_hard_cap_forces_split"
    token_counter_id: str = Field(min_length=1)
    configured_hard_max_tokens: int = Field(ge=1)


class BoundaryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    boundary_index: int
    left_unit_id: str
    right_unit_id: str
    cosine_similarity: float
    semantic_shift: float
    fixed_threshold: float | None = None
    adaptive_threshold: AdaptiveThresholdProvenance | None = None
    multi_scale: MultiScaleSemanticProvenance | None = None
    semantic_candidate: bool
    candidate_chunk_tokens: int | None = None
    target_distance: float | None = None
    selection_score: float | None = None
    selected_reason: str | None = None
    structural: StructuralBoundaryProvenance | None = None
    original_boundary_strength: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    effective_boundary_strength: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    selection_signal: float | None = Field(default=None, ge=0.0, le=1.0)
    selection_strategy: Literal["raw_semantic_shift", "threshold_relative"] | None = (
        None
    )
    merge_decisions: list[MergeDecisionProvenance] | None = None


class ChunkBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    boundary_index: int | None = None
    left_unit_id: str | None = None
    right_unit_id: str | None = None
    cosine_similarity: float | None = None
    semantic_shift: float | None = None
    fixed_threshold: float | None = None
    adaptive_threshold: AdaptiveThresholdProvenance | None = None
    multi_scale: MultiScaleSemanticProvenance | None = None
    semantic_candidate: bool | None = None
    selection_score: float | None = None
    structural: StructuralBoundaryProvenance | None = None
    original_boundary_strength: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    effective_boundary_strength: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    selection_signal: float | None = Field(default=None, ge=0.0, le=1.0)
    selection_strategy: Literal["raw_semantic_shift", "threshold_relative"] | None = (
        None
    )


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
    ablation_id: Literal["a1", "a2", "a3", "a4"] | None = None
    merge_decisions: list[MergeDecisionProvenance] | None = None
    accepted_merge: AcceptedMergeProvenance | None = None
    atomic_splits: list[AtomicSplitProvenance] | None = None


class ChunkingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    chunks: list[Chunk]
    boundaries: list[BoundaryEvidence]
    algorithm_version: str = "amsc-v1"
    parameter_status: str = "poc_initial_not_optimized"
    ablation_id: Literal["a1", "a2", "a3", "a4"] | None = None


@dataclass
class SelectedSegment:
    start: int
    end: int
    end_boundary: ChunkBoundary
    selected_evidence: BoundaryEvidence | None = None
    unmerged_short_tail_reason: str | None = None
    tail_coalesced: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
