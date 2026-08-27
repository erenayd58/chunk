"""What a canonical profile is made of, pinned.

A profile is the only thing that separates ``data/kkb-2024.units.v3.jsonl``
from ``data/kkb-2024.units.jsonl``: same PDF, same extractor, different set of
opt-in repairs. Nothing else in the suite reads that set, so before this file
existed a repair could be added to it, dropped from it or renamed and every
test still passed while every v2 and v3 canonical in ``data/`` silently stopped
matching the code that claims to produce it.

The pins below are deliberately literal. Changing a profile is allowed -- it is
a decision, and it invalidates every downstream frozen result -- so it has to
be made here, in the open, rather than fall out of an edit somewhere else.
"""

from __future__ import annotations

import inspect
import json

import pytest

from amsc.prepare_full_checkpoint import (
    CANONICAL_PROFILES,
    V2_CANONICAL_REPAIRS,
    V3_CANONICAL_REPAIRS,
    _record_full_document_profile_application,
    extract_full_canonical_units,
)


V2_EXPECTED = {
    "reconstruct_visual_grids": True,
    "demote_lead_in_headings": True,
    "promote_missed_headings": True,
    "demote_caption_headings": True,
    "rejoin_split_headings_enabled": True,
    "rejoin_hyphenated_headings_enabled": True,
    "demote_sentence_headings_enabled": True,
    "assign_typographic_heading_levels": True,
}


def test_v1_frozen_applies_no_repair_at_all():
    """The whole point of v1: it reproduces the checked-in canonical."""
    assert CANONICAL_PROFILES["v1-frozen"] == {}


def test_v2_repaired_is_exactly_these_eight_repairs():
    assert V2_CANONICAL_REPAIRS == V2_EXPECTED


def test_v3_semantic_is_v2_plus_semantic_roles_and_nothing_else():
    assert V3_CANONICAL_REPAIRS == {**V2_EXPECTED, "assign_semantic_heading_roles": True}


def test_running_header_removal_stays_out_of_every_profile():
    """It deletes two genuine chapter titles; the banners are the lesser evil."""
    for profile, repairs in CANONICAL_PROFILES.items():
        assert "running_header_min_pages" not in repairs, profile


def test_the_three_profiles_are_the_only_ones_offered():
    assert sorted(CANONICAL_PROFILES) == ["v1-frozen", "v2-repaired", "v3-semantic"]


def test_every_repair_name_is_a_parameter_the_extractor_accepts():
    """A renamed flag must not become a repair that silently never runs."""
    accepted = set(inspect.signature(extract_full_canonical_units).parameters)
    for profile, repairs in CANONICAL_PROFILES.items():
        assert set(repairs) <= accepted, f"{profile}: {set(repairs) - accepted}"


def test_no_repair_is_on_by_default():
    """Calling the extractor without a profile must reproduce v1-frozen."""
    defaults = inspect.signature(extract_full_canonical_units).parameters
    for name in V3_CANONICAL_REPAIRS:
        assert defaults[name].default is False, name


# --- the manifest has to pin its own output ---------------------------------


def manifest(tmp_path, name="doc.units.v3.jsonl"):
    canonical = tmp_path / name
    canonical.write_text('{"unit_id": "p-1"}\n', encoding="utf-8", newline="\n")
    path = tmp_path / "doc.units.v3.manifest.json"
    path.write_text(
        json.dumps({"extraction_parameters": {}, "source_pdf": "doc.pdf"}),
        encoding="utf-8",
        newline="\n",
    )
    return path, canonical


def record(path, canonical, profile):
    _record_full_document_profile_application(
        path,
        canonical_path=canonical,
        portrait_pages=[],
        landscape_pages=[1],
        canonical_profile=profile,
    )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("profile", ["v2-repaired", "v3-semantic"])
def test_a_repaired_manifest_records_the_sha_of_what_it_produced(tmp_path, profile):
    path, canonical = manifest(tmp_path)

    payload = record(path, canonical, profile)

    assert payload["units_file"] == "doc.units.v3.jsonl"
    assert len(payload["units_sha256"]) == 64
    assert payload["canonical_profile"] == {
        "profile_id": profile,
        "repairs": dict(sorted(CANONICAL_PROFILES[profile].items())),
    }


def test_the_frozen_profile_keeps_the_legacy_manifest_shape(tmp_path):
    """v1 is the historical baseline; its manifest is not brought forward.

    The v1 canonical is pinned by its ``.sha256`` sidecar and by every config
    that consumes it, so a self-pin buys nothing -- and writing one would make
    a regenerated v1 manifest differ from the frozen one for no gain.
    """
    path, canonical = manifest(tmp_path)

    payload = record(path, canonical, "v1-frozen")

    assert "units_sha256" not in payload
    assert "units_file" not in payload
    assert payload["canonical_profile"] == {"profile_id": "v1-frozen", "repairs": {}}


def test_the_recorded_sha_actually_tracks_the_file(tmp_path):
    path, canonical = manifest(tmp_path)

    before = record(path, canonical, "v2-repaired")["units_sha256"]
    canonical.write_text('{"unit_id": "p-2"}\n', encoding="utf-8", newline="\n")
    after = record(path, canonical, "v2-repaired")["units_sha256"]

    assert before != after


def test_an_unknown_profile_cannot_be_recorded(tmp_path):
    path, canonical = manifest(tmp_path)

    with pytest.raises(KeyError):
        _record_full_document_profile_application(
            path,
            canonical_path=canonical,
            portrait_pages=[],
            landscape_pages=[1],
            canonical_profile="v4-imaginary",
        )
