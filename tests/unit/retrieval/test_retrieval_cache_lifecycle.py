"""The retrieval embedding cache's write lifecycle.

The same defect the boundary cache had, in the cache next door -- found while
verifying that fix, because clearing ``<data>/cache`` took ingestion down with

    Embedding failed: [Errno 2] No such file or directory:
        .../cache/embeddings/<model>/<sha>.tmp.npy

Two ways a temporary went missing here, and both are covered below: the
directory was created once at construction and could be cleared underneath a
long-lived cache, and the temporary's name was derived from the key, so two
writers of one text shared one file -- the first rename consumed it and the
second found nothing to move.

``tests/unit/embedding/test_embedding_cache_lifecycle.py`` is the same story
for the boundary cache. The two are kept apart deliberately: separate
interfaces, separate namespaces, and no import between them.
"""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

import numpy as np
import pytest

from amsc.retrieval.embeddings import CachedEmbeddings, model_slug


class CountingProvider:
    """A provider that answers deterministically and counts what it was asked."""

    model_id = "test/embedder"

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return np.asarray(
            [[float(len(text)), 1.0, 0.0, 0.0] for text in texts], dtype=np.float32
        )


def store(tmp_path: Path) -> tuple[CachedEmbeddings, Path]:
    cache = CachedEmbeddings(CountingProvider(), tmp_path / "cache" / "embeddings")
    return cache, cache.cache_dir


def strays(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("tmp*.npy"))


def test_a_write_survives_the_cache_directory_being_cleared(tmp_path) -> None:
    """The failure, reproduced: the cache outlives the directory it made."""
    cache, directory = store(tmp_path)
    cache.embed(["first text"])
    assert directory.is_dir()

    shutil.rmtree(tmp_path / "cache")
    assert not directory.exists()

    vectors = cache.embed(["second text"])

    assert directory.is_dir()
    assert vectors.shape == (1, 4)
    assert len(list(directory.glob("*.npy"))) == 1


def test_two_writers_of_one_text_do_not_share_a_temporary(tmp_path) -> None:
    """The name used to be ``{key}.tmp.npy`` -- one file for every writer.

    The first rename consumed it and the second raised ``FileNotFoundError``,
    which is a temporary disappearing before it could be used. Each writer owns
    its own now, so a hundred of them cannot collide.
    """
    cache, directory = store(tmp_path)
    # Defeat the in-memory hit, so every thread really writes a file.
    failures: list[BaseException] = []
    start = threading.Barrier(8)

    def write() -> None:
        start.wait()
        for _ in range(30):
            try:
                cache._memory.clear()
                cache.embed(["one shared text"])
            except BaseException as error:  # noqa: BLE001 - asserted below
                failures.append(error)

    threads = [threading.Thread(target=write) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    assert strays(directory) == []
    assert len(list(directory.glob("*.npy"))) == 1


def test_a_failed_publish_leaves_no_temporary_behind(tmp_path, monkeypatch) -> None:
    cache, directory = store(tmp_path)

    monkeypatch.setattr(
        os, "replace", lambda source, target: (_ for _ in ()).throw(OSError("refused"))
    )

    with pytest.raises(OSError):
        cache.embed(["text"])

    assert strays(directory) == []


def test_a_publish_that_lost_the_race_is_not_a_failure(tmp_path, monkeypatch) -> None:
    cache, directory = store(tmp_path)
    cache.embed(["text"])
    cache._memory.clear()

    monkeypatch.setattr(
        os, "replace", lambda source, target: (_ for _ in ()).throw(PermissionError(13, "busy"))
    )
    cache.embed(["text"])  # already published by the first call

    assert strays(directory) == []


def test_the_cache_still_answers_from_disk_and_spares_the_provider(tmp_path) -> None:
    """The fix must not change what the cache is for."""
    provider = CountingProvider()
    directory = tmp_path / "cache" / "embeddings"
    first = CachedEmbeddings(provider, directory)
    warm = first.embed(["alpha", "beta"])
    assert provider.calls == 1

    # A second process would start with an empty memory and a full directory.
    second = CachedEmbeddings(provider, directory)
    cold = second.embed(["alpha", "beta"])

    assert provider.calls == 1
    assert np.allclose(warm, cold)
    assert second.cache_dir == directory / model_slug(provider.model_id)
