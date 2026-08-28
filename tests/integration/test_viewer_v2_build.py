"""Viewer v2 over the real frozen v5 benchmark artifacts.

The v5 tree is generated output and not part of a fresh clone, so these tests
skip rather than fail when it is absent. When it is present they hold the
viewer to the artifacts themselves: every number asserted below is read from
the tree at test time, never restated.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from amsc.viewer_v2 import build_viewer

ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = {
    "kkb-2024": ROOT / "artifacts" / "chunk-benchmark-v5" / "kkb-2024",
    "kkb-2022": ROOT / "artifacts" / "chunk-benchmark-v5" / "kkb-2022",
}
AGENTIC_TREES = {
    "kkb-2024": ROOT / "artifacts" / "agentic-chunker" / "kkb-2024",
}


def agentic_on_disk():
    """The optional fourth arm joins the build exactly when its tree exists."""
    return {
        doc: tree
        for doc, tree in AGENTIC_TREES.items()
        if (tree / "manifest.json").is_file()
    }


@pytest.fixture(scope="module")
def viewer_html(tmp_path_factory):
    for doc, tree in BENCHMARKS.items():
        if not (tree / "benchmark-summary.json").is_file():
            pytest.skip(f"{tree} has not been generated in this working tree")
    output = tmp_path_factory.mktemp("viewer-v2") / "index.html"
    build_viewer(BENCHMARKS, output, root=ROOT, agentic=agentic_on_disk())
    return output.read_text(encoding="utf-8")


def embedded(html_text):
    match = re.search(
        r'<script id="viewer-data" type="application/json">(.*?)</script>',
        html_text,
        re.S,
    )
    return json.loads(match.group(1).replace("<\\/", "</"))


def test_both_corpora_and_their_final_metrics_are_embedded(viewer_html):
    data = embedded(viewer_html)
    assert sorted(data["docs"]) == ["kkb-2022", "kkb-2024"]

    for doc, tree in BENCHMARKS.items():
        for arm in ("markdown", "hybrid", "structure-only"):
            expected = json.loads(
                (tree / arm / "retrieval.json").read_text(encoding="utf-8")
            )
            embedded_metrics = data["docs"][doc]["arms"][arm]["ret"]
            for key in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "chunk_count"):
                assert embedded_metrics[key] == expected[key], (doc, arm, key)


def test_gold_counts_match_the_gold_sets(viewer_html):
    data = embedded(viewer_html)
    assert len(data["docs"]["kkb-2024"]["gold"]) == 47
    assert len(data["docs"]["kkb-2022"]["gold"]) == 20
    for doc in data["docs"].values():
        unit_ids = {unit["i"] for unit in doc["units"]}
        for query in doc["gold"]:
            assert set(query["ev"]) <= unit_ids, query["id"]


def test_difference_points_are_deterministic_and_nonempty(viewer_html, tmp_path):
    data = embedded(viewer_html)
    for doc in data["docs"].values():
        assert doc["diffs"], "three genuinely different arms must disagree somewhere"
        for point in doc["diffs"]:
            assert set(point["s"]) == {"markdown", "hybrid", "structure-only"}
            assert len(set(point["s"].values())) > 1

    output = tmp_path / "again.html"
    build_viewer(BENCHMARKS, output, root=ROOT, agentic=agentic_on_disk())
    assert output.read_text(encoding="utf-8") == viewer_html


def test_the_checked_in_viewer_artifact_is_current(viewer_html):
    published = ROOT / "artifacts" / "viewer-v2" / "index.html"
    if not published.is_file():
        pytest.skip("artifacts/viewer-v2/index.html has not been built here")
    assert published.read_text(encoding="utf-8") == viewer_html, (
        "artifacts/viewer-v2/index.html is stale; rebuild it with "
        "python -m amsc.viewer_v2"
    )


# --- the continuation layer over the real frozen artifacts ------------------


def test_the_documented_example_link_exists_and_the_banner_variant_does_not(viewer_html):
    """KKB 2024 p47: 0212 -> 0213 is a continuation; 0213 -> 0214 is not.

    The second half is the strictness claim: page 48 re-opens the same chapter
    under a typographically different banner, and the relation refuses it.
    """
    data = embedded(viewer_html)
    chunks = data["docs"]["kkb-2024"]["arms"]["structure-only"]["chunks"]
    by_id = {chunk["id"]: chunk for chunk in chunks}

    assert by_id["kkb-2024:s-chunk-0213"]["cp"] == 211  # index of 0212
    assert by_id["kkb-2024:s-chunk-0212"]["cn"] == 212
    assert by_id["kkb-2024:s-chunk-0213"]["cn"] is None
    assert by_id["kkb-2024:s-chunk-0214"]["cp"] is None
    # The 0212->0213 boundary opens on l-01033: a plain budget cut. The
    # 0211->0212 boundary opens on h-01025: a label seam, recorded but not
    # walked by the expansion.
    assert by_id["kkb-2024:s-chunk-0213"]["rt"] == "TOKEN_BUDGET_CONTINUATION"
    assert by_id["kkb-2024:s-chunk-0212"]["rt"] == "SECTION_LABEL_CONTINUATION"


def test_python_expander_reproduces_the_viewer_simulation():
    """expand_context on the frozen chunks equals the JS mirror's answer."""
    import json as json_module

    from amsc.chunk_relations import derive_continuations, expand_context

    tree = BENCHMARKS["kkb-2024"]
    if not (tree / "structure-only" / "chunks.jsonl").is_file():
        pytest.skip("v5 artifacts absent")
    chunks = [
        json_module.loads(line)
        for line in (tree / "structure-only" / "chunks.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    links = derive_continuations(chunks, kind="structure_first")

    result = expand_context(
        "kkb-2024:s-chunk-0213", chunks=chunks, links=links, max_total_tokens=1126
    )
    # 0212 joins over the budget cut; 0211 does NOT -- its boundary is a
    # label seam, which the narrowed expansion refuses to cross.
    assert result.chunk_ids == [
        "kkb-2024:s-chunk-0212",
        "kkb-2024:s-chunk-0213",
    ]
    assert result.total_tokens == 861
    assert result.stopped["before"] == "non_budget_boundary"
    assert result.stopped["after"] == "section_boundary"

    disabled = expand_context(
        "kkb-2024:s-chunk-0213",
        chunks=chunks,
        links=links,
        max_total_tokens=1126,
        enabled=False,
    )
    assert disabled.chunk_ids == ["kkb-2024:s-chunk-0213"]


def test_the_checked_in_relation_sidecars_are_current(viewer_html):
    from amsc.chunk_relations import derive_tree

    published = ROOT / "artifacts" / "chunk-relations-v1"
    if not (published / "kkb-2024" / "summary.json").is_file():
        pytest.skip("chunk-relations sidecars have not been derived here")

    import tempfile

    for doc, tree in BENCHMARKS.items():
        with tempfile.TemporaryDirectory() as scratch:
            fresh = Path(scratch) / doc
            derive_tree(tree, fresh)
            for name in sorted(p.name for p in fresh.iterdir()):
                assert (published / doc / name).read_bytes() == (
                    fresh / name
                ).read_bytes(), f"{doc}/{name} is stale; re-run amsc.chunk_relations"
