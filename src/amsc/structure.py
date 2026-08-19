from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from .config import SoftStructureConfig
from .models import (
    BoundaryEvidence,
    ContentUnit,
    StructuralBoundaryProvenance,
    UnitType,
)
from .thresholds import longest_common_prefix


_EVIDENCE_ORDER = {
    "heading_presence": 0,
    "section_path_transition": 1,
    "table_transition": 2,
    "list_transition": 3,
    "visual_transition": 4,
}


@dataclass(frozen=True)
class StructuralEvidence:
    evidence_types: tuple[str, ...]
    heading_unit_ids: tuple[str, ...]
    heading_levels: tuple[int, ...]
    left_section_path: tuple[str, ...]
    right_section_path: tuple[str, ...]
    common_section_prefix: tuple[str, ...]

    @property
    def present(self) -> bool:
        return bool(self.evidence_types)


class StructuralEvidenceProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def evidence(
        self, left: ContentUnit, right: ContentUnit
    ) -> StructuralEvidence: ...


class CanonicalStructuralEvidenceProvider:
    """Parser-agnostic evidence from optional canonical structural fields.

    The provider never treats a heading level, section label, or content type as
    authoritative. It only reports the presence of evidence that a bounded
    semantic threshold relaxation may use.
    """

    provider_id = "canonical-soft-structure@1"

    def __init__(self, config: SoftStructureConfig) -> None:
        self.config = config

    def evidence(
        self, left: ContentUnit, right: ContentUnit
    ) -> StructuralEvidence:
        evidence_types: list[str] = []
        headings = right.leading_headings if self.config.heading_support else ()
        if headings:
            evidence_types.append("heading_presence")

        if (
            self.config.section_transition_support
            and left.section_path != right.section_path
        ):
            evidence_types.append("section_path_transition")

        if self.config.atomic_type_support:
            if left.type != right.type and UnitType.TABLE in {left.type, right.type}:
                evidence_types.append("table_transition")
            if left.type != right.type and UnitType.LIST in {left.type, right.type}:
                evidence_types.append("list_transition")
            if _is_visual(left) != _is_visual(right):
                evidence_types.append("visual_transition")

        evidence_types.sort(key=_EVIDENCE_ORDER.__getitem__)
        return StructuralEvidence(
            evidence_types=tuple(evidence_types),
            heading_unit_ids=tuple(heading.unit_id for heading in headings),
            heading_levels=tuple(heading.heading_level for heading in headings),
            left_section_path=left.section_path,
            right_section_path=right.section_path,
            common_section_prefix=longest_common_prefix(
                left.section_path, right.section_path
            ),
        )


class SoftStructureSupportPolicy:
    def __init__(
        self,
        config: SoftStructureConfig,
        evidence_provider: StructuralEvidenceProvider | None = None,
    ) -> None:
        self.config = config
        self.evidence_provider = evidence_provider or (
            CanonicalStructuralEvidenceProvider(config)
        )

    def apply(
        self,
        boundaries: Sequence[BoundaryEvidence],
        units_by_id: Mapping[str, ContentUnit],
    ) -> list[BoundaryEvidence]:
        if not self.config.enabled:
            return list(boundaries)

        updated: list[BoundaryEvidence] = []
        for boundary in boundaries:
            threshold = boundary.adaptive_threshold
            if threshold is None:
                raise ValueError("Soft structure requires an adaptive threshold")
            left = units_by_id[boundary.left_unit_id]
            right = units_by_id[boundary.right_unit_id]
            evidence = self.evidence_provider.evidence(left, right)
            original_candidate = boundary.semantic_candidate

            effective_threshold = threshold.value
            if evidence.present and not threshold.degenerate:
                applicable_floor = min(
                    threshold.value,
                    self.config.semantic_floor,
                )
                effective_threshold = max(
                    applicable_floor,
                    threshold.value - self.config.max_threshold_relaxation,
                )
            applied_relaxation = threshold.value - effective_threshold
            effective_candidate = (
                not threshold.degenerate
                and boundary.semantic_shift >= effective_threshold
            )
            structural_assisted = (
                not original_candidate
                and effective_candidate
                and applied_relaxation > 0.0
            )
            provenance = StructuralBoundaryProvenance(
                provider_id=self.evidence_provider.provider_id,
                evidence_types=list(evidence.evidence_types),
                heading_unit_ids=list(evidence.heading_unit_ids),
                heading_levels=list(evidence.heading_levels),
                left_section_path=list(evidence.left_section_path),
                right_section_path=list(evidence.right_section_path),
                common_section_prefix=list(evidence.common_section_prefix),
                original_adaptive_threshold=threshold.value,
                effective_threshold=effective_threshold,
                configured_max_relaxation=(
                    self.config.max_threshold_relaxation
                ),
                applied_relaxation=applied_relaxation,
                semantic_floor=self.config.semantic_floor,
                original_semantic_candidate=original_candidate,
                effective_semantic_candidate=effective_candidate,
                structural_assisted_candidate=structural_assisted,
                boundary_candidate=effective_candidate,
                adaptive_degenerate=threshold.degenerate,
            )
            updated.append(boundary.model_copy(update={"structural": provenance}))
        return updated


def effective_semantic_candidate(boundary: BoundaryEvidence) -> bool:
    if boundary.structural is not None:
        return boundary.structural.boundary_candidate
    return boundary.semantic_candidate


def _is_visual(unit: ContentUnit) -> bool:
    return getattr(unit.source, "content_origin", None) == "visual"
