"""Builders shared by the chunk mapping/quality/chunker tests.

Not a test module: ``tests/unit`` is on ``sys.path`` during collection, so this
is imported by name. Keeping the builders here means a fixture shape is defined
once -- a heading whose ``section_path`` did not end in its own text quietly
produced a real ``section_inconsistency`` finding the first time these were
written separately.
"""

from __future__ import annotations

from typing import Any, Iterable

from amsc.models import RawDocumentUnit, UnitType


def unit(
    unit_id: str,
    text: str,
    *,
    order: int,
    type: UnitType = UnitType.PARAGRAPH,
    level: int | None = None,
    section: Iterable[str] = (),
) -> RawDocumentUnit:
    return RawDocumentUnit(
        document_id="doc",
        unit_id=unit_id,
        order=order,
        text=text,
        type=type,
        heading_level=level,
        section_path=list(section),
    )


def heading(
    unit_id: str, text: str, order: int, *, section: Iterable[str] | None = None
) -> RawDocumentUnit:
    """A heading unit whose section path ends in its own text, as the parser emits."""
    return unit(
        unit_id,
        text,
        order=order,
        type=UnitType.HEADING,
        level=2,
        section=section if section is not None else (text,),
    )


def chunk(
    chunk_id: str, text: str, unit_ids: Iterable[str], **extra: Any
) -> dict[str, Any]:
    return {"chunk_id": chunk_id, "text": text, "unit_ids": list(unit_ids), **extra}


def words(count: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{index}" for index in range(count))


class WhitespaceCounter:
    """Whitespace token counter, so sizes in these fixtures read as word counts."""

    counter_id = "test:whitespace@1"

    def count(self, text: str) -> int:
        return len(text.split())

    def split(self, text: str, max_tokens: int) -> list[str]:
        pieces = text.split()
        return [
            " ".join(pieces[index : index + max_tokens])
            for index in range(0, len(pieces), max_tokens)
        ]
