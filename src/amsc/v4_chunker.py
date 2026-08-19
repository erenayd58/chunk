from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

import numpy as np

from .config import V4Config
from .embeddings import SemanticBoundaryEmbedder
from .features import MultiScaleSemanticFeatureExtractor
from .merge import SemanticSafeMergeResolver, V4ChunkDraft
from .models import (
    AtomicSplitProvenance,
    BoundaryEvidence,
    Chunk,
    ChunkBoundary,
    ChunkingResult,
    ContentUnit,
    RawDocumentUnit,
    SemanticEmbeddingProvenance,
    UnitType,
)
from .selection import V2TailResolver
from .strength import (
    DualBoundaryStrengthAnnotator,
    EffectiveThresholdRelativeSelectionScorer,
    RawSemanticShiftSelectionScorer,
)
from .structure import SoftStructureSupportPolicy
from .thresholds import HierarchicalAdaptiveThresholdEstimator
from .tokenization import TokenCounter
from .units import HeadingAttachmentBuilder, RenderedTokenBudgeter, render_units
from .v4_selection import V4IntervalBoundarySelector


@dataclass(frozen=True)
class V4Composition:
    composition_id: str
    structure_enabled: bool
    threshold_relative_selector: bool
    merge_enabled: bool

    @classmethod
    def from_id(cls, composition_id: str) -> "V4Composition":
        combinations = {
            "a1": cls("a1", False, True, False),
            "a2": cls("a2", True, False, False),
            "a3": cls("a3", False, False, True),
            "a4": cls("a4", True, True, True),
        }
        try:
            return combinations[composition_id]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported V4 ablation composition: {composition_id!r}"
            ) from exc


@dataclass(frozen=True)
class _SemanticRun:
    start: int
    end: int
    units: tuple[ContentUnit, ...]
    raw_boundaries: tuple[BoundaryEvidence, ...]


