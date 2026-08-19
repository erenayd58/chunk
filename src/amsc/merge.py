from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

import numpy as np

from .config import SemanticSafeMergeConfig, TokenLimitsConfig
from .features import TokenSqrtWindowPooler
from .models import (
    AcceptedMergeProvenance,
    BoundaryEvidence,
    ChunkBoundary,
    ContentUnit,
    MergeDecisionProvenance,
)
from .tokenization import TokenCounter
from .units import RenderedTokenBudgeter


@dataclass
class V4ChunkDraft:
    units: list[ContentUnit]
    end_boundary: ChunkBoundary
    original_chunk_indices: tuple[int, ...]
    unmerged_short_tail_reason: str | None = None
    tail_coalesced: bool = False
    removed_tail_boundary_reason: str | None = None
    merge_decisions: list[MergeDecisionProvenance] = field(default_factory=list)
    accepted_merge: AcceptedMergeProvenance | None = None


@dataclass
class _Proposal:
    proposal_id: str
    focus_index: int
    left_index: int
    right_index: int
    direction: str
    boundary_index: int | None
    boundary_original_reason: str
    original_boundary_strength: float | None
    pair_shift: float | None
    original_adaptive_threshold: float | None
    semantic_cohesion_passed: bool | None
    combined_token_count: int | None
    hard_cap_passed: bool | None
    structural_compatibility: bool | None
    rejection_reason: str | None
    accepted: bool = False

    @property
    def eligible(self) -> bool:
        return self.rejection_reason is None


