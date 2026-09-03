"""How many provider calls a Deep Analysis run has in flight, and when.

The product sizes the proposer and verifier pools from one setting
(``DeepAnalysisSettings.concurrency``); nothing pinned that the setting is a
real bound, or that the two phases run one after the other rather than at
once. Both facts decide what N simultaneous documents cost a gateway, so they
are pinned here as behaviour a future job model must keep. What is
deliberately *not* pinned is the absence of a process-wide limit -- that is a
gap to close, not a contract to protect.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import json
import re

from amsc import deep_pipeline as pipe
from amsc.agentic_chunker import collect_votes

from test_deep_pipeline import CONFIG, COUNTER, corpus


class ForbiddingProvider:
    """Votes against every marked boundary and calls every verifier
    comparison a tie: the proposal then differs from the deterministic
    baseline, which is what gives the verifier a change group to judge."""

    model_id = "test:forbidding@1"

    def complete(self, prompt: str) -> str:
        if "DIVISION ONE" in prompt:
            return '{"better": "EQUAL"}'
        labels = sorted(set(re.findall(r"\[(B\d+)\]", prompt)))
        rows = [
            {"id": label, "strength": 0, "before": "introduces_next", "after": "continues_previous"}
            for label in labels
        ]
        return json.dumps({"boundaries": rows})


@dataclass(frozen=True)
class _Call:
    call_id: str
    prompt: str
    prompt_sha256: str


class InFlightMeter:
    """A provider that counts how many of its calls overlap.

    Each call waits until ``expected`` calls are in flight (or a timeout),
    so with a pool of that size every worker is provably busy at once, and a
    pool any larger would be caught with more in flight than allowed.
    """

    model_id = "test:in-flight@1"

    def __init__(self, expected: int):
        self.expected = expected
        self.in_flight = 0
        self.peak = 0
        self.lock = threading.Lock()
        self.full = threading.Condition(self.lock)

    def complete(self, prompt: str) -> str:
        with self.lock:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
            self.full.notify_all()
            self.full.wait_for(lambda: self.peak >= self.expected, timeout=2.0)
        try:
            return "{}"
        finally:
            with self.lock:
                self.in_flight -= 1


def test_the_concurrency_setting_bounds_one_documents_provider_calls():
    calls = [_Call(f"c{i}", f"prompt {i}", f"sha{i}") for i in range(12)]
    meter = InFlightMeter(expected=3)

    outcomes = collect_votes(calls, provider=meter, concurrency=3)

    assert meter.peak == 3, "the pool is exactly the setting: fully used, never exceeded"
    assert [o.status for o in outcomes] == ["ok"] * 12
    assert [o.call_id for o in outcomes] == [c.call_id for c in calls], "plan order, not completion order"


def test_cached_prompts_never_reach_the_provider():
    calls = [_Call(f"c{i}", f"prompt {i}", f"sha{i}") for i in range(4)]
    meter = InFlightMeter(expected=1)
    cache = {"sha1": "cached-answer", "sha3": "cached-answer"}

    outcomes = collect_votes(calls, provider=meter, cache=cache, concurrency=8)

    assert [o.status for o in outcomes] == ["ok", "cached", "ok", "cached"]
    assert meter.peak <= 2, "only the two uncached calls were made"


class PhaseRecorder:
    """Wraps a provider and records, per call, which phase it served and
    when it started and finished, on one shared timeline."""

    def __init__(self, phase: str, inner, timeline: list, lock: threading.Lock):
        self.phase, self.inner, self.timeline, self.lock = phase, inner, timeline, lock
        self.model_id = f"test:{phase}@1"

    def complete(self, prompt: str) -> str:
        with self.lock:
            self.timeline.append((self.phase, "start", len(self.timeline)))
        try:
            return self.inner.complete(prompt)
        finally:
            with self.lock:
                self.timeline.append((self.phase, "end", len(self.timeline)))


def test_the_verifier_starts_only_after_every_proposer_call_has_returned():
    """Proposer and verifier are two pools run one after the other, not one
    pool of twice the size: a document never has more than ``concurrency``
    provider calls in flight, whichever phase it is in."""
    timeline: list = []
    lock = threading.Lock()
    proposer = PhaseRecorder("proposer", ForbiddingProvider(), timeline, lock)
    verifier = PhaseRecorder("verifier", ForbiddingProvider(), timeline, lock)
    settings = pipe.DeepAnalysisSettings(config=CONFIG, use_llm=True, verify=True, concurrency=4,
                                         api_key_env="AMSC_TEST_KEY_THAT_IS_UNSET")

    result = pipe.chunk_document(corpus(), mode="deep", settings=settings, counter=COUNTER,
                                 provider=proposer, verifier_provider=verifier)

    proposer_calls = [t for t in timeline if t[0] == "proposer"]
    verifier_calls = [t for t in timeline if t[0] == "verifier"]
    assert proposer_calls, "the corpus produced proposer calls"
    assert verifier_calls, "and change groups for the verifier to judge"
    assert result.report["verifier"]["group_count"] > 0
    last_proposer_end = max(t[2] for t in proposer_calls if t[1] == "end")
    first_verifier_start = min(t[2] for t in verifier_calls if t[1] == "start")
    assert last_proposer_end < first_verifier_start
    assert result.report["proposer"]["call_count"] == len(proposer_calls) // 2
    assert 2 * result.report["verifier"]["group_count"] == len(verifier_calls) // 2, (
        "two verifier calls per change group (both presentation orders)"
    )
