from __future__ import annotations

from collections.abc import Sequence

from .models import ContentUnit, HeadingAttachment, RawDocumentUnit, UnitType
from .tokenization import TokenCounter


RENDER_SEPARATOR = "\n\n"


def render_units(units: Sequence[ContentUnit]) -> str:
    return RENDER_SEPARATOR.join(unit.rendered_text for unit in units if unit.rendered_text)


class RenderedTokenBudgeter:
    """Prepares units so each rendered unit fits the configured PoC counter cap."""

    def __init__(self, token_counter: TokenCounter, hard_max_tokens: int) -> None:
        self.token_counter = token_counter
        self.hard_max_tokens = hard_max_tokens

    def count_units(self, units: Sequence[ContentUnit]) -> int:
        return self.token_counter.count(render_units(units))

    def split_content(
        self,
        raw: RawDocumentUnit,
        headings: Sequence[HeadingAttachment],
    ) -> list[ContentUnit]:
        attached = tuple(headings)
        complete = self._content_unit(raw, raw.text, attached, 0, 1, None)
        if self.token_counter.count(complete.rendered_text) <= self.hard_max_tokens:
            return [complete]

        # If headings consume the full rendered budget, emit them first. This is
        # planned before selection rather than discovered by the final invariant.
        leading_text = "\n".join(heading.text for heading in attached)
        if attached and self.token_counter.count(
            f"{leading_text}{RENDER_SEPARATOR}x"
        ) > self.hard_max_tokens:
            return self.heading_only_units(
                attached,
                order=raw.order,
                document_id=raw.document_id,
                section_path=tuple(raw.section_path),
            ) + self.split_content(raw, ())

        budget = self._largest_safe_content_budget(raw.text, attached)
        if budget < 1:
            if attached:
                return self.heading_only_units(
                    attached,
                    order=raw.order,
                    document_id=raw.document_id,
                    section_path=tuple(raw.section_path),
                ) + self.split_content(raw, ())
            raise ValueError(
                f"Unable to split unit {raw.unit_id!r} under configured hard cap"
            )

        pieces = self.token_counter.split(raw.text, budget)
        units = [
            self._content_unit(
                raw,
                piece,
                attached if index == 0 else (),
                index,
                len(pieces),
                "configured_token_counter_hard_split",
            )
            for index, piece in enumerate(pieces)
        ]
        self._assert_individual_fit(units)
        return units

    def heading_only_units(
        self,
        headings: Sequence[HeadingAttachment],
        order: int,
        document_id: str,
        section_path: tuple[str, ...],
    ) -> list[ContentUnit]:
        result: list[ContentUnit] = []
        for heading in headings:
            pieces = self.token_counter.split(heading.text, self.hard_max_tokens)
            for index, piece in enumerate(pieces):
                unit_id = (
                    heading.unit_id
                    if len(pieces) == 1
                    else f"{heading.unit_id}#heading-fragment-{index + 1}"
                )
                result.append(
                    ContentUnit(
                        document_id=document_id,
                        unit_id=unit_id,
                        source_unit_id=heading.unit_id,
                        order=order,
                        text=piece,
                        type=UnitType.HEADING,
                        section_path=section_path,
                        source=heading.source,
                        fragment_index=index,
                        fragment_count=len(pieces),
                        forced_split_reason=(
                            "oversized_heading_split"
                            if len(pieces) > 1
                            else "heading_budget_flush"
                        ),
                        semantic_text=None,
                    )
                )
        self._assert_individual_fit(result)
        return result

    def _largest_safe_content_budget(
        self, text: str, headings: tuple[HeadingAttachment, ...]
    ) -> int:
        high = min(self.hard_max_tokens, max(1, self.token_counter.count(text)))
        low = 1
        best = 0
        while low <= high:
            candidate = (low + high) // 2
            pieces = self.token_counter.split(text, candidate)
            safe = True
            for index, piece in enumerate(pieces):
                heading_text = (
                    "\n".join(heading.text for heading in headings)
                    if index == 0
                    else ""
                )
                rendered = (
                    f"{heading_text}{RENDER_SEPARATOR}{piece}"
                    if heading_text
                    else piece
                )
                if self.token_counter.count(rendered) > self.hard_max_tokens:
                    safe = False
                    break
            if safe:
                best = candidate
                low = candidate + 1
            else:
                high = candidate - 1
        return best

    def _content_unit(
        self,
        raw: RawDocumentUnit,
        text: str,
        headings: tuple[HeadingAttachment, ...],
        fragment_index: int,
        fragment_count: int,
        reason: str | None,
    ) -> ContentUnit:
        unit_id = (
            raw.unit_id
            if fragment_count == 1
            else f"{raw.unit_id}#fragment-{fragment_index + 1}"
        )
        return ContentUnit(
            document_id=raw.document_id,
            unit_id=unit_id,
            source_unit_id=raw.unit_id,
            order=raw.order,
            text=text,
            type=raw.type,
            section_path=tuple(raw.section_path),
            source=raw.source,
            leading_headings=headings,
            fragment_index=fragment_index,
            fragment_count=fragment_count,
            forced_split_reason=reason,
            semantic_text=text,
        )

    def _assert_individual_fit(self, units: Sequence[ContentUnit]) -> None:
        for unit in units:
            count = self.token_counter.count(unit.rendered_text)
            if count > self.hard_max_tokens:
                raise AssertionError(
                    f"Prepared unit {unit.unit_id!r} has {count} configured tokens"
                )


class HeadingAttachmentBuilder:
    def __init__(self, budgeter: RenderedTokenBudgeter) -> None:
        self.budgeter = budgeter

    def build(self, raw_units: Sequence[RawDocumentUnit]) -> list[ContentUnit]:
        pending: list[HeadingAttachment] = []
        prepared: list[ContentUnit] = []

        for raw in raw_units:
            if raw.type == UnitType.HEADING:
                pending.append(
                    HeadingAttachment(
                        unit_id=raw.unit_id,
                        text=raw.text,
                        heading_level=raw.heading_level or 1,
                        source=raw.source,
                    )
                )
                continue

            new_units = self.budgeter.split_content(raw, pending)
            prepared.extend(new_units)
            pending = []

        if pending:
            trailing = self.budgeter.heading_only_units(
                pending,
                order=raw_units[-1].order if raw_units else 0,
                document_id=raw_units[0].document_id,
                section_path=tuple(raw_units[-1].section_path),
            )
            prepared.extend(trailing)

        return prepared
