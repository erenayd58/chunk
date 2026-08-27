"""Embedding-assisted arbitration -- a research baseline, not the product mode.

**Scope note (architecture decision).** The product's user-facing modes are
``Standard`` (Structure-only) and ``Deep Analysis`` (Structure + LLM-assisted
chunking, :mod:`amsc.llm_boundary_judge`): boundary decisions on important
documents are made by a *generative* model at backend ingest. This module is
the **embedding-assisted research baseline** kept for comparison -- the
benchmarked "Hybrid" arm behind a switch -- so the three-way study
Structure-only vs Embedding-assisted vs LLM-assisted stays runnable. It is
deliberately **thin**: ``STANDARD`` delegates to
:func:`amsc.structural_chunker.chunk_units` unchanged, ``SEMANTIC_ASSIST``
delegates to :func:`amsc.hybrid_chunker.chunk_units`, whose H1 arbitration is
the embedding-side assist. Nothing is duplicated, so neither path can drift
from the benchmarked arms.

**This is not a confidence or uncertainty detector.** Nothing scores how
"reliable" a structural decision is; there is no threshold and no learned
signal deciding when to ask for help. The eligibility rule is structural and
exact, and it is the greedy splitter's own rule:

**What "ambiguous" means here, and why no confidence score is invented.** The
structure-first chunker is deterministic everywhere except one place: inside a
section that exceeds the soft budget it must pick a cut, and every admissible
cut (inside the greedy rule's own ``[min_tokens, target_tokens]`` window) is
structurally equivalent. That set of admissible cuts *is* the ambiguity --
observable from sizes alone, no scoring involved. Semantic assist is consulted
exactly there and nowhere else: sections that fit are never embedded, and a
section offering no admissible cut falls back to the greedy rule verbatim
(``h1_fallback_section_count`` counts those). :func:`eligible_sections`
computes this surface without any embedder, so a caller can see what the
assist *would* be asked before spending a single embedding call.

The provider contract is :class:`amsc.hybrid_chunker.BoundaryEmbedder` --
``embed_units(texts) -> batch`` whose ``vectors`` are L2-normalised.
:class:`OpenRouterEmbeddingProvider` adapts an OpenAI-compatible embeddings
endpoint to that contract. **Qwen3-Embedding-8B's intended role has moved**:
it is reserved as a future *retrieval* embedding candidate, not the chunking
assist -- the adapter stays because the contract is the same either way. It is
**NOT VERIFIED** against the live service: this environment has no key and the
provider's embedding surface was not probed, so the adapter sticks to the
minimal request shape (``model`` + ``input``), normalises locally rather than
assuming the service does, and fails loudly. The API key is read from the
``OPENROUTER_API_KEY`` environment variable at call time and is never written
to disk, config, or any artifact.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from . import hybrid_chunker, structural_chunker
from .hybrid_chunker import BoundaryEmbedder, _plan_cuts
from .models import EmbeddingBatch, RawDocumentUnit
from .structural_chunker import _sections
from .tokenization import TokenCounter

TUNING_STATUS = "poc_initial_not_optimized"


class ChunkingMode(str, Enum):
    """The user-facing switch. Names are product language, values are stable."""

    STANDARD = "standard"
    SEMANTIC_ASSIST = "semantic_assist"


@dataclass(frozen=True)
class SemanticAssistConfig:
    """PoC toggle configuration. Defaults reproduce the benchmarked arms."""

    mode: ChunkingMode = ChunkingMode.STANDARD
    min_tokens: int = 160
    target_tokens: int = 700
    soft_max_tokens: int = 900
    hard_max_tokens: int = 1126
    respect_semantic_roles: bool = True
    tuning_status: str = TUNING_STATUS


@dataclass(frozen=True)
class ModeResult:
    mode: ChunkingMode
    chunks: list[dict[str, Any]]
    diagnostics: dict[str, Any]


def eligible_sections(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    config: SemanticAssistConfig = SemanticAssistConfig(),
) -> list[dict[str, Any]]:
    """The boundaries semantic assist would be asked about -- embedder-free.

    Reuses the hybrid planner with flat shifts: with every shift equal, the
    argmax's later-cut tie-break reproduces the greedy cut, so the plan walks
    the same boundaries the real arbitration would walk while choosing exactly
    what Standard chooses. What comes back is the ambiguity surface:
    ``ambiguous_boundaries`` (cuts with at least one admissible candidate) and
    ``admissible_candidates`` per oversized section.
    """
    records: list[dict[str, Any]] = []
    for section in _sections(
        units, counter, config.hard_max_tokens, config.respect_semantic_roles
    ):
        if section.tokens <= config.soft_max_tokens:
            continue
        head_cost = counter.count(section.heading) + 2 if section.heading else 0
        plan = _plan_cuts(
            section.pieces,
            head_cost,
            min_tokens=config.min_tokens,
            target_tokens=config.target_tokens,
            shifts=[0.0] * len(section.pieces),
        )
        records.append(
            {
                "heading": section.heading,
                "section_path": list(section.section_path),
                "tokens": section.tokens,
                "piece_count": len(section.pieces),
                "ambiguous_boundaries": plan.arbitrated,
                "admissible_candidates": plan.candidates,
                "greedy_fallback": plan.fallback,
            }
        )
    return records


def chunk_with_mode(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    config: SemanticAssistConfig = SemanticAssistConfig(),
    provider: BoundaryEmbedder | None = None,
) -> ModeResult:
    """Chunk under the selected mode.

    ``STANDARD`` is byte-identical to :func:`structural_chunker.chunk_units`
    and never touches ``provider``. ``SEMANTIC_ASSIST`` requires a provider
    and is byte-identical to the benchmarked hybrid arm (chunk ids aside --
    the underlying chunker names them).
    """
    budgets = dict(
        min_tokens=config.min_tokens,
        target_tokens=config.target_tokens,
        soft_max_tokens=config.soft_max_tokens,
        hard_max_tokens=config.hard_max_tokens,
        respect_semantic_roles=config.respect_semantic_roles,
    )
    if config.mode is ChunkingMode.STANDARD:
        chunks = structural_chunker.chunk_units(units, counter=counter, **budgets)
        return ModeResult(
            mode=config.mode,
            chunks=chunks,
            diagnostics={
                "mode": config.mode.value,
                "semantic_assist": False,
                "tuning_status": config.tuning_status,
            },
        )
    if provider is None:
        raise ValueError(
            "Structure + Semantic Assist needs an embedding provider; "
            "Standard mode does not"
        )
    result = hybrid_chunker.chunk_units(
        units, counter=counter, boundary_embedder=provider, arbitrate=True, **budgets
    )
    return ModeResult(
        mode=config.mode,
        chunks=result.chunks,
        diagnostics={
            "mode": config.mode.value,
            "semantic_assist": True,
            "tuning_status": config.tuning_status,
            **result.diagnostics,
        },
    )


# --------------------------------------------------------------------------
# provider adapter (NOT VERIFIED against the live service)
# --------------------------------------------------------------------------

OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"

#: Adapter status, restated where tooling can read it. The endpoint has not
#: been exercised from this repository; treat the adapter as scaffolding until
#: a real call has been observed.
QWEN_ADAPTER_STATUS = "adapter_only_not_verified"


class OpenRouterEmbeddingProvider:
    """Minimal OpenAI-compatible embeddings adapter for the assist contract.

    Sends only the two parameters every OpenAI-compatible embeddings endpoint
    accepts (``model``, ``input``); assumes nothing else about the provider.
    Vectors are L2-normalised locally because the hybrid arbitration computes
    cosine as a dot product and service-side normalisation is not something to
    take on faith.

    The key comes from ``OPENROUTER_API_KEY`` at request time. It is used in
    the ``Authorization`` header only -- never logged, never returned, never
    persisted.
    """

    status = QWEN_ADAPTER_STATUS

    def __init__(
        self,
        model: str = "qwen/qwen3-embedding-8b",
        *,
        endpoint: str = "https://openrouter.ai/api/v1/embeddings",
        timeout_seconds: float = 60.0,
    ) -> None:
        self.model = model
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def _key(self) -> str:
        key = os.environ.get(OPENROUTER_API_KEY_ENV, "").strip()
        if not key:
            raise RuntimeError(
                f"{OPENROUTER_API_KEY_ENV} is not set; the semantic-assist "
                "provider cannot run without it (and it is never stored)"
            )
        return key

    def embed_units(self, texts: Sequence[str]) -> EmbeddingBatch:
        import numpy as np

        if not texts:
            return EmbeddingBatch(
                vectors=np.empty((0, 0), dtype=np.float32), provenance=()
            )
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps({"model": self.model, "input": list(texts)}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._key()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = payload.get("data")
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise RuntimeError(
                "embedding endpoint returned an unexpected shape; refusing to guess"
            )
        vectors = np.asarray(
            [row["embedding"] for row in sorted(rows, key=lambda r: r.get("index", 0))],
            dtype=np.float32,
        )
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return EmbeddingBatch(vectors=vectors / norms, provenance=())
