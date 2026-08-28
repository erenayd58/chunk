"""The Agentic Chunker, held to its contract.

Load-bearing claims: no votes / all-KEEP / any failure is byte-identical to
the structural chunker; one provider call per planned section segment, all
independent; the model's SPLIT can move a cut but a self-contradictory SPLIT
never creates one; the coherence threshold is exact; replay from the response
cache reproduces the run byte for byte; artifacts carry hashes, never raw
prompt text; and no API key can reach any surface.
"""

from __future__ import annotations

import json
import re

import pytest

from amsc.agentic_chunker import (
    AgenticConfig,
    apply_guard,
    build_artifact,
    coherence_threshold,
    collect_votes,
    run_agentic,
    section_call_plan,
    slice_units_by_pages,
)
from amsc.structural_chunker import chunk_units as structural_chunk_units

from _chunk_fixtures import WhitespaceCounter, heading, unit, words

COUNTER = WhitespaceCounter()

CONFIG = AgenticConfig(
    min_tokens=50,
    target_tokens=150,
    soft_max_tokens=160,
    hard_max_tokens=1000,
    respect_semantic_roles=False,
)

BODIES = [words(60, "a"), words(60, "b"), words(60, "c"), words(60, "d")]
SMALL = words(30, "s")


def corpus():
    units = [heading("h-1", "KUCUK", 1), unit("p-0", SMALL, order=2, section=("KUCUK",))]
    units.append(heading("h-2", "BUYUK", 3))
    for index, body in enumerate(BODIES, start=1):
        units.append(unit(f"p-{index}", body, order=index + 3, section=("BUYUK",)))
    return units


def wide_corpus(piece_words: int, piece_count: int):
    units = [heading("h-2", "BUYUK", 1)]
    for index in range(1, piece_count + 1):
        units.append(
            unit(
                f"p-{index}",
                words(piece_words, f"q{index}v"),
                order=index + 1,
                section=("BUYUK",),
            )
        )
    return units


def structural(units, *, respect=False, min_tokens=50):
    return structural_chunk_units(
        units,
        counter=COUNTER,
        min_tokens=min_tokens,
        target_tokens=150,
        soft_max_tokens=160,
        hard_max_tokens=1000,
        respect_semantic_roles=respect,
    )


def texts(chunks):
    """Chunk ids differ by arm prefix; content equality is what matters."""
    return [
        (chunk["text"], chunk["unit_ids"], chunk["token_count"], chunk["heading"])
        for chunk in chunks
    ]


class FakeProvider:
    model_id = "test:fake-agentic@1"

    def __init__(self, answer):
        self.answer = answer
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answer(prompt) if callable(self.answer) else self.answer


CANDIDATE_MARKER = re.compile(r"\[CANDIDATE (C\d+) \| cut before \w+ ([\w#-]+)\]")


def scripted(decide):
    def answer(prompt):
        rows = []
        for candidate_id, unit_id in CANDIDATE_MARKER.findall(prompt):
            decision, reason = decide(candidate_id, unit_id)
            rows.append(
                {"candidate_id": candidate_id, "decision": decision, "reason_code": reason}
            )
        return json.dumps(rows)

    return answer


KEEP_ALL = scripted(lambda cid, uid: ("KEEP", "CONTINUATION"))
SPLIT_ALL = scripted(lambda cid, uid: ("SPLIT", "TOPIC_SHIFT"))


def split_before(target_unit_id, reason="TOPIC_SHIFT"):
    return scripted(
        lambda cid, uid: ("SPLIT", reason)
        if uid == target_unit_id
        else ("KEEP", "CONTINUATION")
    )


# --- the deterministic floor -------------------------------------------------


def test_no_provider_is_byte_identical_to_structure_only():
    run = run_agentic(corpus(), counter=COUNTER, provider=None, config=CONFIG)
    assert texts(run.result.chunks) == texts(structural(corpus()))
    assert run.result.chunks[0]["chunk_id"].endswith("a-chunk-0001")
    assert run.diagnostics["provider_call_count"] == 0
    assert run.diagnostics["replay_miss_call_count"] == len(run.plan.calls)


