"""The provider transport and the parallel-call machinery, on their own.

Both were product infrastructure living inside research modules until Phase 8:
the transport in ``amsc.llm_boundary_judge`` (the superseded v1 judge) and the
call scheduler in ``amsc.agentic_chunker`` (the Agentic research arm). Deep
Analysis needed them and therefore imported both arms, which is what kept two
large research modules on the product path.

What these tests hold:

* the adapter's own contract -- marked unverified, no model hardcoded, the
  key's variable configurable and a missing key loud. Moved here unchanged
  from ``test_llm_boundary_judge.py``;
* the scheduler's contract at the seam Deep Analysis relies on: a cache hit
  never reaches the provider, ``provider=None`` is a deterministic replay,
  one call's failure does not take the batch down, and results come back in
  plan order however they completed;
* that the two research arms still see the same objects under their own
  names, because their tests and their artifacts refer to them that way.
"""

from __future__ import annotations

import json

import pytest

from amsc.provider_calls import (
    JUDGE_ADAPTER_STATUS,
    CallOutcome,
    OpenAICompatibleJudgeProvider,
    collect_votes,
    load_response_cache,
)


class Call:
    """The whole of what ``collect_votes`` asks of a planned call."""

    def __init__(self, call_id: str, prompt: str) -> None:
        self.call_id = call_id
        self.prompt = prompt
        self.prompt_sha256 = f"sha-{prompt}"


class Provider:
    model_id = "test:provider@1"

    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.seen: list[str] = []
        self.fail_on = fail_on or set()

    def complete(self, prompt: str) -> str:
        self.seen.append(prompt)
        if prompt in self.fail_on:
            raise RuntimeError("provider said no")
        return f"answer-{prompt}"


# --- the adapter and the key ------------------------------------------------


def test_the_adapter_is_marked_not_verified_and_hardcodes_no_model():
    assert OpenAICompatibleJudgeProvider.status == JUDGE_ADAPTER_STATUS
    with pytest.raises(TypeError):
        OpenAICompatibleJudgeProvider(endpoint="https://example.invalid/v1")  # model required


def test_the_key_env_is_configurable_and_a_missing_key_is_loud(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    provider = OpenAICompatibleJudgeProvider(
        "company/minimax-class-model",
        endpoint="https://gateway.example.invalid/v1/chat/completions",
        api_key_env="MINIMAX_API_KEY",
    )
    with pytest.raises(RuntimeError, match="MINIMAX_API_KEY"):
        provider.complete("prompt")


# --- collecting many calls --------------------------------------------------


def test_a_cache_hit_never_reaches_the_provider():
    provider = Provider()
    calls = [Call("c1", "p1"), Call("c2", "p2")]

    outcomes = collect_votes(
        calls, provider=provider, cache={"sha-p1": "cached-answer"}
    )

    assert provider.seen == ["p2"]
    assert outcomes[0] == CallOutcome("c1", "cached", "cached-answer")
    assert outcomes[1] == CallOutcome("c2", "ok", "answer-p2")


def test_replay_without_a_provider_is_deterministic():
    """``provider=None`` is the replay mode: a miss is ``replay_miss``, which
    the parser treats exactly as the original run's provider error."""
    calls = [Call("c1", "p1"), Call("c2", "p2")]

    outcomes = collect_votes(calls, provider=None, cache={"sha-p1": "recorded"})

    assert [(o.call_id, o.status) for o in outcomes] == [
        ("c1", "cached"), ("c2", "replay_miss"),
    ]
    assert outcomes[1].response is None


def test_one_failing_call_does_not_take_the_batch_down():
    provider = Provider(fail_on={"p2"})
    calls = [Call("c1", "p1"), Call("c2", "p2"), Call("c3", "p3")]

    outcomes = collect_votes(calls, provider=provider, concurrency=3)

    assert [(o.call_id, o.status) for o in outcomes] == [
        ("c1", "ok"), ("c2", "provider_error"), ("c3", "ok"),
    ]


def test_results_come_back_in_plan_order():
    """Order is the plan's, not the completion order -- the artifacts and the
    strict parser both index by position."""
    calls = [Call(f"c{n}", f"p{n}") for n in range(8)]

    outcomes = collect_votes(calls, provider=Provider(), concurrency=8)

    assert [o.call_id for o in outcomes] == [call.call_id for call in calls]


# --- the recorded cache -----------------------------------------------------


def test_a_missing_cache_file_is_an_empty_cache(tmp_path):
    assert load_response_cache(tmp_path / "nothing.jsonl") == {}


def test_the_cache_file_is_read_as_the_map_collect_votes_takes(tmp_path):
    path = tmp_path / "responses.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"prompt_sha256": f"sha-p{n}", "response": f"recorded-{n}"})
            for n in (1, 2)
        )
        + "\n\n",  # a trailing blank line is not a row
        encoding="utf-8",
    )

    cache = load_response_cache(path)

    assert cache == {"sha-p1": "recorded-1", "sha-p2": "recorded-2"}
    outcomes = collect_votes([Call("c1", "p1")], provider=None, cache=cache)
    assert outcomes[0] == CallOutcome("c1", "cached", "recorded-1")


# --- what the research arms still see --------------------------------------


def test_both_research_arms_still_reach_these_under_their_own_names():
    """The Agentic arm's tests and the v1 judge's docstrings name these on the
    modules they used to live in; the move must not have renamed anything."""
    from amsc import agentic_chunker, llm_boundary_judge, provider_calls

    assert agentic_chunker.collect_votes is provider_calls.collect_votes
    assert agentic_chunker.CallOutcome is provider_calls.CallOutcome
    assert agentic_chunker.load_response_cache is provider_calls.load_response_cache
    assert (
        agentic_chunker.OpenAICompatibleJudgeProvider
        is provider_calls.OpenAICompatibleJudgeProvider
    )
    assert llm_boundary_judge.BoundaryJudgeModel is provider_calls.BoundaryJudgeModel


def test_the_transport_knows_nothing_about_chunking():
    """The reason this module exists: it must not grow a chunking dependency,
    or the two arms come back onto the product path with it."""
    import ast
    from pathlib import Path

    source = Path(provider_calls_path()).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.level:
            imported.add(node.module or "")
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}

    assert not any(name.startswith("amsc") for name in imported), imported
    assert imported <= {"__future__", "json", "os", "urllib", "concurrent",
                        "dataclasses", "pathlib", "typing"}, imported


def provider_calls_path() -> str:
    from amsc import provider_calls

    return provider_calls.__file__
