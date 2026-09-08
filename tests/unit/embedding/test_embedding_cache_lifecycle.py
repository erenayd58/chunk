"""The boundary-embedding cache's write lifecycle.

The failure these were written for: a Hybrid analysis died with

    FileNotFoundError: .../cache/boundary-embeddings/tmp<random>.npz

which reads as a temporary file disappearing before it could be renamed, and
was really ``tempfile`` failing to *create* one because the cache directory had
gone since the cache object was built. The product holds one
``FileEmbeddingCache`` for the life of the process, and a cache directory is
something an operator, a container reset or a test is entitled to clear.

The other two tests cover what the same publish path does when it goes wrong in
the two other ways it can: it must not leave the temporary behind, and it must
not turn a lost race for one key into a failed chunking run.
"""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

import numpy as np
import pytest

from amsc.document.models import SemanticEmbeddingProvenance
from amsc.embedding.cache import CacheEntry, FileEmbeddingCache


def provenance(**over) -> SemanticEmbeddingProvenance:
    fields = dict(
        model_id="test:e5",
        prefix_policy="symmetric_query",
        prefix="query: ",
        model_input_limit=512,
        semantic_fragment_count=1,
        semantic_pooling="mean",
    )
    fields.update(over)
    return SemanticEmbeddingProvenance(**fields)


def entry(seed: int = 0) -> CacheEntry:
    return CacheEntry(
        vector=np.full(8, float(seed), dtype=np.float32), provenance=provenance()
    )


def strays(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("tmp*.npz"))


# ------------------------------------------------------------------ the bug


def test_a_write_survives_the_cache_directory_being_cleared(tmp_path) -> None:
    """The reported failure, reproduced and fixed.

    A cache object outlives the directory it was constructed against. Before
    the fix this raised ``FileNotFoundError`` naming a ``tmp*.npz`` that had
    never been created, and every Hybrid analysis in the process failed from
    then on.
    """
    directory = tmp_path / "cache" / "boundary-embeddings"
    cache = FileEmbeddingCache(directory)
    cache.set("first", entry(1))

    # Anything may clear a cache: an operator reclaiming disk, a container
    # reset, a test's temporary root going away.
    shutil.rmtree(tmp_path / "cache")
    assert not directory.exists()

    cache.set("second", entry(2))

    assert directory.is_dir()
    stored = cache.get("second")
    assert stored is not None
    assert np.allclose(stored.vector, entry(2).vector)
    # And the cache is a cache again, not a one-shot recovery.
    cache.set("third", entry(3))
    assert cache.get("third") is not None


def test_a_read_after_the_directory_is_cleared_is_a_miss(tmp_path) -> None:
    """A cleared cache forgets; it does not raise."""
    directory = tmp_path / "cache" / "boundary-embeddings"
    cache = FileEmbeddingCache(directory)
    cache.set("gone", entry(1))
    shutil.rmtree(tmp_path / "cache")

    assert cache.get("gone") is None


# ------------------------------------------------- what a failure leaves behind


def test_a_failed_publish_leaves_no_temporary_behind(tmp_path, monkeypatch) -> None:
    """Every early return used to leak one ``tmp*.npz`` per attempt."""
    cache = FileEmbeddingCache(tmp_path / "cache")

    def refuse(source, target):
        raise OSError("the rename failed")

    monkeypatch.setattr(os, "replace", refuse)

    with pytest.raises(OSError):
        cache.set("key", entry(1))

    assert strays(cache.directory) == []


def test_a_successful_publish_leaves_no_temporary_behind(tmp_path) -> None:
    cache = FileEmbeddingCache(tmp_path / "cache")
    for index in range(5):
        cache.set(f"key{index}", entry(index))

    assert strays(cache.directory) == []
    assert len(list(cache.directory.glob("key*.npz"))) == 5


# ------------------------------------------------------------- under contention


def test_concurrent_writers_of_one_key_all_succeed(tmp_path) -> None:
    """Two threads writing one key is contention, not corruption.

    On Windows ``os.replace`` refuses to overwrite a file another thread has
    open, which a concurrent reader of the same key is doing. The entry is
    content-addressed -- the same key is the same bytes -- so a destination
    that is already there is this call's answer.
    """
    cache = FileEmbeddingCache(tmp_path / "cache")
    written = entry(7)
    failures: list[BaseException] = []
    start = threading.Barrier(9)

    def write() -> None:
        start.wait()
        for _ in range(40):
            try:
                cache.set("shared", written)
            except BaseException as error:  # noqa: BLE001 - the assertion is below
                failures.append(error)

    def read() -> None:
        start.wait()
        for _ in range(40):
            cache.get("shared")

    threads = [threading.Thread(target=write) for _ in range(8)]
    threads.append(threading.Thread(target=read))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    assert strays(cache.directory) == []
    stored = cache.get("shared")
    assert stored is not None
    assert np.allclose(stored.vector, written.vector)


def test_a_publish_that_lost_the_race_is_not_a_failure(tmp_path, monkeypatch) -> None:
    """The Windows path, forced: the rename is refused and the key is there."""
    cache = FileEmbeddingCache(tmp_path / "cache")
    cache.set("shared", entry(1))

    real_replace = os.replace
    monkeypatch.setattr(
        os, "replace", lambda source, target: (_ for _ in ()).throw(PermissionError(13, "busy"))
    )

    cache.set("shared", entry(1))  # refused every time, and already published

    monkeypatch.setattr(os, "replace", real_replace)
    assert strays(cache.directory) == []
    stored = cache.get("shared")
    assert stored is not None
    assert np.allclose(stored.vector, entry(1).vector)


def test_a_refused_publish_with_nothing_published_still_raises(tmp_path, monkeypatch) -> None:
    """The fallback must not swallow a write that really did not happen."""
    cache = FileEmbeddingCache(tmp_path / "cache")
    monkeypatch.setattr(
        os, "replace", lambda source, target: (_ for _ in ()).throw(PermissionError(13, "busy"))
    )

    with pytest.raises(PermissionError):
        cache.set("never-published", entry(1))

    assert strays(cache.directory) == []
    assert cache.get("never-published") is None


# --------------------------------------------------------- semantics unchanged


def test_the_entry_round_trips_unchanged(tmp_path) -> None:
    """The fix must not touch what a cache stores or returns."""
    cache = FileEmbeddingCache(tmp_path / "cache")
    written = CacheEntry(
        vector=np.linspace(-1.0, 1.0, 16, dtype=np.float32),
        provenance=provenance(semantic_fragment_count=3, cache_hit=False),
    )
    cache.set("round-trip", written)

    stored = cache.get("round-trip")
    assert stored is not None
    assert stored.vector.dtype == np.float32
    assert np.allclose(stored.vector, written.vector)
    assert stored.provenance == written.provenance


def test_a_corrupt_entry_is_a_miss_not_a_failure(tmp_path) -> None:
    cache = FileEmbeddingCache(tmp_path / "cache")
    cache.set("torn", entry(1))
    (cache.directory / "torn.npz").write_bytes(b"not a zip file")

    assert cache.get("torn") is None
