from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import ChunkingResult, RawDocumentUnit


def load_jsonl_units(path: str | Path) -> list[RawDocumentUnit]:
    source = Path(path)
    units: list[RawDocumentUnit] = []
    with source.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                units.append(RawDocumentUnit.model_validate(payload))
            except Exception as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc

    validate_document_units(units)
    return units


def validate_document_units(units: Iterable[RawDocumentUnit]) -> None:
    materialized = list(units)
    if not materialized:
        raise ValueError("Input must contain at least one unit")

    document_ids = {unit.document_id for unit in materialized}
    if len(document_ids) != 1:
        raise ValueError("A canonical JSONL file must contain exactly one document")

    unit_ids = [unit.unit_id for unit in materialized]
    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("unit_id values must be unique")

    orders = [unit.order for unit in materialized]
    if len(orders) != len(set(orders)):
        raise ValueError("order values must be unique")
    if orders != sorted(orders):
        raise ValueError("units must be stored in strictly increasing order")


def write_chunking_result(result: ChunkingResult, output_dir: str | Path) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    chunks_path = destination / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in result.chunks:
            handle.write(chunk.model_dump_json(exclude_none=True) + "\n")

    boundaries_path = destination / "boundaries.jsonl"
    with boundaries_path.open("w", encoding="utf-8", newline="\n") as handle:
        for boundary in result.boundaries:
            handle.write(boundary.model_dump_json(exclude_none=True) + "\n")


def write_resolved_config(config: object, output_dir: str | Path) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "resolved-config.json"
    data = config.model_dump(mode="json")  # type: ignore[attr-defined]
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

