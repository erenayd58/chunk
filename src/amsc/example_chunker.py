"""The smallest complete chunking method -- the template for a new one.

Copy this file, change the partition, register the result in
:mod:`amsc.methods`, write a test. That is the whole procedure; nothing in
the Viewer, the benchmark or the console has to learn the method's name.

The method here packs consecutive content units into a chunk until the
next unit would push it past the shared target, cutting only at unit
boundaries and never crossing a heading. It is deliberately naive -- a
partition that any reader can predict -- so that a test can hold it to a
hand-computed answer. It is **not registered**: it exists to be copied and
to let the extension path be proved without leaving a fifth product method
behind. ``docs/adding-a-chunker.md`` walks through it.

What a partition must produce is the structural row schema, which every
downstream consumer reads: the chunk mapper locates each row's text in the
canonical, the packager writes it beside the other arms, the Viewer's
boundary-reason reader keys on ``section_paths`` and unit types, and the
retrieval index reads ``text`` and ``unit_ids``.
"""

from __future__ import annotations

from typing import Any, Sequence

from .methods import ChunkMethod, PartitionResult
from .models import RawDocumentUnit, UnitType

#: The chunk id infix, so a row says which method wrote it.
CHUNK_INFIX = "fw-chunk"
RENDER_SEPARATOR = "\n\n"


def partition_fixed_window(
    units: Sequence[RawDocumentUnit],
    *,
    counter: Any,
    budget: Any,
    max_units: int = 3,
    **_ignored: Any,
) -> PartitionResult:
    """Pack up to ``max_units`` content units per chunk, within the target.

    Headings are not chunk content (the structural family leaves them out of
    ``unit_ids`` too); they close the open chunk so a window never crosses a
    section. A unit that alone exceeds the hard maximum is emitted on its own
    rather than split: this example makes no claim about oversized units.
    """
    target = int(budget["target_tokens"])
    document_id = units[0].document_id if units else ""
    rows: list[dict[str, Any]] = []
    open_units: list[RawDocumentUnit] = []

    def close() -> None:
        if not open_units:
            return
        text = RENDER_SEPARATOR.join(unit.text for unit in open_units)
        paths: list[list[str]] = []
        for unit in open_units:
            path = list(unit.section_path or [])
            if path and path not in paths:
                paths.append(path)
        rows.append(
            {
                "chunk_id": f"{document_id}:{CHUNK_INFIX}-{len(rows) + 1:04d}",
                "text": text,
                "unit_ids": [unit.unit_id for unit in open_units],
                "token_count": counter.count(text),
                "pages": sorted({unit.source.page for unit in open_units}),
                "section_paths": paths,
                "heading": None,
                "split_strategies": ["whole"],
            }
        )
        open_units.clear()

    for unit in units:
        if unit.type == UnitType.HEADING:
            close()
            continue
        projected = counter.count(RENDER_SEPARATOR.join(u.text for u in (*open_units, unit)))
        if open_units and (len(open_units) >= max_units or projected > target):
            close()
        open_units.append(unit)
    close()
    return PartitionResult(rows, {"max_units": max_units})


#: The registration a developer adds to ``amsc.methods._BUILTIN``. Kept here,
#: unregistered, so the tests can prove the path.
FIXED_WINDOW = ChunkMethod(
    key="fixed-window",
    kind="fixed_window",
    label="Sabit Pencere",
    summary="Ardışık birimleri sabit sayıda pencereler halinde paketler; başlıkları geçmez.",
    partition=partition_fixed_window,
    options={"max_units": 3},
)
