from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

from .config import V1Config, V2Config
from .embeddings import SemanticBoundaryEmbedder
from .features import AdjacentSemanticFeatureExtractor
from .models import (
    BoundaryEvidence,
    Chunk,
    ChunkBoundary,
    ChunkingResult,
    ContentUnit,
    RawDocumentUnit,
    SemanticEmbeddingProvenance,
)
from .selection import (
    IntervalBoundarySelector,
    V2TailResolver,
)
from .thresholds import (
    FixedThresholdEstimator,
    HierarchicalAdaptiveThresholdEstimator,
    SemanticThresholdEstimator,
)
from .tokenization import TokenCounter
from .units import HeadingAttachmentBuilder, RenderedTokenBudgeter, render_units


@dataclass
class _ChunkDraft:
    units: list[ContentUnit]
    end_boundary: ChunkBoundary
    unmerged_short_tail_reason: str | None
    tail_coalesced: bool = False
    removed_tail_boundary_reason: str | None = None


@dataclass(frozen=True)
class _SemanticRun:
    start: int
    end: int
    units: tuple[ContentUnit, ...]
    raw_boundaries: tuple[BoundaryEvidence, ...]


class _BaseChunker:
    algorithm_version: str

    def __init__(
        self,
        *,
        config: V1Config | V2Config,
        token_counter: TokenCounter,
        boundary_embedder: SemanticBoundaryEmbedder,
        threshold_estimator: SemanticThresholdEstimator,
        selector: IntervalBoundarySelector,
    ) -> None:
        self.config = config
        self.token_counter = token_counter
        self.boundary_embedder = boundary_embedder
        self.threshold_estimator = threshold_estimator
        self.selector = selector
        self.budgeter = selector.budgeter
        self.unit_builder = HeadingAttachmentBuilder(self.budgeter)
        self.feature_extractor = AdjacentSemanticFeatureExtractor()

    def chunk(self, raw_units: Sequence[RawDocumentUnit]) -> ChunkingResult:
        if not raw_units:
            raise ValueError("At least one raw unit is required")
        prepared = self.unit_builder.build(raw_units)
        if not prepared:
            raise ValueError("Document produced no prepared units")

        runs, raw_boundaries, provenance_by_unit = self._embed_and_extract(prepared)
        units_by_id = {unit.unit_id: unit for unit in prepared}
        resolved_boundaries = self.threshold_estimator.apply(
            raw_boundaries, units_by_id
        )
        resolved_by_index = {
            boundary.boundary_index: boundary for boundary in resolved_boundaries
        }

        drafts: list[_ChunkDraft] = []
        all_boundaries: list[BoundaryEvidence] = []
        run_by_start = {run.start: run for run in runs}
        cursor = 0
        while cursor < len(prepared):
            run = run_by_start.get(cursor)
            if run is None:
                unit = prepared[cursor]
                drafts.append(
                    _ChunkDraft(
                        units=[unit],
                        end_boundary=ChunkBoundary(
                            reason=unit.forced_split_reason
                            or "nonsemantic_heading_boundary"
                        ),
                        unmerged_short_tail_reason=None,
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
                    _ChunkDraft(
                        units=list(run.units[segment.start : segment.end]),
                        end_boundary=segment.end_boundary,
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
    ]:
        runs: list[_SemanticRun] = []
        all_boundaries: list[BoundaryEvidence] = []
        provenance_by_unit: dict[str, SemanticEmbeddingProvenance] = {}
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
            for unit, provenance in zip(run_units, batch.provenance, strict=True):
                provenance_by_unit[unit.unit_id] = provenance

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

        return runs, all_boundaries, provenance_by_unit

    def _materialize(
        self,
        *,
        document_id: str,
        drafts: Sequence[_ChunkDraft],
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

            unit_ids = self._unique(
                unit_id for unit in draft.units for unit_id in unit.raw_unit_ids
            )
            source_spans = self._unique_dicts(
                span.model_dump(exclude_none=True)
                for unit in draft.units
                for span in unit.source_spans
            )
            section_paths = self._unique_lists(
                list(unit.section_path) for unit in draft.units if unit.section_path
            )
            semantic_provenance = [
                {"unit_id": unit.unit_id, **asdict(provenance_by_unit[unit.unit_id])}
                for unit in draft.units
                if unit.unit_id in provenance_by_unit
            ]
            chunks.append(
                Chunk(
                    chunk_id=f"{document_id}:chunk-{index:04d}",
                    document_id=document_id,
                    text=text,
                    token_count=token_count,
                    unit_ids=unit_ids,
                    content_unit_ids=[unit.unit_id for unit in draft.units],
                    section_paths=section_paths,
                    source_spans=source_spans,
                    start_boundary=start_boundary,
                    end_boundary=draft.end_boundary,
                    unmerged_short_tail_reason=draft.unmerged_short_tail_reason,
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
                )
            )
            start_boundary = draft.end_boundary

        return ChunkingResult(
            document_id=document_id,
            chunks=chunks,
            boundaries=boundaries,
            algorithm_version=self.algorithm_version,
            parameter_status=self.config.algorithm.tuning_status,
        )

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


class V1Chunker(_BaseChunker):
    algorithm_version = "amsc-v1"

    def __init__(
        self,
        *,
        config: V1Config,
        token_counter: TokenCounter,
        boundary_embedder: SemanticBoundaryEmbedder,
    ) -> None:
        budgeter = RenderedTokenBudgeter(
            token_counter=token_counter,
            hard_max_tokens=config.tokens.hard_max_tokens,
        )
        estimator = FixedThresholdEstimator(config.semantic.fixed_threshold)
        selector = IntervalBoundarySelector(
            budgeter=budgeter,
            token_limits=config.tokens,
            semantic=config.semantic,
            selection=config.selection,
            semantic_boundary_reason=estimator.semantic_boundary_reason,
        )
        super().__init__(
            config=config,
            token_counter=token_counter,
            boundary_embedder=boundary_embedder,
            threshold_estimator=estimator,
            selector=selector,
        )
        # Preserve the V1 feature-extractor facade while orchestration uses
        # compute_raw + FixedThresholdEstimator internally.
        self.feature_extractor = AdjacentSemanticFeatureExtractor(
            config.semantic.fixed_threshold
        )


class V2Chunker(_BaseChunker):
    algorithm_version = "amsc-v2"

    def __init__(
        self,
        *,
        config: V2Config,
        token_counter: TokenCounter,
        boundary_embedder: SemanticBoundaryEmbedder,
    ) -> None:
        budgeter = RenderedTokenBudgeter(
            token_counter=token_counter,
            hard_max_tokens=config.tokens.hard_max_tokens,
        )
        estimator = HierarchicalAdaptiveThresholdEstimator(config.semantic)
        selector = IntervalBoundarySelector(
            budgeter=budgeter,
            token_limits=config.tokens,
            semantic=None,
            selection=config.selection,
            semantic_boundary_reason=estimator.semantic_boundary_reason,
            tail_resolver=V2TailResolver(budgeter, config.tokens),
            removed_tail_selected_reason="removed_by_v2_tail_coalescing",
        )
        super().__init__(
            config=config,
            token_counter=token_counter,
            boundary_embedder=boundary_embedder,
            threshold_estimator=estimator,
            selector=selector,
        )