def test_an_all_keep_model_changes_nothing():
    provider = FakeProvider(KEEP_ALL)
    run = run_agentic(corpus(), counter=COUNTER, provider=provider, config=CONFIG)

    assert texts(run.result.chunks) == texts(structural(corpus()))
    assert run.diagnostics["changed_from_greedy_count"] == 0
    assert all(w.fallback == "forced_greedy_all_keep" for w in run.result.window_audit)


def test_garbage_and_raising_providers_fall_back_to_structural():
    garbage = run_agentic(
        corpus(), counter=COUNTER, provider=FakeProvider("elbette!"), config=CONFIG
    )
    assert texts(garbage.result.chunks) == texts(structural(corpus()))
    assert garbage.diagnostics["parse_error_call_count"] == 1

    class Broken(FakeProvider):
        def complete(self, prompt):
            raise RuntimeError("gateway down")

    broken = run_agentic(
        corpus(), counter=COUNTER, provider=Broken(KEEP_ALL), config=CONFIG
    )
    assert texts(broken.result.chunks) == texts(structural(corpus()))
    assert broken.diagnostics["provider_error_call_count"] == 1


# --- call plan ---------------------------------------------------------------


def test_one_call_per_section_covers_all_non_label_boundaries():
    provider = FakeProvider(KEEP_ALL)
    run = run_agentic(corpus(), counter=COUNTER, provider=provider, config=CONFIG)

    # The small section is never called; the oversized one gets ONE call
    # marking all three internal boundaries (not only the admissible two).
    assert len(provider.prompts) == 1
    assert run.diagnostics["planned_call_count"] == 1
    markers = CANDIDATE_MARKER.findall(provider.prompts[0])
    assert [unit_id for _, unit_id in markers] == ["p-2", "p-3", "p-4"]
    assert SMALL not in provider.prompts[0]


def test_a_section_whose_dry_walk_offers_no_choice_is_never_called():
    # min_tokens=100 leaves exactly one admissible stop at the overflow.
    config = AgenticConfig(**{**CONFIG.__dict__, "min_tokens": 100})
    units = [heading("h-2", "BUYUK", 1)]
    for index in range(1, 4):
        units.append(
            unit(f"p-{index}", BODIES[index - 1], order=index + 1, section=("BUYUK",))
        )
    provider = FakeProvider(SPLIT_ALL)
    run = run_agentic(units, counter=COUNTER, provider=provider, config=config)

    assert provider.prompts == []
    assert run.diagnostics["planned_call_count"] == 0
    assert texts(run.result.chunks) == texts(structural(units, min_tokens=100))


def test_a_label_seam_is_never_a_candidate_and_needs_no_call():
    from amsc.models import RawDocumentUnit, UnitType

    label = RawDocumentUnit(
        document_id="doc",
        unit_id="h-9",
        order=4,
        text="ARA ETIKET",
        type=UnitType.HEADING,
        heading_level=3,
        section_path=["BUYUK"],
        semantic_role="item",
        opens_section=False,
    )
    units = [heading("h-2", "BUYUK", 1)]
    units.append(unit("p-1", BODIES[0], order=2, section=("BUYUK",)))
    units.append(unit("p-2", BODIES[1], order=3, section=("BUYUK",)))
    units.append(label)
    units.append(unit("p-3", BODIES[2], order=5, section=("BUYUK",)))

    config = AgenticConfig(**{**CONFIG.__dict__, "respect_semantic_roles": True})
    provider = FakeProvider(SPLIT_ALL)
    run = run_agentic(units, counter=COUNTER, provider=provider, config=config)

    # The only cut is the label seam: structure's own, no window, no call.
    assert provider.prompts == []
    assert texts(run.result.chunks) == texts(structural(units, respect=True))


# --- votes steering the walk -------------------------------------------------


def test_a_split_vote_moves_the_cut_with_a_single_call():
    provider = FakeProvider(split_before("p-2"))
    run = run_agentic(corpus(), counter=COUNTER, provider=provider, config=CONFIG)

    big = [c for c in run.result.chunks if c["heading"] == "BUYUK"]
    assert [c["unit_ids"] for c in big] == [["p-1"], ["p-2", "p-3"], ["p-4"]]
    assert run.diagnostics["changed_from_greedy_count"] == 1
    # Two decision windows open during the walk, but the section was asked
    # ONCE up front -- this is the batching win over the sequential judge.
    assert run.diagnostics["decision_window_count"] == 2
    assert len(provider.prompts) == 1


