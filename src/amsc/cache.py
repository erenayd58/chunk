from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from .models import SemanticEmbeddingProvenance


@dataclass(frozen=True)
class CacheEntry:
    vector: np.ndarray
    provenance: SemanticEmbeddingProvenance


class EmbeddingCache(Protocol):
    def get(self, key: str) -> CacheEntry | None: ...

    def set(self, key: str, entry: CacheEntry) -> None: ...


class FileEmbeddingCache:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> CacheEntry | None:
        path = self.directory / f"{key}.npz"
        if not path.exists():
            return None
        try:
            with np.load(path, allow_pickle=False) as data:
                vector = np.asarray(data["vector"], dtype=np.float32)
                metadata = json.loads(str(data["metadata"].item()))
            return CacheEntry(
                vector=vector,
                provenance=SemanticEmbeddingProvenance(**metadata),
            )
        except Exception:
            return None

    def set(self, key: str, entry: CacheEntry) -> None:
        destination = self.directory / f"{key}.npz"
        metadata = json.dumps(asdict(entry.provenance), sort_keys=True)
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".npz", dir=self.directory, delete=False
        ) as handle:
            temporary = Path(handle.name)
            np.savez_compressed(
                handle,
                vector=np.asarray(entry.vector, dtype=np.float32),
                metadata=np.asarray(metadata),
            )
        os.replace(temporary, destination)