class V4Chunker:
    algorithm_version = "amsc-v4"

    def __init__(
        self,
        *,
        config: V4Config,
        token_counter: TokenCounter,
        boundary_embedder: SemanticBoundaryEmbedder,
    ) -> None:
        self.config = config
        self.token_counter = token_counter
        self.boundary_embedder = boundary_embedder
        self.composition = V4Composition.from_id(
            config.ablation.composition
        )
        self.budgeter = RenderedTokenBudgeter(
            token_counter=token_counter,
            hard_max_tokens=config.tokens.hard_max_tokens,
        )
        self.unit_builder = HeadingAttachmentBuilder(self.budgeter)
        self.feature_extractor = MultiScaleSemanticFeatureExtractor(
            config.multi_scale, token_counter
        )
        self.threshold_estimator = HierarchicalAdaptiveThresholdEstimator(
            config.semantic
        )
        self.structure_policy = SoftStructureSupportPolicy(config.structure)
        self.strength_annotator = DualBoundaryStrengthAnnotator(
            epsilon=config.selection.strength_epsilon
        )
        selection_scorer = (
            EffectiveThresholdRelativeSelectionScorer()
            if self.composition.threshold_relative_selector
            else RawSemanticShiftSelectionScorer()
        )
        self.selector = V4IntervalBoundarySelector(
            budgeter=self.budgeter,
            token_limits=config.tokens,
            selection=config.selection,
            scorer=selection_scorer,
            tail_resolver=V2TailResolver(self.budgeter, config.tokens),
        )
        merge_config = config.merge.model_copy(
            update={
                "enabled": (
                    config.merge.enabled and self.composition.merge_enabled
                )
            }
        )
        self.merge_resolver = SemanticSafeMergeResolver(
            config=merge_config,
            token_limits=config.tokens,
            token_counter=token_counter,
            budgeter=self.budgeter,
        )

    def chunk(self, raw_units: Sequence[RawDocumentUnit]) -> ChunkingResult:
        if not raw_units:
            raise ValueError("At least one raw unit is required")
        prepared = self.unit_builder.build(raw_units)
        if not prepared:
            raise ValueError("Document produced no prepared units")

        (
            runs,
            raw_boundaries,
            provenance_by_unit,
            retained_embeddings,
        ) = self._embed_and_extract(prepared)
        units_by_id = {unit.unit_id: unit for unit in prepared}
        resolved_boundaries = self.threshold_estimator.apply(
            raw_boundaries, units_by_id
        )
        if self.composition.structure_enabled and self.config.structure.enabled:
            resolved_boundaries = self.structure_policy.apply(
                resolved_boundaries, units_by_id
            )
        resolved_boundaries = self.strength_annotator.apply(
            resolved_boundaries
        )
        resolved_by_index = {
            boundary.boundary_index: boundary
            for boundary in resolved_boundaries
        }

        drafts: list[V4ChunkDraft] = []
        all_boundaries: list[BoundaryEvidence] = []
        run_by_start = {run.start: run for run in runs}
        cursor = 0
        while cursor < len(prepared):
            run = run_by_start.get(cursor)
            if run is None:
                unit = prepared[cursor]
                drafts.append(
                    V4ChunkDraft(
                        units=[unit],
                        end_boundary=ChunkBoundary(
                            reason=unit.forced_split_reason
                            or "nonsemantic_heading_boundary"
                        ),
                        original_chunk_indices=(len(drafts),),
                    )
                )
                cursor += 1
                continue

            boundaries = [
                resolved_by_index[boundary.boundary_index]
                for boundary in run.raw_boundaries
            ]
            segments, updated = self.selector.select(run.units, boundaries)
            all_boundaries.extend(updated)
            for segment in segments:
                drafts.append(
                    V4ChunkDraft(
                        units=list(run.units[segment.start : segment.end]),
                        end_boundary=segment.end_boundary,
                        original_chunk_indices=(len(drafts),),
                        unmerged_short_tail_reason=(
                            segment.unmerged_short_tail_reason
                        ),
                        tail_coalesced=segment.tail_coalesced,
                        removed_tail_boundary_reason=segment.metadata.get(
                            "removed_tail_boundary_reason"
                        ),
                    )
                )
            cursor = run.end

        for draft in drafts[:-1]:
            if draft.end_boundary.reason == "document_end":
                draft.end_boundary = ChunkBoundary(
                    reason="nonsemantic_forced_boundary"
                )
        if drafts:
            drafts[-1].end_boundary = ChunkBoundary(reason="document_end")

        drafts, all_boundaries = self.merge_resolver.resolve(
            drafts, all_boundaries, retained_embeddings
        )
        return self._materialize(
            document_id=raw_units[0].document_id,
            drafts=drafts,
            boundaries=all_boundaries,
            provenance_by_unit=provenance_by_unit,
        )

    def _embed_and_extract(
        self, prepared: Sequence[ContentUnit]
    ) -> tuple[
        list[_SemanticRun],
        list[BoundaryEvidence],
        dict[str, SemanticEmbeddingProvenance],
        dict[str, np.ndarray],
    ]:
        runs: list[_SemanticRun] = []
        all_boundaries: list[BoundaryEvidence] = []
        provenance_by_unit: dict[str, SemanticEmbeddingProvenance] = {}
        retained_embeddings: dict[str, np.ndarray] = {}
        boundary_offset = 0
        cursor = 0
        while cursor < len(prepared):
            if prepared[cursor].text_for_embedding is None:
                cursor += 1
                continue
            run_end = cursor
            while (
                run_end < len(prepared)
                and prepared[run_end].text_for_embedding is not None
            ):
                run_end += 1
            run_units = tuple(prepared[cursor:run_end])
            texts = [unit.text_for_embedding or "" for unit in run_units]
            batch = self.boundary_embedder.embed_units(texts)
            vectors = np.asarray(batch.vectors, dtype=np.float64)
            if vectors.ndim != 2 or vectors.shape[0] != len(run_units):
                raise ValueError("Embedding count must match semantic run units")
            for index, (unit, provenance) in enumerate(
                zip(run_units, batch.provenance, strict=True)
            ):
                provenance_by_unit[unit.unit_id] = provenance
                retained_embeddings[unit.unit_id] = vectors[index].copy()

            boundaries = self.feature_extractor.compute_raw(
                run_units,
                batch,
                boundary_index_offset=boundary_offset,
            )
            runs.append(
                _SemanticRun(
                    start=cursor,
                    end=run_end,
                    units=run_units,
                    raw_boundaries=tuple(boundaries),
                )
            )
            all_boundaries.extend(boundaries)
            boundary_offset += len(boundaries)
            cursor = run_end
        return (
            runs,
            all_boundaries,
            provenance_by_unit,
            retained_embeddings,
        )

    def _materialize(
        self,
        *,
        document_id: str,
        drafts: Sequence[V4ChunkDraft],
        boundaries: list[BoundaryEvidence],
        provenance_by_unit: dict[str, SemanticEmbeddingProvenance],
    ) -> ChunkingResult:
        chunks: list[Chunk] = []
        start_boundary = ChunkBoundary(reason="document_start")
        for index, draft in enumerate(drafts, start=1):
            text = render_units(draft.units)
            token_count = self.token_counter.count(text)
            if token_count > self.config.tokens.hard_max_tokens:
                raise AssertionError(
                    f"Chunk {index} exceeds configured PoC counter hard cap: "
                    f"{token_count} > {self.config.tokens.hard_max_tokens}"
                )
            semantic_provenance = [
                {
                    "unit_id": unit.unit_id,
                    **asdict(provenance_by_unit[unit.unit_id]),
                }
                for unit in draft.units
                if unit.unit_id in provenance_by_unit
            ]
            atomic_splits = self._atomic_split_provenance(draft.units)
            chunks.append(
                Chunk(
                    chunk_id=f"{document_id}:chunk-{index:04d}",
                    document_id=document_id,
                    text=text,
                    token_count=token_count,
                    unit_ids=self._unique(
                        unit_id
                        for unit in draft.units
                        for unit_id in unit.raw_unit_ids
                    ),
                    content_unit_ids=[unit.unit_id for unit in draft.units],
                    section_paths=self._unique_lists(
                        list(unit.section_path)
                        for unit in draft.units
                        if unit.section_path
                    ),
                    source_spans=self._unique_dicts(
                        span.model_dump(exclude_none=True)
                        for unit in draft.units
                        for span in unit.source_spans
                    ),
                    start_boundary=start_boundary,
                    end_boundary=draft.end_boundary,
                    unmerged_short_tail_reason=(
                        draft.unmerged_short_tail_reason
                    ),
                    tail_coalesced=draft.tail_coalesced,
                    removed_tail_boundary_reason=(
                        draft.removed_tail_boundary_reason
                    ),
                    semantic_embeddings=semantic_provenance,
                    algorithm_version=self.algorithm_version,
                    boundary_embedding_model=self.boundary_embedder.model_id,
                    boundary_prefix_policy=self.boundary_embedder.prefix_policy,
                    boundary_model_input_limit=(
                        self.boundary_embedder.model_input_limit
                    ),
                    token_counter_id=self.token_counter.counter_id,
                    hard_cap_semantics=self.config.token_counter.cap_semantics,
                    config_hash=self.config.config_hash,
                    ablation_id=self.config.ablation.composition,
                    merge_decisions=(draft.merge_decisions or None),
                    accepted_merge=draft.accepted_merge,
                    atomic_splits=(atomic_splits or None),
                )
            )
            start_boundary = draft.end_boundary

        return ChunkingResult(
            document_id=document_id,
            chunks=chunks,
            boundaries=boundaries,
            algorithm_version=self.algorithm_version,
            parameter_status=self.config.algorithm.tuning_status,
            ablation_id=self.config.ablation.composition,
        )

    def _atomic_split_provenance(
        self, units: Sequence[ContentUnit]
    ) -> list[AtomicSplitProvenance]:
        provenance: list[AtomicSplitProvenance] = []
        for unit in units:
            if (
                unit.fragment_count < 2
                or unit.forced_split_reason
                != "configured_token_counter_hard_split"
            ):
                continue
            atomic_kind: str | None = None
            if getattr(unit.source, "content_origin", None) == "visual":
                atomic_kind = "visual"
            elif unit.type == UnitType.TABLE:
                atomic_kind = "table"
            elif unit.type == UnitType.LIST:
                atomic_kind = "list"
            if atomic_kind is None:
                continue
            provenance.append(
                AtomicSplitProvenance(
                    source_unit_id=unit.source_unit_id,
                    atomic_kind=atomic_kind,  # type: ignore[arg-type]
                    fragment_unit_id=unit.unit_id,
                    fragment_index=unit.fragment_index + 1,
                    fragment_count=unit.fragment_count,
                    reason="configured_token_counter_hard_split",
                    token_counter_id=self.token_counter.counter_id,
                    configured_hard_max_tokens=(
                        self.config.tokens.hard_max_tokens
                    ),
                )
            )
        return provenance

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result

    @staticmethod
    def _unique_dicts(
        values: Iterable[dict[str, object]],
    ) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        seen: set[str] = set()
        for value in values:
            key = repr(sorted(value.items()))
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result

    @staticmethod
    def _unique_lists(values: Iterable[list[str]]) -> list[list[str]]:
        result: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()
        for value in values:
            key = tuple(value)
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result
