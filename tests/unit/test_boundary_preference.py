"""The labelling instrument, held to its contract.

The window mirror reproduces the structural walk's cuts; items are built
only where the partitions differ (plus deterministic samples of unchanged
windows and smelly forced cuts); the blinding lives in the manifest and
never reaches the form; scoring unblinds; everything is deterministic.
"""

from __future__ import annotations

import json

from amsc.boundary_preference import (
    KIND_CHANGE_GROUP,
    KIND_FORCED_CUT,
    KIND_UNCHANGED_WINDOW,
    WINDOW_FORCED,
    WINDOW_MULTI,
    build_items,
    enumerate_windows,
    main,
    render_form,
    score,
)
from amsc.boundary_quality import QualityConfig
from amsc.structural_chunker import chunk_units as structural_chunk_units

from _chunk_fixtures import WhitespaceCounter, heading, unit, words

COUNTER = WhitespaceCounter()
CONFIG = QualityConfig(min_tokens=50, target_tokens=150, soft_max_tokens=160, hard_max_tokens=1000)


def corpus():
    """Three oversized sections: a multi-candidate one, an identical twin, and
    a forced one whose forced cut lands after a lead-in."""
    units = [heading("h-1", "BIR", 1)]
    order = 2
    for index, prefix in enumerate(("A", "B", "C", "D"), start=1):
        units.append(unit(f"p-1{index}", words(60, prefix), order=order, section=("BIR",)))
        order += 1
    units.append(heading("h-2", "IKI", order))
    order += 1
    for index, prefix in enumerate(("E", "F", "G", "H"), start=1):
        units.append(unit(f"p-2{index}", words(60, prefix), order=order, section=("IKI",)))
        order += 1
    units.append(heading("h-3", "UC", order))
    order += 1
    units.append(unit("p-31", words(99, "I") + " şöyle:", order=order, section=("UC",)))
    order += 1
    units.append(unit("p-32", words(100, "J"), order=order, section=("UC",)))
    order += 1
    units.append(unit("p-33", words(100, "K"), order=order, section=("UC",)))
    return units


def structural(units):
    return structural_chunk_units(
        units, counter=COUNTER, min_tokens=50, target_tokens=150,
        soft_max_tokens=160, hard_max_tokens=1000, respect_semantic_roles=True,
    )


def cut_ids(chunks):
    cuts = set()
    for left, right in zip(chunks, chunks[1:]):
        if left["heading"] == right["heading"]:
            cuts.add(left["unit_ids"][-1])
    return cuts


def test_the_window_mirror_reproduces_the_structural_cuts():
    units = corpus()
    windows = enumerate_windows(units, counter=COUNTER, config=CONFIG)
    assert {window.cut_after_unit_id for window in windows} == cut_ids(structural(units))
    kinds = {window.cut_after_unit_id: window.kind for window in windows}
    assert kinds["p-12"] == WINDOW_MULTI and kinds["p-22"] == WINDOW_MULTI
    assert kinds["p-31"] == WINDOW_FORCED and kinds["p-32"] == WINDOW_FORCED
    multi = next(window for window in windows if window.cut_after_unit_id == "p-12")
    assert multi.candidate_cut_after == ("p-11", "p-12")


def deep_rows(units):
    """Standard's partition with the first section cut one piece earlier."""
    rows = []
    for row in structural(units):
        rows.append(dict(row))
    first, second = rows[0], rows[1]
    assert first["unit_ids"] == ["p-11", "p-12"] and second["unit_ids"] == ["p-13", "p-14"]
    first["unit_ids"], second["unit_ids"] = ["p-11"], ["p-12", "p-13", "p-14"]
    first["token_count"], second["token_count"] = 62, 182
    return rows


def test_items_cover_change_groups_unchanged_windows_and_smelly_forced_cuts():
    units = corpus()
    manifest = build_items(units, structural(units), deep_rows(units), counter=COUNTER, config=CONFIG)
    kinds = manifest["kind_counts"]
    assert kinds == {KIND_CHANGE_GROUP: 1, KIND_UNCHANGED_WINDOW: 1, KIND_FORCED_CUT: 1}
    group = next(item for item in manifest["items"] if item["kind"] == KIND_CHANGE_GROUP)
    assert group["unit_ids"] == ["p-11", "p-12", "p-13", "p-14"]
    assert group["cuts_after"] == {"standard": ["p-12"], "deep": ["p-11"]}
    assert set(group["blinding"].values()) == {"standard", "deep"}
    window = next(item for item in manifest["items"] if item["kind"] == KIND_UNCHANGED_WINDOW)
    assert window["standard_cut_after"] == "p-22" and window["candidates"] == ["p-21", "p-22"]
    forced = next(item for item in manifest["items"] if item["kind"] == KIND_FORCED_CUT)
    assert forced["standard_cut_after"] == "p-31" and forced["smells"] == ["lead_in_cut"]
    assert manifest["window_counts"] == {WINDOW_MULTI: 2, WINDOW_FORCED: 2}


