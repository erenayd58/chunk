"""The Viewer's reader, against a tree whose every derived value is known.

``viewer_corpus`` is the cross-repository contract: both the Viewer page and
the console's packaging worker turn artifact trees into this one payload
shape. What is pinned here is what the reader *derives* -- boundary reasons,
difference points, query pairing, evidence offsets, continuation links, the
display rendering -- and what it refuses. Page markup belongs to the page's
own tests.
"""

from __future__ import annotations

import pytest

from amsc.viewer.corpus import display_html, heading_plain, load_corpus

from _viewer_fixtures import P3, T1, make_tree


def corpus(tmp_path):
    return load_corpus(make_tree(tmp_path), tmp_path)


# --- query / gold pairing ---------------------------------------------------


def test_query_gold_pairing_matches_the_artifacts(tmp_path):
    data = corpus(tmp_path)

    gold = {g["id"]: g for g in data["gold"]}
    assert gold["q1"]["ev"] == ["p-3"] and gold["q1"]["pg"] == [2]
    assert gold["q2"]["ev"] == ["p-1"]

    structure = data["arms"]["structure-only"]["q"]
    assert structure["q1"]["f"] == 1
    top = structure["q1"]["res"][0]
    assert top["m"] == ["p-3"]
    # The rank-1 chunk really is the one that holds the evidence unit.
    chunk = data["arms"]["structure-only"]["chunks"][top["c"]]
    assert any(uid.split("#")[0] == "p-3" for uid in chunk["u"])

    assert data["arms"]["hybrid"]["q"]["q1"]["f"] == 4
    assert data["arms"]["markdown"]["q"]["q1"]["f"] is None


def test_evidence_segments_slice_the_evidence_text_exactly(tmp_path):
    arm = corpus(tmp_path)["arms"]["structure-only"]
    rank1_chunk = arm["q"]["q1"]["res"][0]["c"]

    segments = [row for row in arm["seg"]["p-3"] if row[0] == rank1_chunk]
    assert segments == [[rank1_chunk, 0, len(P3), "provenance"]]
    unit = next(u for u in corpus(tmp_path)["units"] if u["i"] == "p-3")
    start, end = segments[0][1], segments[0][2]
    assert unit["x"][start:end] == P3


# --- differences ------------------------------------------------------------


def test_difference_points_are_exactly_the_disagreements(tmp_path):
    data = corpus(tmp_path)
    assert data["diffs"] == [
        {
            "a": "p-1",
            "b": "p-2",
            "p": 1,
            "s": {"markdown": True, "hybrid": True, "structure-only": False},
        },
        {
            "a": "p-2",
            "b": "p-3",
            "p": 2,
            "s": {"markdown": True, "hybrid": False, "structure-only": True},
        },
    ]
    assert data["diffPages"] == [1, 2]


# --- display rendering never shows raw markup -------------------------------


def test_rendering_carries_no_raw_markdown(tmp_path):
    data = corpus(tmp_path)
    for unit in data["units"]:
        if unit["h"]:
            assert "**" not in unit["h"], unit["i"]
            assert not unit["h"].lstrip().startswith("#"), unit["i"]
    heading = next(u for u in data["units"] if u["i"] == "h-1")
    assert heading["h"] == "1. GIRIS"
    bold = next(u for u in data["units"] if u["i"] == "p-1")
    assert "<strong>kalin</strong>" in bold["h"]
    for arm in data["arms"].values():
        for chunk in arm["chunks"]:
            if chunk["hh"]:
                assert "**" not in chunk["hh"]
            assert chunk["sd"] == ["1. GIRIS"]


def test_display_rendering_rules():
    assert heading_plain("**15. BOLUM**") == "15. BOLUM"
    assert display_html("## Baslik", "heading") == "Baslik"
    assert display_html("- bir\n- iki", "list") == "<ul><li>bir</li><li>iki</li></ul>"
    table = display_html(T1, "table")
    assert "<table>" in table and "<th>A</th>" in table and "<td>1</td>" in table
    assert display_html("a < b **c**", "paragraph") == "a &lt; b <strong>c</strong>"


# --- boundary reasons -------------------------------------------------------


def test_boundary_reasons_follow_the_observable_rules(tmp_path):
    reasons = {
        arm: [chunk["rs"] for chunk in payload["chunks"]]
        for arm, payload in corpus(tmp_path)["arms"].items()
    }
    assert reasons["markdown"] == ["doc_start", "md_overlap", "md_heading"]
    assert reasons["hybrid"] == ["doc_start", "budget_split"]
    assert reasons["structure-only"] == ["doc_start", "label_split"]


def test_the_technical_surface_survives_for_debug(tmp_path):
    data = corpus(tmp_path)
    heading = next(u for u in data["units"] if u["i"] == "h-2")
    assert heading["r"] == "item" and heading["o"] is False and heading["l"] == 3
    assert heading["b"] == 0 and heading["s"] == ["**1. GIRIS**"]

    arm = data["arms"]["structure-only"]
    methods = {row[3] for rows in arm["seg"].values() for row in rows}
    assert {"provenance", "sequential"} <= methods
    assert any("#f1" in uid for chunk in arm["chunks"] for uid in chunk["u"])


# --- continuation links -----------------------------------------------------


def test_continuation_links_are_read_per_chunk(tmp_path):
    data = corpus(tmp_path)

    structure = data["arms"]["structure-only"]["chunks"]
    # c1 -> c2: same heading, same path, adjacent => linked both ways -- but
    # the boundary is a label seam, so it is NOT a token-budget continuation
    # and the two chunks share no expansion group.
    assert structure[0]["cn"] == 1 and structure[0]["cp"] is None
    assert structure[1]["cp"] == 0 and structure[1]["cn"] is None
    assert structure[1]["rt"] == "SECTION_LABEL_CONTINUATION"
    assert structure[0]["g"] is None and structure[1]["g"] is None

    markdown = data["arms"]["markdown"]["chunks"]
    assert markdown[0]["cn"] == 1 and markdown[1]["cp"] == 0
    assert markdown[1]["cn"] == 2  # md_heading boundary, still the same section
    assert markdown[1]["rt"] == "MARKDOWN_SPLIT_CONTINUATION"
    assert markdown[2]["rt"] == "MARKDOWN_SPLIT_CONTINUATION"
    assert all(chunk["g"] is None for chunk in markdown)

    hybrid = data["arms"]["hybrid"]["chunks"]
    assert hybrid[0]["cn"] == 1 and hybrid[1]["cp"] == 0
    # A plain budget split: the one relation the expansion walks.
    assert hybrid[1]["rt"] == "TOKEN_BUDGET_CONTINUATION"
    assert hybrid[0]["g"] == hybrid[1]["g"] == 0


# --- what the reader refuses ------------------------------------------------


def test_a_missing_artifact_is_a_clear_error(tmp_path):
    tree = make_tree(tmp_path)
    (tree / "hybrid" / "chunks.jsonl").unlink()

    with pytest.raises(ValueError, match=r"chunks\.jsonl.*missing"):
        load_corpus(tree, tmp_path)


def test_a_canonical_that_moved_is_refused(tmp_path):
    tree = make_tree(tmp_path)
    units = tmp_path / "data" / "doc.units.v3.jsonl"
    units.write_text(
        units.read_text(encoding="utf-8") + "\n", encoding="utf-8", newline="\n"
    )

    with pytest.raises(ValueError, match="refuses to pair"):
        load_corpus(tree, tmp_path)
