"""A file-backed embedding cache, written so a publish cannot half-happen.

An entry is content-addressed: the key is a hash of the embedder's namespace
and the exact text, so the same key always names the same vector and the same
provenance. That is what makes the write safe to repeat and safe to lose --
losing one costs a model call, and two writers of one key write the same bytes.

The write is therefore a *publish*: a temporary file in the same directory,
then one atomic rename onto the key. What the rename needs, and what this
module is careful about, is that the temporary file exists for exactly as long
as it takes to consume it:

* **the directory is ensured on every write, not once at construction.** This
  object is long-lived -- the product holds one for the life of the process --
  and its directory is a *cache*, which an operator clearing disk, a container
  reset or a test's temporary root is entitled to remove underneath it. When it
  had gone, ``tempfile`` failed while creating the temporary and reported the
  failure against a path that had never existed, which reads as the temporary
  vanishing;
* **a failed publish takes its temporary with it.** Every early return from a
  write used to leave a ``tmp*.npz`` behind, so a directory that failed to
  publish once accumulated one stray per attempt;
* **a publish that loses a race is not a failure.** Windows refuses to rename
  over a file another thread has open, which is exactly what a concurrent
  reader of the same key is doing. The entry is content-addressed, so a
  destination that is already there holds the bytes this call was going to
  write, and the write has succeeded by another hand.

Nothing sweeps the directory of strays, deliberately: a sweeper cannot tell a
temporary another thread is still writing from one nobody will finish, and
deleting the first is precisely the failure this module exists to prevent.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from ..document.models import SemanticEmbeddingProvenance

#: How many times a publish that lost a race is retried before the destination
#: is inspected. Small on purpose: the contention is another thread reading the
#: same key, which is over in microseconds.
_PUBLISH_ATTEMPTS = 5
#: How long to wait between those attempts.
_PUBLISH_BACKOFF_SECONDS = 0.01


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
            # A miss, whatever went wrong. A cache that raises on a file it
            # cannot read turns a recoverable cost -- one model call -- into a
            # failed chunking run.
            return None

    def set(self, key: str, entry: CacheEntry) -> None:
        destination = self.directory / f"{key}.npz"
        metadata = json.dumps(asdict(entry.provenance), sort_keys=True)
        # Ensured here as well as in __init__, because this object outlives any
        # guarantee made at construction: see the module docstring.
        self.directory.mkdir(parents=True, exist_ok=True)

        handle = tempfile.NamedTemporaryFile(
            mode="wb", suffix=".npz", dir=self.directory, delete=False
        )
        temporary = Path(handle.name)
        try:
            with handle:
                np.savez_compressed(
                    handle,
                    vector=np.asarray(entry.vector, dtype=np.float32),
                    metadata=np.asarray(metadata),
                )
            _publish(temporary, destination)
        finally:
            # A no-op after a publish consumed it; the whole point after
            # anything else, so a directory does not fill with strays.
            temporary.unlink(missing_ok=True)


def _publish(temporary: Path, destination: Path) -> None:
    """Rename the temporary onto its key, atomically.

    ``os.replace`` is atomic on both platforms this runs on. On Windows it
    additionally refuses to replace a file that is open, so a reader of this
    key can make it fail; that is contention, not corruption, and the retry
    below outlasts it. If it still cannot, an entry already at the destination
    is this call's answer -- the same key means the same bytes.
    """
    for attempt in range(_PUBLISH_ATTEMPTS):
        try:
            os.replace(temporary, destination)
            return
        except PermissionError:
            if attempt + 1 < _PUBLISH_ATTEMPTS:
                time.sleep(_PUBLISH_BACKOFF_SECONDS)
                continue
            if destination.exists():
                return
            raise