def test_among_several_splits_the_latest_wins():
    provider = FakeProvider(SPLIT_ALL)
    run = run_agentic(corpus(), counter=COUNTER, provider=provider, config=CONFIG)

    assert texts(run.result.chunks) == texts(structural(corpus()))
    assert run.diagnostics["changed_from_greedy_count"] == 0


def test_steering_keeps_the_hard_cap_and_full_coverage():
    units = wide_corpus(7, 24)
    provider = FakeProvider(split_before("p-8"))
    run = run_agentic(units, counter=COUNTER, provider=provider, config=CONFIG)

    assert run.diagnostics["changed_from_greedy_count"] == 1
    assert texts(run.result.chunks) != texts(structural(units))
    assert all(c["token_count"] <= CONFIG.hard_max_tokens for c in run.result.chunks)
    covered = [uid for c in run.result.chunks for uid in c["unit_ids"]]
    assert covered == [u.unit_id for u in units if not u.unit_id.startswith("h-")]


# --- the coherence guard -----------------------------------------------------


def test_coherence_threshold_pins():
    config = AgenticConfig()
    assert coherence_threshold(3, config) == 2
    assert coherence_threshold(10, config) == 2
    assert coherence_threshold(24, config) == 5
    custom = AgenticConfig(coherence_min_violations=1, coherence_violation_ratio=0.5)
    assert coherence_threshold(3, custom) == 2  # ceil(1.5)


def test_a_contradictory_split_is_demoted_and_never_creates_a_cut():
    provider = FakeProvider(split_before("p-2", reason="LIST_CONTINUATION"))
    run = run_agentic(corpus(), counter=COUNTER, provider=provider, config=CONFIG)

    assert texts(run.result.chunks) == texts(structural(corpus()))
    assert run.diagnostics["demoted_vote_count"] == 1
    assert run.diagnostics["coherence_rejected_call_count"] == 0
    first = run.result.window_audit[0]
    assert first.fallback == "forced_greedy_after_coherence"
    demoted = [d for d in first.decisions if d["effective"] == "ABSTAIN"]
    assert demoted and demoted[0]["decision_raw"] == "SPLIT"
    assert demoted[0]["reason_code"] == "LIST_CONTINUATION"


def test_demotions_at_the_threshold_pass_and_one_more_rejects_the_call():
    # corpus() offers 3 candidates -> threshold max(2, ceil(0.6)) == 2.
    def demote_first(count):
        state = {"seen": 0}

        def decide(cid, uid):
            state["seen"] += 1
            if state["seen"] <= count:
                return ("SPLIT", "LIST_CONTINUATION")
            return ("KEEP", "CONTINUATION")

        return scripted(decide)

    at_threshold = run_agentic(
        corpus(), counter=COUNTER, provider=FakeProvider(demote_first(2)), config=CONFIG
    )
    assert at_threshold.diagnostics["coherence_rejected_call_count"] == 0
    assert at_threshold.diagnostics["demoted_vote_count"] == 2

    over_threshold = run_agentic(
        corpus(), counter=COUNTER, provider=FakeProvider(demote_first(3)), config=CONFIG
    )
    assert over_threshold.diagnostics["coherence_rejected_call_count"] == 1
    assert over_threshold.diagnostics["demoted_vote_count"] == 0
    assert texts(over_threshold.result.chunks) == texts(structural(corpus()))
    assert over_threshold.call_audit[0].status == "coherence_violation"


def test_an_incoherent_keep_passes_through_and_is_only_counted():
    provider = FakeProvider(scripted(lambda cid, uid: ("KEEP", "TOPIC_SHIFT")))
    run = run_agentic(corpus(), counter=COUNTER, provider=provider, config=CONFIG)

    assert texts(run.result.chunks) == texts(structural(corpus()))
    assert run.diagnostics["incoherent_keep_count"] == 3
    assert run.diagnostics["coherence_rejected_call_count"] == 0


# --- segmentation ------------------------------------------------------------


