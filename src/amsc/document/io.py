"""Reading and writing the artifact files: canonical units in, chunks out.

One owner for the file-level side of an artifact, including its content
hash: a manifest that records ``units_sha256`` and a benchmark that verifies
it must agree byte for byte, so the digest is computed in one place rather
than reimplemented beside each writer.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from .models import ChunkingResult, RawDocumentUnit


def sha256_file(path: str | Path) -> str:
    """The SHA-256 of a file's bytes, read in 1 MiB blocks.

    The identity every artifact manifest is pinned by. Streamed rather than
    read whole because the canonical corpora are large enough to matter.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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