def test_the_form_is_blind_self_contained_and_deterministic():
    units = corpus()
    manifest = build_items(units, structural(units), deep_rows(units), counter=COUNTER, config=CONFIG)
    form = render_form(manifest, units, title="Test")
    assert "blinding" not in form and "deterministic_verdict" not in form
    assert "<script src" not in form and "http" not in form.split("<main>")[1]
    for item in manifest["items"]:
        assert item["item_id"] in form
    assert form.count('<h3>A</h3>') == 1 and form.count('<h3>B</h3>') == 1
    assert form.count("— — — Standard kesimi — — —") == 2  # one per candidate item
    again = render_form(build_items(units, structural(units), deep_rows(units), counter=COUNTER, config=CONFIG), units, title="Test")
    assert again == form


def test_scoring_unblinds_against_the_manifest():
    units = corpus()
    manifest = build_items(units, structural(units), deep_rows(units), counter=COUNTER, config=CONFIG)
    group = next(item for item in manifest["items"] if item["kind"] == KIND_CHANGE_GROUP)
    deep_letter = next(letter for letter, arm in group["blinding"].items() if arm == "deep")
    window = next(item for item in manifest["items"] if item["kind"] == KIND_UNCHANGED_WINDOW)
    forced = next(item for item in manifest["items"] if item["kind"] == KIND_FORCED_CUT)
    labels = {
        "schema_version": "1.0",
        "labels": {
            group["item_id"]: {"preferred": deep_letter, f"acceptable_{deep_letter}": "yes", "reasons": ["lead_in"]},
            window["item_id"]: {"acceptable_standard": "yes", "better_candidate": "none", "reasons": []},
            forced["item_id"]: {"acceptable_standard": "no", "better_candidate": "C1", "reasons": ["lead_in"]},
            "ghost": {"preferred": "A"},
        },
    }
    result = score(labels, manifest)
    assert result["change_groups"]["deep_preferred"] == 1
    assert result["change_groups"]["standard_preferred"] == 0
    assert result["change_groups"]["deep_acceptable"] == 1
    assert result["change_groups"]["preferred_or_equal_rate"] == 1.0
    assert result["change_groups"]["zero_worse_and_n_at_least_60"] is False
    assert result["unchanged_windows"]["standard_acceptable_rate"] == 1.0
    assert result["forced_cuts"]["better_candidate_named"] == 1
    assert result["reasons"] == {"lead_in": 2}
    assert result["unknown_item_ids"] == ["ghost"]


def test_cli_builds_and_scores(tmp_path, capsys):
    units = corpus()
    units_path = tmp_path / "doc.units.jsonl"
    with units_path.open("w", encoding="utf-8") as handle:
        for item in units:
            handle.write(item.model_dump_json(exclude_none=True) + "\n")
    standard_path, deep_path = tmp_path / "standard.jsonl", tmp_path / "deep.jsonl"
    standard_path.write_text("\n".join(json.dumps(r) for r in structural(units)) + "\n", encoding="utf-8")
    deep_path.write_text("\n".join(json.dumps(r) for r in deep_rows(units)) + "\n", encoding="utf-8")
    out = tmp_path / "labels"
    main([
        "build", "--units", str(units_path), "--standard", str(standard_path), "--deep", str(deep_path),
        "--output-dir", str(out), "--min-tokens", "50", "--target-tokens", "150",
        "--soft-max-tokens", "160", "--hard-max-tokens", "1000",
    ])
    manifest = json.loads((out / "items.json").read_text(encoding="utf-8"))
    assert (out / "form.html").is_file() and manifest["kind_counts"][KIND_CHANGE_GROUP] == 1
    labels_path = tmp_path / "labels.json"
    labels_path.write_text(json.dumps({"schema_version": "1.0", "labels": {}}), encoding="utf-8")
    main(["score", "--labels", str(labels_path), "--manifest", str(out / "items.json"), "--output", str(tmp_path / "metrics.json")])
    metrics = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["change_groups"]["labeled"] == 0
    assert capsys.readouterr().out.strip()