def test_segments_partition_the_candidates_and_fire_separately():
    config = AgenticConfig(**{**CONFIG.__dict__, "max_candidates_per_call": 4})
    units = wide_corpus(20, 9)  # 8 non-label boundaries -> two segments
    provider = FakeProvider(KEEP_ALL)
    run = run_agentic(units, counter=COUNTER, provider=provider, config=config)

    assert len(provider.prompts) == 2
    seen = [uid for prompt in provider.prompts for _, uid in CANDIDATE_MARKER.findall(prompt)]
    assert seen == [f"p-{i}" for i in range(2, 10)]  # each boundary exactly once
    assert texts(run.result.chunks) == texts(structural(units))


def test_a_broken_segment_loses_only_its_own_votes():
    config = AgenticConfig(**{**CONFIG.__dict__, "max_candidates_per_call": 4})
    units = wide_corpus(20, 9)

    def answer(prompt):
        markers = CANDIDATE_MARKER.findall(prompt)
        if markers and markers[0][1] == "p-2":  # first segment answers well
            return scripted(
                lambda cid, uid: ("SPLIT", "TOPIC_SHIFT")
                if uid == "p-4"
                else ("KEEP", "CONTINUATION")
            )(prompt)
        return "bozuk cevap"  # second segment fails to parse

    run = run_agentic(units, counter=COUNTER, provider=FakeProvider(answer), config=config)

    assert run.diagnostics["parse_error_call_count"] == 1
    # The SPLIT from the healthy first segment still steers the cut.
    assert run.diagnostics["changed_from_greedy_count"] == 1
    assert run.result.window_audit[0].chosen_after_unit_id == "p-3"


def test_an_unfittable_single_candidate_region_stays_unvoted():
    long_words = " ".join(f"w{'x' * 40}{i}" for i in range(60))
    units = [heading("h-2", "BUYUK", 1)]
    for index in range(1, 4):
        units.append(unit(f"p-{index}", long_words, order=index + 1, section=("BUYUK",)))
    config = AgenticConfig(**{**CONFIG.__dict__, "max_prompt_chars": 1000})
    provider = FakeProvider(SPLIT_ALL)
    run = run_agentic(units, counter=COUNTER, provider=provider, config=config)

    assert provider.prompts == []  # every segment bisected down and dropped
    assert run.diagnostics["dropped_candidate_count"] > 0
    assert texts(run.result.chunks) == texts(structural(units))


# --- replay and determinism --------------------------------------------------


def test_replay_from_the_response_cache_is_byte_identical():
    provider = FakeProvider(split_before("p-2"))
    live = run_agentic(corpus(), counter=COUNTER, provider=provider, config=CONFIG)

    cache = {
        call.prompt_sha256: outcome.response
        for call, outcome in zip(live.plan.calls, live.outcomes)
        if outcome.response is not None
    }
    replay = run_agentic(
        corpus(), counter=COUNTER, provider=None, config=CONFIG, cache=cache
    )

    assert replay.result.chunks == live.result.chunks
    assert replay.result.window_audit == live.result.window_audit
    assert replay.diagnostics["cache_hit_count"] == 1
    assert replay.diagnostics["provider_call_count"] == 0


