"""Retrieval embeddings for the RAG chat: a provider seam and a text cache.

The chat's dense leg embeds every arm's chunks with one model and every
question with the same model, so a comparison across chunkers varies the
chunker and nothing else. The model is configuration, not architecture:

* :class:`OpenAICompatibleEmbeddingProvider` speaks the ``/embeddings``
  contract every OpenAI-compatible gateway offers (OpenRouter today; a
  company gateway tomorrow). The reference candidate is the self-hostable
  ``Qwen/Qwen3-Embedding-8B``, reached as ``qwen/qwen3-embedding-8b``. The
  key is read from the environment at request time and used in one header.
* :class:`SentenceTransformerEmbeddingProvider` runs a local model through
  ``sentence-transformers`` for deployments that keep everything on-prem.

Both return L2-normalised ``float32`` rows, so cosine is a dot product and
the index never has to know which provider produced a vector.

:class:`CachedEmbeddings` stores one vector per exact text under
``.cache/rag-embeddings/<model slug>/<sha256(text)>.npy`` -- the same
per-text discipline the retrieval benchmark uses, in its own namespace, so a
re-run after a crash embeds only what is missing and a chunker change embeds
only the chunks that actually changed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

import numpy as np

DEFAULT_EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"
DEFAULT_EMBEDDING_ENDPOINT = "https://openrouter.ai/api/v1/embeddings"


class EmbeddingProvider(Protocol):
    """Anything that turns texts into normalised vectors."""

    @property
    def model_id(self) -> str: ...

    def embed(self, texts: Sequence[str]) -> np.ndarray: ...


@dataclass(frozen=True)
class EmbeddingUsage:
    texts: int
    cache_hits: int
    cache_misses: int
    provider_calls: int
    seconds: float


def _normalise(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim != 2:
        raise ValueError("embedding provider must return a 2-D array")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return vectors / norms


class OpenAICompatibleEmbeddingProvider:
    """``POST /embeddings`` with ``model`` + ``input``; nothing else assumed.

    Batches are sent whole; a transient HTTP failure is retried a few times
    with a fixed backoff, then raised -- the chat layer turns that into a
    user-facing message rather than a stack trace. ``dimensions`` is only
    sent when set, for models that accept a reduced output size.
    """

    def __init__(
        self,
        model: str = DEFAULT_EMBEDDING_MODEL,
        *,
        endpoint: str = DEFAULT_EMBEDDING_ENDPOINT,
        api_key_env: str = "OPENROUTER_API_KEY",
        batch_size: int = 32,
        timeout_seconds: float = 120.0,
        retries: int = 3,
        dimensions: int | None = None,
        concurrency: int = 4,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.model = model
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.batch_size = batch_size
        self.timeout_seconds = timeout_seconds
        self.retries = max(1, retries)
        self.dimensions = dimensions
        self.concurrency = max(1, concurrency)
        self.calls = 0
        self.prompt_tokens = 0
        self._lock = __import__("threading").Lock()

    @property
    def model_id(self) -> str:
        return self.model

    def _key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise RuntimeError(
                f"{self.api_key_env} is not set; the embedding provider cannot run "
                "without it (and it is never stored)"
            )
        return key

    def _post(self, texts: Sequence[str]) -> np.ndarray:
        body: dict[str, Any] = {"model": self.model, "input": list(texts)}
        if self.dimensions:
            body["dimensions"] = self.dimensions
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._key()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as error:
                last_error = RuntimeError(f"embedding endpoint returned HTTP {error.code}")
                if error.code in (400, 401, 403, 404):
                    raise last_error from None
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last_error = RuntimeError(f"embedding endpoint unreachable: {error}")
            time.sleep(1.5 * (attempt + 1))
        else:
            raise last_error or RuntimeError("embedding endpoint failed")
        usage = payload.get("usage") or {}
        with self._lock:
            self.calls += 1
            self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        rows = payload.get("data")
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise RuntimeError("embedding endpoint returned an unexpected shape; refusing to guess")
        ordered = sorted(rows, key=lambda row: int(row.get("index", 0)))
        return _normalise(np.asarray([row["embedding"] for row in ordered], dtype=np.float32))

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        batches = [
            texts[start : start + self.batch_size]
            for start in range(0, len(texts), self.batch_size)
        ]
        if self.concurrency <= 1 or len(batches) == 1:
            return np.vstack([self._post(batch) for batch in batches])
        # Batches are independent requests; a small pool turns a cold index
        # build from minutes into seconds without changing any vector.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            return np.vstack(list(pool.map(self._post, batches)))


class SentenceTransformerEmbeddingProvider:
    """A local ``sentence-transformers`` model; optional dependency."""

    def __init__(self, model_name: str, *, device: str = "cpu", batch_size: int = 16,
                 query_prefix: str = "", document_prefix: str = "") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:  # pragma: no cover - optional dependency
            raise RuntimeError("local embeddings need: pip install -e '.[model]'") from error
        self._model = SentenceTransformer(model_name, device=device)
        self.model_name = model_name
        self.batch_size = batch_size
        self.query_prefix = query_prefix
        self.document_prefix = document_prefix
        self.calls = 0
        self.prompt_tokens = 0

    @property
    def model_id(self) -> str:
        return f"local:{self.model_name}"

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        self.calls += 1
        vectors = self._model.encode(
            list(texts), batch_size=self.batch_size, normalize_embeddings=True,
            convert_to_numpy=True, show_progress_bar=False,
        )
        return _normalise(vectors)


def model_slug(model_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model_id).strip("_") or "model"


class CachedEmbeddings:
    """Per-text vector cache in front of any provider.

    Keys are ``sha256(text)`` under a per-model directory, so two models never
    share a vector and two identical chunks (a repeated banner) share one.
    """

    def __init__(self, provider: EmbeddingProvider, cache_dir: str | Path | None) -> None:
        self.provider = provider
        self.cache_dir = (
            Path(cache_dir) / model_slug(provider.model_id) if cache_dir is not None else None
        )
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, np.ndarray] = {}
        self.last_usage: EmbeddingUsage | None = None

    @property
    def model_id(self) -> str:
        return self.provider.model_id

    @staticmethod
    def key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _load(self, key: str) -> np.ndarray | None:
        vector = self._memory.get(key)
        if vector is not None:
            return vector
        if self.cache_dir is None:
            return None
        path = self.cache_dir / f"{key}.npy"
        if not path.is_file():
            return None
        try:
            vector = np.load(path).astype(np.float32)
        except (OSError, ValueError):
            return None
        self._memory[key] = vector
        return vector

    def _store(self, key: str, vector: np.ndarray) -> None:
        self._memory[key] = vector
        if self.cache_dir is None:
            return
        path = self.cache_dir / f"{key}.npy"
        # numpy appends ".npy" to any other suffix, so the temporary name
        # must already end in it for the rename below to find the file.
        temporary = self.cache_dir / f"{key}.tmp.npy"
        np.save(temporary, vector.astype(np.float32))
        os.replace(temporary, path)

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Vectors for ``texts`` in order; only cache misses reach the provider."""
        started = time.perf_counter()
        keys = [self.key(text) for text in texts]
        found: dict[str, np.ndarray] = {}
        missing: list[str] = []
        for key, text in zip(keys, texts):
            if key in found:
                continue
            vector = self._load(key)
            if vector is None:
                missing.append(key)
            else:
                found[key] = vector
        calls_before = getattr(self.provider, "calls", 0)
        if missing:
            unique_texts = {key: text for key, text in zip(keys, texts) if key in set(missing)}
            order = list(unique_texts)
            vectors = self.provider.embed([unique_texts[key] for key in order])
            for key, vector in zip(order, vectors):
                self._store(key, vector)
                found[key] = vector
        self.last_usage = EmbeddingUsage(
            texts=len(texts),
            cache_hits=len(texts) - len(missing),
            cache_misses=len(missing),
            provider_calls=getattr(self.provider, "calls", 0) - calls_before,
            seconds=round(time.perf_counter() - started, 3),
        )
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        return np.vstack([found[key] for key in keys])


def build_embedding_provider(config: dict[str, Any]) -> EmbeddingProvider:
    """Construct a provider from a plain config mapping (no secrets inside)."""
    kind = str(config.get("provider", "openai_compatible"))
    if kind == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(
            str(config.get("model", DEFAULT_EMBEDDING_MODEL)),
            endpoint=str(config.get("endpoint", DEFAULT_EMBEDDING_ENDPOINT)),
            api_key_env=str(config.get("api_key_env", "OPENROUTER_API_KEY")),
            batch_size=int(config.get("batch_size", 32)),
            timeout_seconds=float(config.get("timeout_seconds", 120.0)),
            dimensions=config.get("dimensions"),
            concurrency=int(config.get("concurrency", 4)),
        )
    if kind == "sentence_transformers":
        return SentenceTransformerEmbeddingProvider(
            str(config["model"]),
            device=str(config.get("device", "cpu")),
            batch_size=int(config.get("batch_size", 16)),
        )
    raise ValueError(f"unknown embedding provider {kind!r}")
