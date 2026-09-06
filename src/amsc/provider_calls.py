"""Calling a generative provider: the transport, and many calls at once.

The product path -- Deep Analysis's proposer and verifier -- needs two things
from a generative model, and neither of them is a chunking decision:

* a way to send one bounded prompt and get text back
  (:class:`BoundaryJudgeModel`, and :class:`OpenAICompatibleJudgeProvider` as
  the one shipped implementation of it);
* a way to make many such calls concurrently, answering from a cache where it
  can and never letting one failure take the batch down
  (:func:`collect_votes`).

Both lived inside research modules until Phase 8: the protocol and the
transport in :mod:`amsc.llm_boundary_judge` (the superseded v1 per-boundary
judge) and the call machinery in :mod:`amsc.agentic_chunker` (the Agentic
research arm). Product code therefore imported two large research modules to
reach a few hundred lines of infrastructure, which is what kept both of them
on the product path. They are here now, and both research arms import them
from here, so the boundary follows the code rather than the history.

Nothing in this module knows what a chunk is. It transports prompts.
"""

from __future__ import annotations

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence


class BoundaryJudgeModel(Protocol):
    """A generative model that answers one bounded prompt with text.

    Provider-agnostic on purpose: anything that can complete a prompt --
    an OpenAI-compatible endpoint, a MiniMax-class company model, a test
    double -- fits. The caller builds the prompt and parses the answer; the
    provider only transports.
    """

    @property
    def model_id(self) -> str: ...

    def complete(self, prompt: str) -> str: ...


class PlannedProviderCall(Protocol):
    """What :func:`collect_votes` needs of a planned call, and no more.

    Deep Analysis's proposer and verifier each plan their own call shape;
    what they share is an id, a prompt and the prompt's digest. Stating that
    as a protocol is why three unrelated plan classes can go through one
    scheduler without inheriting from anything.
    """

    @property
    def call_id(self) -> str: ...

    @property
    def prompt(self) -> str: ...

    @property
    def prompt_sha256(self) -> str: ...


# --------------------------------------------------------------------------
# parallel collection (cache-first, provider optional)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CallOutcome:
    call_id: str
    status: str  # ok | cached | provider_error | replay_miss
    response: str | None


def collect_votes(
    calls: Sequence[PlannedProviderCall],
    *,
    provider: BoundaryJudgeModel | None,
    cache: Mapping[str, str] | None = None,
    concurrency: int = 8,
) -> list[CallOutcome]:
    """One ``complete()`` per planned call; independent, so concurrent.

    ``cache`` maps prompt_sha256 to a raw response; hits never reach the
    provider. With ``provider=None`` (replay) a miss becomes
    ``replay_miss`` -- deterministically equivalent to the original run's
    provider error. Results are assembled in plan order regardless of
    completion order.
    """
    cache = cache or {}
    outcomes: dict[str, CallOutcome] = {}
    to_call: list[PlannedProviderCall] = []
    for call in calls:
        if call.prompt_sha256 in cache:
            outcomes[call.call_id] = CallOutcome(
                call.call_id, "cached", cache[call.prompt_sha256]
            )
        elif provider is None:
            outcomes[call.call_id] = CallOutcome(call.call_id, "replay_miss", None)
        else:
            to_call.append(call)

    def run(call: PlannedProviderCall) -> CallOutcome:
        try:
            return CallOutcome(call.call_id, "ok", provider.complete(call.prompt))
        except Exception:
            return CallOutcome(call.call_id, "provider_error", None)

    if to_call:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            for outcome in pool.map(run, to_call):
                outcomes[outcome.call_id] = outcome
    return [outcomes[call.call_id] for call in calls]


def load_response_cache(path: Path) -> dict[str, str]:
    """The ``prompt_sha256 -> response`` map a run wrote, for replay.

    The exact shape :func:`collect_votes` takes as ``cache``: a missing file
    is an empty cache, so a replay with no recorded answers is a run of
    ``replay_miss`` rather than an error.
    """
    cache: dict[str, str] = {}
    if not path.is_file():
        return cache
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cache[row["prompt_sha256"]] = row["response"]
    return cache


# --------------------------------------------------------------------------
# provider adapter (backend-only; NOT VERIFIED against any live service)
# --------------------------------------------------------------------------

JUDGE_ADAPTER_STATUS = "adapter_only_not_verified"


class OpenAICompatibleJudgeProvider:
    """Chat-completions transport for the judge. Backend ingest only.

    No model is hardcoded: ``model`` is required, and the key's environment
    variable name is configurable so a company deployment (a MiniMax-class
    model behind a different gateway) needs no code change. Only the minimal
    OpenAI-compatible payload is sent (``model`` + ``messages``); nothing else
    about the provider is assumed. The key is read from the environment at
    request time, used in the Authorization header, and never persisted.
    """

    status = JUDGE_ADAPTER_STATUS

    def __init__(
        self,
        model: str,
        *,
        endpoint: str,
        api_key_env: str = "OPENROUTER_API_KEY",
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model = model
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    @property
    def model_id(self) -> str:
        return self.model

    def _key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise RuntimeError(
                f"{self.api_key_env} is not set; the boundary judge cannot run "
                "without it (and it is never stored)"
            )
        return key

    def complete(self, prompt: str) -> str:
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(
                {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._key()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError(
                "judge endpoint returned an unexpected shape; refusing to guess"
            ) from error