def test_the_run_is_deterministic():
    def snapshot():
        run = run_agentic(
            corpus(),
            counter=COUNTER,
            provider=FakeProvider(split_before("p-2")),
            config=CONFIG,
        )
        return json.dumps(
            {
                "chunks": run.result.chunks,
                "windows": [w.__dict__ | {"decisions": list(w.decisions)} for w in run.result.window_audit],
                "diagnostics": run.diagnostics,
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )

    assert snapshot() == snapshot()


def test_the_prompt_set_is_stable_for_the_same_canonical_and_config():
    once = section_call_plan(corpus(), counter=COUNTER, config=CONFIG)
    twice = section_call_plan(corpus(), counter=COUNTER, config=CONFIG)
    assert [c.prompt_sha256 for c in once.calls] == [c.prompt_sha256 for c in twice.calls]
    # A config change may legitimately change the plan -- the claim is
    # deliberately narrow, and the hash key protects the cache.
    smaller = AgenticConfig(**{**CONFIG.__dict__, "max_candidates_per_call": 2})
    other = section_call_plan(corpus(), counter=COUNTER, config=smaller)
    assert [c.prompt_sha256 for c in other.calls] != [c.prompt_sha256 for c in once.calls]


# --- helpers -----------------------------------------------------------------


def test_slice_units_by_pages_filters_without_rewriting():
    from amsc.models import SourceSpan

    units = [
        unit("p-1", "bir", order=1),
        unit("p-2", "iki", order=2),
        unit("p-3", "uc", order=3),
    ]
    units[0] = units[0].model_copy(update={"source": SourceSpan(page=67)})
    units[1] = units[1].model_copy(update={"source": SourceSpan(page=68)})
    units[2] = units[2].model_copy(update={"source": SourceSpan(page=75)})
    sliced = slice_units_by_pages(units, 68, 75)
    assert [u.unit_id for u in sliced] == ["p-2", "p-3"]
    assert sliced[0] is units[1]
    with pytest.raises(ValueError, match="widen the range"):
        slice_units_by_pages(units, 90, 99)


# --- the artifact builder ----------------------------------------------------


def write_units(tmp_path, units):
    path = tmp_path / "doc.units.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for u in units:
            handle.write(u.model_dump_json(exclude_none=True))
            handle.write("\n")
    return path


def corpus_with_pages():
    from amsc.models import SourceSpan

    units = corpus()
    return [
        u.model_copy(update={"source": SourceSpan(page=1 + (i // 3))})
        for i, u in enumerate(units)
    ]


def test_build_artifact_writes_hashes_not_prompts(tmp_path, monkeypatch):
    sentinel = "sk-AGENTIC-SENTINEL-NEVER-PERSIST"
    monkeypatch.setenv("OPENROUTER_API_KEY", sentinel)
    units_path = write_units(tmp_path, corpus_with_pages())
    output = tmp_path / "artifacts" / "agentic" / "doc"

    build_artifact(
        units_path=units_path,
        output=output,
        provider=FakeProvider(split_before("p-2")),
        config=CONFIG,
        counter=COUNTER,
    )

    for name in (
        "agentic/chunks.jsonl",
        "agentic/mapping.json",
        "judge/calls.jsonl",
        "judge/responses.jsonl",
        "judge/audit.jsonl",
        "judge/summary.json",
        "boundary-diff.json",
        "resolved-config.json",
        "manifest.json",
    ):
        assert (output / name).is_file(), name

    calls_text = (output / "judge" / "calls.jsonl").read_text(encoding="utf-8")
    assert "prompt_sha256" in calls_text
    assert "Text (excerpts" not in calls_text  # raw prompt never persisted
    assert BODIES[0][:40] not in calls_text  # no corpus text either

    whole_tree = "".join(
        p.read_text(encoding="utf-8") for p in sorted(output.rglob("*")) if p.is_file()
    )
    assert sentinel not in whole_tree
    assert "openrouter.ai" not in whole_tree  # no endpoint in artifacts

    diff = json.loads((output / "boundary-diff.json").read_text(encoding="utf-8"))
    assert diff["summary"]["moved"] == 1

    # Replay: same tree rebuilt from the response cache, no provider.
    replay_output = tmp_path / "artifacts" / "agentic" / "doc"
    before = (output / "agentic" / "chunks.jsonl").read_bytes()
    build_artifact(
        units_path=units_path,
        output=replay_output,
        provider=None,
        config=CONFIG,
        counter=COUNTER,
        replay=True,
    )
    assert (replay_output / "agentic" / "chunks.jsonl").read_bytes() == before


def test_build_artifact_refuses_frozen_surfaces(tmp_path):
    units_path = write_units(tmp_path, corpus_with_pages())
    with pytest.raises(ValueError, match="evaluation/"):
        build_artifact(
            units_path=units_path,
            output=tmp_path / "evaluation" / "agentic",
            provider=None,
            config=CONFIG,
            counter=COUNTER,
        )
    frozen = tmp_path / "bench"
    frozen.mkdir()
    (frozen / "benchmark-summary.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen benchmark tree"):
        build_artifact(
            units_path=units_path,
            output=frozen / "agentic",
            provider=None,
            config=CONFIG,
            counter=COUNTER,
        )
    with pytest.raises(ValueError, match="outside the artifact tree"):
        build_artifact(
            units_path=units_path,
            output=tmp_path / "out",
            provider=None,
            config=CONFIG,
            counter=COUNTER,
            dump_prompts=tmp_path / "out" / "prompts",
        )
