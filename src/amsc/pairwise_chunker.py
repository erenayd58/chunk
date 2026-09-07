"""A deliberately simple pairwise chunking method.

Every two consecutive content units become one chunk.

Example:
    unit-1 + unit-2 -> chunk-1
    unit-3 + unit-4 -> chunk-2
    unit-5          -> chunk-3

Headings are treated as section boundaries. An open chunk is closed before a
heading so that a pair never crosses into another section.
"""

from __future__ import annotations

from typing import Any, Sequence

from .chunk_method import ChunkMethod, PartitionResult
from .models import RawDocumentUnit, UnitType


CHUNK_INFIX = "pairwise"
RENDER_SEPARATOR = "\n\n"


def partition_pairwise(
    units: Sequence[RawDocumentUnit],
    *,
    counter: Any,
    budget: Any,
    **_ignored: Any,
) -> PartitionResult:
    """Group consecutive content units into pairs."""

    document_id = units[0].document_id if units else ""

    rows: list[dict[str, Any]] = []
    open_units: list[RawDocumentUnit] = []

    def close() -> None:
        if not open_units:
            return

        text = RENDER_SEPARATOR.join(unit.text for unit in open_units)

        section_paths: list[list[str]] = []
        for unit in open_units:
            path = list(unit.section_path or [])
            if path and path not in section_paths:
                section_paths.append(path)

        rows.append(
            {
                "chunk_id": (
                    f"{document_id}:{CHUNK_INFIX}-{len(rows) + 1:04d}"
                ),
                "text": text,
                "unit_ids": [unit.unit_id for unit in open_units],
                "token_count": counter.count(text),
                "pages": sorted(
                    {unit.source.page for unit in open_units}
                ),
                "section_paths": section_paths,
                "heading": None,
                "split_strategies": ["pairwise"],
            }
        )

        open_units.clear()

    for unit in units:
        # Headings define section boundaries but are not chunk content.
        if unit.type == UnitType.HEADING:
            close()
            continue

        open_units.append(unit)

        if len(open_units) == 2:
            close()

    # Odd number of units -> last one becomes a chunk by itself.
    close()

    return PartitionResult(
        rows,
        {
            "pair_size": 2,
        },
    )


PAIRWISE = ChunkMethod(
    key="pairwise",
    kind="pairwise",
    label="Pairwise",
    summary="Ardışık içerik birimlerini ikişerli chunk'lar halinde paketler.",
    partition=partition_pairwise,
)