"""The decision story a Deep tree is packaged with.

Held to hand-computable cases: a section the contract improved names the
smell it removed; a section nothing touched is ``standard_kept``; every
final boundary has exactly one origin; and the packaged arm pins the
canonical it was built from.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from amsc import deep_analysis as da
from amsc import deep_arm
from amsc import deep_pipeline as pipe
from amsc.deep_run import write_tree
from amsc.models import UnitType

from _chunk_fixtures import WhitespaceCounter, heading, unit, words

COUNTER = WhitespaceCounter()
CONFIG = da.DeepConfig(min_tokens=50, target_tokens=150, soft_max_tokens=160, hard_max_tokens=1000)


def lead_in_corpus():
    units = [heading("h-1", "BIR", 1)]
    units.append(unit("p-11", words(120, "A"), order=2, section=("BIR",)))
    units.append(unit("p-12", words(20, "B") + " şöyle:", order=3, section=("BIR",)))
    units.append(unit("l-13", "- " + words(30, "C"), order=4, section=("BIR",), type=UnitType.LIST))
    units.append(unit("l-14", "- " + words(30, "D"), order=5, section=("BIR",), type=UnitType.LIST))
    units.append(heading("h-2", "IKI", 6))
    for index, prefix in enumerate(("E", "F", "G"), start=1):
        units.append(unit(f"p-2{index}", words(60, prefix), order=6 + index, section=("IKI",)))
    return units


def deterministic_result(units):
    return pipe.run_deep_analysis(
        units, counter=COUNTER, settings=pipe.DeepAnalysisSettings(config=CONFIG, use_llm=False)
    )


def test_the_story_names_the_smell_the_contract_removed():
    units = lead_in_corpus()
    result = deterministic_result(units)
    story = deep_arm.boundary_story(
        units, counter=COUNTER, config=CONFIG, audit=result.audit, quality=result.quality
    )
    improved = [s for s in story["sections"] if s["status"] == "deterministic_improved"]
    assert len(improved) == 1 and improved[0]["heading"] == "BIR"
    group = improved[0]["change_groups"][0]
    assert group["removed_smells"] == ["lead_in_cut"]
    assert group["introduced_smells"] == []
    assert group["origin"] == "deterministic"
    # The moved final cut is attributed on its cut_after unit.
    for cut_after in group["final_cuts_after"]:
        assert story["by_cut_after"][cut_after]["status"] == "det_moved"
        assert story["by_cut_after"][cut_after]["removed_smells"] == ["lead_in_cut"]


def test_untouched_sections_are_standard_kept_and_origins_add_up():
    units = lead_in_corpus()
    result = deterministic_result(units)
    story = deep_arm.boundary_story(
        units, counter=COUNTER, config=CONFIG, audit=result.audit, quality=result.quality
    )
    counts = story["counts"]
    assert counts["sections"] == 2
    assert sum(counts[s] for s in deep_arm.SECTION_STATUSES) == counts["sections"]
    assert counts["standard_kept"] >= 1
    final_total = sum(counts["final_boundaries_by_origin"].values())
    assert final_total == sum(len(s["final_cuts_after"]) for s in story["sections"])
    assert counts["final_boundaries_by_origin"]["llm"] == 0
    assert counts["llm_proposals"] == 0


def test_a_verifier_verdict_is_attached_to_its_section():
    units = lead_in_corpus()
    result = deterministic_result(units)
    verdicts = [
        {"group_key": "cg-0001-0-3", "section_index": 1, "accepted": False, "reason": "order_dependent"}
    ]
    story = deep_arm.boundary_story(
        units, counter=COUNTER, config=CONFIG, audit=result.audit, quality=result.quality,
        verdicts=verdicts,
    )
    section = story["sections"][1]
    assert section["llm_proposals"][0]["reason"] == "order_dependent"
    assert section["llm_proposals"][0]["unit_ids"] == section["piece_unit_ids"][0:3]
    assert story["counts"]["llm_proposals"] == 1 and story["counts"]["llm_proposals_accepted"] == 0


def test_packaging_writes_the_arm_and_pins_the_canonical(tmp_path):
    units = lead_in_corpus()
    units_path = tmp_path / "data" / "doc.units.jsonl"
    units_path.parent.mkdir()
    units_path.write_text(
        "".join(json.dumps(u.model_dump(mode="json"), ensure_ascii=False) + "\n" for u in units),
        encoding="utf-8",
        newline="\n",
    )
    tree = tmp_path / "deep"
    write_tree(deterministic_result(units), tree, units_path=units_path)
    summary = deep_arm.package(tree, units_path, root=tmp_path, counter=COUNTER)
    for name in (
        "arm/manifest.json", "arm/chunks.jsonl", "arm/mapping.json", "arm/structural_quality.json",
        "standard/chunks.jsonl", "standard/mapping.json", "boundary-decisions.json",
    ):
        assert (tree / name).is_file(), name
    manifest = json.loads((tree / "arm" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["canonical_sha256"] == hashlib.sha256(units_path.read_bytes()).hexdigest()
    assert manifest["arm_kind"] == "deep_analysis" and manifest["has_retrieval"] is False
    assert manifest["units_file"] == "data/doc.units.jsonl"
    assert summary["chunk_count"]["deep"] >= 1 and summary["retrieval"]["deep"] is None
    assert not (tree / "arm" / "retrieval.json").exists()


def test_packaging_refuses_a_foreign_document(tmp_path):
    units = lead_in_corpus()
    tree = tmp_path / "deep"
    write_tree(deterministic_result(units), tree)
    other = [u.model_copy(update={"document_id": "other"}) for u in units]
    path = tmp_path / "other.jsonl"
    path.write_text(
        "".join(json.dumps(u.model_dump(mode="json"), ensure_ascii=False) + "\n" for u in other),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        deep_arm.package(tree, path, root=tmp_path, counter=COUNTER)


def test_writing_into_evaluation_is_refused(tmp_path):
    with pytest.raises(ValueError):
        deep_arm.refuse_output(tmp_path / "evaluation" / "x")
