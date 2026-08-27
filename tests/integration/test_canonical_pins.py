"""Each canonical profile against its own contract -- not against one schema.

Three things name a canonical by hash and none of them used to be cross-checked
against the file itself: the manifest beside it, the benchmark configs that
consume it, and the gold sets pinned to it. A canonical regenerated under a
different profile keeps its filename, so the drift is silent until a benchmark
run refuses -- or worse, until a re-pinned gold set is scored against a
canonical it was never authored on.

**The three profiles do not share a manifest contract, and requiring one would
be a regression.** ``v1-frozen`` is the historical baseline: its checked-in
manifest predates both ``canonical_profile`` and ``units_sha256``, and bringing
it up to the newer shape would mean rewriting the one artifact whose value is
that it has not been rewritten. So v1 is verified where it actually is pinned
-- the ``.sha256`` sidecar, the literal constants below, and the configs that
consume it -- and its manifest is checked only for the legacy fields it does
carry. ``v2-repaired`` and ``v3-semantic`` are generated artifacts, so they
carry the newer shape and are held to it.

File-level pins skip rather than fail when a canonical is absent: the repaired
profiles are produced on demand and are not part of a fresh clone. The v1
canonicals are checked in and must always be there.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

#: The frozen v1 canonicals, pinned here as well as in their sidecar and their
#: configs. Restated literally so that rewriting the sidecar cannot quietly
#: bless a rewritten baseline.
V1_FROZEN = {
    "kkb-2024.units.jsonl": "2776742d5bddad7dcf2a03320dca36e6b384e2ba042ab99ccdecce61612720d5",
    "kkb-2022.units.jsonl": "230ba9c9cdd0f8a8e3cefc191c0fd547a40e4bd195176cfd6c08ef8bf3511f03",
}

REPAIRED = {
    "kkb-2024.units.v2.jsonl": "v2-repaired",
    "kkb-2024.units.v3.jsonl": "v3-semantic",
    "kkb-2022.units.v2.jsonl": "v2-repaired",
    "kkb-2022.units.v3.jsonl": "v3-semantic",
}

#: Fields the historical v1 manifests do carry. The newer ones are absent by
#: design and their absence is not a defect.
LEGACY_MANIFEST_FIELDS = (
    "document_id",
    "extraction_parameters",
    "layout_profile",
    "pymupdf4llm_version",
    "schema_version",
    "source_pdf",
    "source_pdf_sha256",
    "visual_provenance_file",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_for(units: Path) -> Path:
    return units.with_name(units.name.replace(".jsonl", ".manifest.json"))


def load_manifest(units: Path) -> dict:
    path = manifest_for(units)
    assert path.is_file(), f"{path.name} is missing"
    return json.loads(path.read_text(encoding="utf-8"))


def repaired(name: str) -> Path:
    path = DATA / name
    if not path.is_file():
        pytest.skip(f"{name} has not been generated in this working tree")
    return path


# --- v1-frozen: the baseline is verified by its hash, not by its schema ------


@pytest.mark.parametrize("name", sorted(V1_FROZEN))
def test_the_frozen_canonical_is_byte_identical_to_its_pin(name):
    """The one invariant the whole freeze rests on."""
    path = DATA / name
    assert path.is_file(), f"{name} is checked in and must exist"
    assert sha256(path) == V1_FROZEN[name], (
        f"{name} is no longer the frozen baseline; every result pinned to it "
        "is invalid until this is restored"
    )


def test_the_sha256_sidecar_agrees_with_the_frozen_pin():
    sidecar = DATA / "kkb-2024.units.sha256"
    assert sidecar.is_file()
    digest, name = sidecar.read_text(encoding="utf-8").split()
    assert name == "kkb-2024.units.jsonl"
    assert digest == V1_FROZEN["kkb-2024.units.jsonl"]


@pytest.mark.parametrize("name", sorted(V1_FROZEN))
def test_the_frozen_manifest_keeps_its_legacy_shape(name):
    """v1 is not held to the newer manifest contract, and must not be.

    Rewriting the baseline's manifest to match a schema introduced years later
    would change the artifact whose only job is to have stayed still.
    """
    manifest = load_manifest(DATA / name)
    for field in LEGACY_MANIFEST_FIELDS:
        assert field in manifest, f"{name}: legacy manifest lost {field}"
    assert manifest["source_pdf_sha256"]
    # If a regenerated manifest ever does carry the newer pin, it still has to
    # be right -- accepted, but not trusted blindly.
    if "units_sha256" in manifest:
        assert manifest["units_sha256"] == V1_FROZEN[name]


# --- v2 / v3: generated artifacts, held to the newer contract ---------------


@pytest.mark.parametrize("name", sorted(REPAIRED))
def test_a_repaired_manifest_pins_the_canonical_beside_it(name):
    units = repaired(name)
    manifest = load_manifest(units)

    assert "units_sha256" in manifest, (
        f"{name}: manifest predates the units_sha256 pin; regenerate it"
    )
    assert manifest["units_file"] == units.name
    assert manifest["units_sha256"] == sha256(units)


@pytest.mark.parametrize("name", sorted(REPAIRED))
def test_a_repaired_manifest_records_the_profile_its_filename_claims(name):
    from amsc.prepare_full_checkpoint import CANONICAL_PROFILES

    manifest = load_manifest(repaired(name))
    recorded = manifest["canonical_profile"]

    assert recorded["profile_id"] == REPAIRED[name]
    assert recorded["repairs"] == dict(
        sorted(CANONICAL_PROFILES[REPAIRED[name]].items())
    ), f"{name} was produced by a repair set the code no longer defines"


def test_v3_carries_the_semantic_pass_and_v2_does_not():
    v3 = load_manifest(repaired("kkb-2024.units.v3.jsonl"))
    v2 = load_manifest(repaired("kkb-2024.units.v2.jsonl"))

    assert v3["canonical_profile"]["repairs"]["assign_semantic_heading_roles"]
    assert "assign_semantic_heading_roles" not in v2["canonical_profile"]["repairs"]


# --- everything downstream that names a canonical by hash -------------------


@pytest.mark.parametrize("config", sorted((ROOT / "configs").glob("*.yaml")))
def test_every_config_pinning_a_canonical_pins_the_current_one(config):
    payload = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    source = payload.get("source") or {}
    units, pinned = source.get("units"), source.get("units_sha256")
    if not units or not pinned:
        pytest.skip(f"{config.name} pins no canonical")

    name = Path(units).name
    path = DATA / name if name in V1_FROZEN else repaired(name)
    assert pinned == sha256(path), (
        f"{config.name} pins a stale sha for {units}; "
        "re-pin it or restore the canonical"
    )


#: Every re-pinned gold set, both repaired profiles. A v2 set left pinned to a
#: superseded canonical is the same silent drift as a v3 one, and only shows up
#: when someone runs the v2 benchmark months later.
GOLD_SETS = [
    "evaluation/kkb-2024/retrieval-benchmark/canonical-v2/gold-queries-v2.canonical-v2.json",
    "evaluation/kkb-2024/retrieval-benchmark/canonical-v2/gold-queries.canonical-v2.json",
    "evaluation/kkb-2024/retrieval-benchmark/canonical-v3/gold-queries-v2.canonical-v3.json",
    "evaluation/kkb-2024/retrieval-benchmark/canonical-v3/gold-queries.canonical-v3.json",
    "evaluation/holdout-kkb-2022/retrieval-benchmark/canonical-v2/gold-queries-v2.canonical-v2.json",
    "evaluation/holdout-kkb-2022/retrieval-benchmark/canonical-v3/gold-queries-v2.canonical-v3.json",
]


def load_gold(relative: str) -> dict:
    path = ROOT / relative
    if not path.is_file():
        pytest.skip(f"{Path(relative).name} has not been generated here")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("relative", GOLD_SETS)
def test_every_repinned_gold_set_names_a_canonical_that_still_matches(relative):
    gold = load_gold(relative)
    units = repaired(Path(gold["source_units_file"]).name)

    assert gold["source_units_sha256"] == sha256(units), (
        f"{Path(relative).name} is pinned to a canonical that has since "
        "changed; re-pin it with amsc.gold_repin before scoring against it"
    )


@pytest.mark.parametrize("relative", GOLD_SETS)
def test_every_gold_evidence_id_resolves_in_the_canonical_it_is_pinned_to(relative):
    gold = load_gold(relative)
    units = repaired(Path(gold["source_units_file"]).name)

    by_id = {}
    for line in units.read_text(encoding="utf-8").splitlines():
        if line.strip():
            unit = json.loads(line)
            by_id[unit["unit_id"]] = unit

    for query in gold["queries"]:
        for unit_id in query.get("evidence_unit_ids") or []:
            unit = by_id.get(unit_id)
            assert unit is not None, f"{query['query_id']}: {unit_id} is gone"
            pages = query.get("evidence_pages") or []
            if pages:
                assert unit["source"]["page"] in pages, (
                    f"{query['query_id']}: {unit_id} moved to page "
                    f"{unit['source']['page']}, expected one of {pages}"
                )