class SemanticSafeMergeResolver:
    """Single-pass, semantic-first merge over original adjacent chunks."""

    def __init__(
        self,
        *,
        config: SemanticSafeMergeConfig,
        token_limits: TokenLimitsConfig,
        token_counter: TokenCounter,
        budgeter: RenderedTokenBudgeter,
        pooler: TokenSqrtWindowPooler | None = None,
    ) -> None:
        self.config = config
        self.limits = token_limits
        self.token_counter = token_counter
        self.budgeter = budgeter
        self.pooler = pooler or TokenSqrtWindowPooler()

    def resolve(
        self,
        drafts: Sequence[V4ChunkDraft],
        boundaries: Sequence[BoundaryEvidence],
        retained_embeddings: Mapping[str, np.ndarray],
    ) -> tuple[list[V4ChunkDraft], list[BoundaryEvidence]]:
        if not self.config.enabled or len(drafts) < 2:
            return list(drafts), list(boundaries)

        working = [
            replace(
                draft,
                units=list(draft.units),
                merge_decisions=list(draft.merge_decisions),
            )
            for draft in drafts
        ]
        boundary_by_index = {
            boundary.boundary_index: boundary for boundary in boundaries
        }
        small_limit = self.config.small_chunk_threshold or self.limits.min_tokens
        proposals: list[_Proposal] = []
        preferred: list[_Proposal] = []

        for focus_index, draft in enumerate(working):
            if self.budgeter.count_units(draft.units) >= small_limit:
                continue
            directional: list[_Proposal] = []
            if focus_index > 0:
                directional.append(
                    self._inspect(
                        focus_index=focus_index,
                        left_index=focus_index - 1,
                        right_index=focus_index,
                        direction="left",
                        drafts=working,
                        boundary_by_index=boundary_by_index,
                        retained_embeddings=retained_embeddings,
                    )
                )
            if focus_index + 1 < len(working):
                directional.append(
                    self._inspect(
                        focus_index=focus_index,
                        left_index=focus_index,
                        right_index=focus_index + 1,
                        direction="right",
                        drafts=working,
                        boundary_by_index=boundary_by_index,
                        retained_embeddings=retained_embeddings,
                    )
                )
            proposals.extend(directional)
            eligible = [proposal for proposal in directional if proposal.eligible]
            if eligible:
                chosen = min(eligible, key=self._proposal_rank)
                preferred.append(chosen)
                for proposal in eligible:
                    if proposal is not chosen:
                        proposal.rejection_reason = "not_preferred_direction"

        used: set[int] = set()
        accepted: list[_Proposal] = []
        for proposal in sorted(preferred, key=self._proposal_rank):
            if proposal.left_index in used or proposal.right_index in used:
                proposal.rejection_reason = "overlapping_proposal_conflict"
                continue
            proposal.accepted = True
            used.add(proposal.left_index)
            used.add(proposal.right_index)
            accepted.append(proposal)

        decisions_by_boundary: dict[int, list[MergeDecisionProvenance]] = {}
        for proposal in proposals:
            decision = self._as_decision(proposal)
            working[proposal.focus_index].merge_decisions.append(decision)
            if proposal.boundary_index is not None:
                decisions_by_boundary.setdefault(
                    proposal.boundary_index, []
                ).append(decision)

        updated_boundaries: list[BoundaryEvidence] = []
        accepted_boundary_indices = {
            proposal.boundary_index
            for proposal in accepted
            if proposal.boundary_index is not None
        }
        for boundary in boundaries:
            decisions = decisions_by_boundary.get(boundary.boundary_index)
            update: dict[str, object] = {}
            if decisions:
                update["merge_decisions"] = sorted(
                    decisions, key=lambda item: item.proposal_id
                )
            if boundary.boundary_index in accepted_boundary_indices:
                update["selected_reason"] = (
                    "removed_by_v4_semantic_safe_merge"
                )
            updated_boundaries.append(
                boundary.model_copy(update=update) if update else boundary
            )

        accepted_by_left = {proposal.left_index: proposal for proposal in accepted}
        merged: list[V4ChunkDraft] = []
        index = 0
        while index < len(working):
            proposal = accepted_by_left.get(index)
            if proposal is None:
                merged.append(working[index])
                index += 1
                continue
            left = working[proposal.left_index]
            right = working[proposal.right_index]
            combined_units = [*left.units, *right.units]
            post_tokens = self.budgeter.count_units(combined_units)
            if post_tokens > self.limits.hard_max_tokens:
                raise AssertionError("Accepted merge violates configured hard cap")
            strength = proposal.original_boundary_strength or 0.0
            if proposal.pair_shift is None or proposal.original_adaptive_threshold is None:
                raise AssertionError("Accepted merge lacks semantic cohesion provenance")
            if proposal.boundary_index is None:
                raise AssertionError("Accepted merge lacks a boundary index")
            provenance = AcceptedMergeProvenance(
                proposal_id=proposal.proposal_id,
                source_chunk_indices=[
                    proposal.left_index,
                    proposal.right_index,
                ],
                removed_boundary_index=proposal.boundary_index,
                direction=proposal.direction,  # type: ignore[arg-type]
                pre_merge_token_counts=[
                    self.budgeter.count_units(left.units),
                    self.budgeter.count_units(right.units),
                ],
                post_merge_token_count=post_tokens,
                pair_shift=proposal.pair_shift,
                original_adaptive_threshold=(
                    proposal.original_adaptive_threshold
                ),
                original_boundary_strength=strength,
            )
            merged.append(
                V4ChunkDraft(
                    units=combined_units,
                    end_boundary=right.end_boundary,
                    original_chunk_indices=(
                        *left.original_chunk_indices,
                        *right.original_chunk_indices,
                    ),
                    unmerged_short_tail_reason=(
                        right.unmerged_short_tail_reason
                    ),
                    tail_coalesced=(left.tail_coalesced or right.tail_coalesced),
                    removed_tail_boundary_reason=(
                        right.removed_tail_boundary_reason
                        or left.removed_tail_boundary_reason
                    ),
                    merge_decisions=sorted(
                        [*left.merge_decisions, *right.merge_decisions],
                        key=lambda item: item.proposal_id,
                    ),
                    accepted_merge=provenance,
                )
            )
            index += 2

        return merged, updated_boundaries

    def _inspect(
        self,
        *,
        focus_index: int,
        left_index: int,
        right_index: int,
        direction: str,
        drafts: Sequence[V4ChunkDraft],
        boundary_by_index: Mapping[int, BoundaryEvidence],
        retained_embeddings: Mapping[str, np.ndarray],
    ) -> _Proposal:
        boundary = drafts[left_index].end_boundary
        boundary_index = boundary.boundary_index
        proposal_id = f"merge-{focus_index:04d}-{direction}"
        base = dict(
            proposal_id=proposal_id,
            focus_index=focus_index,
            left_index=left_index,
            right_index=right_index,
            direction=direction,
            boundary_index=boundary_index,
            boundary_original_reason=boundary.reason,
            original_boundary_strength=boundary.original_boundary_strength,
            pair_shift=None,
            original_adaptive_threshold=(
                boundary.adaptive_threshold.value
                if boundary.adaptive_threshold is not None
                else None
            ),
            semantic_cohesion_passed=None,
            combined_token_count=None,
            hard_cap_passed=None,
            structural_compatibility=self._structural_compatibility(
                drafts[left_index], drafts[right_index]
            ),
        )
        if boundary_index is None or boundary_index not in boundary_by_index:
            return _Proposal(
                **base, rejection_reason="boundary_missing_semantic_evidence"
            )

        if boundary.reason == "hard_limit_fallback":
            return _Proposal(
                **base,
                rejection_reason="original_boundary_hard_limit_fallback",
            )

        strength = boundary.original_boundary_strength or 0.0
        if strength >= self.config.high_confidence_strength_threshold:
            return _Proposal(
                **base, rejection_reason="original_boundary_high_confidence"
            )

        pair_shift = self._pair_shift(
            drafts[left_index], drafts[right_index], retained_embeddings
        )
        if pair_shift is None:
            return _Proposal(
                **base, rejection_reason="missing_retained_unit_embedding"
            )
        threshold = boundary.adaptive_threshold
        if threshold is None:
            return _Proposal(
                **base, rejection_reason="missing_original_adaptive_threshold"
            )
        cohesion_passed = pair_shift < threshold.value
        combined_tokens = self.budgeter.count_units(
            [*drafts[left_index].units, *drafts[right_index].units]
        )
        hard_cap_passed = combined_tokens <= self.limits.hard_max_tokens
        base.update(
            pair_shift=pair_shift,
            original_adaptive_threshold=threshold.value,
            semantic_cohesion_passed=cohesion_passed,
            combined_token_count=combined_tokens,
            hard_cap_passed=hard_cap_passed,
        )
        if not cohesion_passed:
            return _Proposal(
                **base, rejection_reason="semantic_cohesion_not_met"
            )
        if not hard_cap_passed:
            return _Proposal(
                **base, rejection_reason="combined_hard_cap_exceeded"
            )
        return _Proposal(**base, rejection_reason=None)

    def _pair_shift(
        self,
        left: V4ChunkDraft,
        right: V4ChunkDraft,
        retained_embeddings: Mapping[str, np.ndarray],
    ) -> float | None:
        left_vector = self._draft_vector(left, retained_embeddings)
        right_vector = self._draft_vector(right, retained_embeddings)
        if left_vector is None or right_vector is None:
            return None
        cosine = float(np.dot(left_vector, right_vector))
        cosine = max(-1.0, min(1.0, cosine))
        return (1.0 - cosine) / 2.0

    def _draft_vector(
        self,
        draft: V4ChunkDraft,
        retained_embeddings: Mapping[str, np.ndarray],
    ) -> np.ndarray | None:
        vectors: list[np.ndarray] = []
        counts: list[int] = []
        for unit in draft.units:
            text = unit.text_for_embedding
            if text is None:
                continue
            vector = retained_embeddings.get(unit.unit_id)
            if vector is None:
                return None
            count = self.token_counter.count(text)
            if count <= 0:
                return None
            vectors.append(np.asarray(vector, dtype=np.float64))
            counts.append(count)
        if not vectors:
            return None
        return self.pooler.pool(vectors, counts)

    def _proposal_rank(self, proposal: _Proposal) -> tuple[object, ...]:
        strength = proposal.original_boundary_strength or 0.0
        cohesion_margin = (
            proposal.original_adaptive_threshold - proposal.pair_shift
            if proposal.pair_shift is not None
            and proposal.original_adaptive_threshold is not None
            else float("-inf")
        )
        target_distance = self._target_distance(
            proposal.combined_token_count or 0
        )
        structural_penalty = (
            1 if proposal.structural_compatibility is False else 0
        )
        return (
            -cohesion_margin,
            strength,
            target_distance,
            proposal.focus_index,
            0 if proposal.direction == "left" else 1,
            structural_penalty,
            proposal.proposal_id,
        )

    def _target_distance(self, token_count: int) -> float:
        if token_count <= self.limits.target_tokens:
            denominator = self.limits.target_tokens - self.limits.min_tokens
            value = (self.limits.target_tokens - token_count) / denominator
        else:
            denominator = (
                self.limits.soft_max_tokens - self.limits.target_tokens
            )
            value = (token_count - self.limits.target_tokens) / denominator
        return max(0.0, min(1.0, value))

    @staticmethod
    def _structural_compatibility(
        left: V4ChunkDraft, right: V4ChunkDraft
    ) -> bool | None:
        left_paths = [unit.section_path for unit in left.units if unit.section_path]
        right_paths = [unit.section_path for unit in right.units if unit.section_path]
        if not left_paths or not right_paths:
            return None
        for left_path in left_paths:
            for right_path in right_paths:
                depth = min(len(left_path), len(right_path))
                if left_path[:depth] == right_path[:depth]:
                    return True
                if left_path and right_path and left_path[0] == right_path[0]:
                    return True
        return False

    @staticmethod
    def _as_decision(proposal: _Proposal) -> MergeDecisionProvenance:
        return MergeDecisionProvenance(
            proposal_id=proposal.proposal_id,
            focus_chunk_index=proposal.focus_index,
            left_chunk_index=proposal.left_index,
            right_chunk_index=proposal.right_index,
            direction=proposal.direction,  # type: ignore[arg-type]
            boundary_index=proposal.boundary_index,
            boundary_original_reason=proposal.boundary_original_reason,
            original_boundary_strength=proposal.original_boundary_strength,
            pair_shift=proposal.pair_shift,
            original_adaptive_threshold=proposal.original_adaptive_threshold,
            semantic_cohesion_passed=proposal.semantic_cohesion_passed,
            combined_token_count=proposal.combined_token_count,
            hard_cap_passed=proposal.hard_cap_passed,
            structural_compatibility=proposal.structural_compatibility,
            accepted=proposal.accepted,
            rejection_reason=proposal.rejection_reason,
            removed_boundary=proposal.accepted,
        )
