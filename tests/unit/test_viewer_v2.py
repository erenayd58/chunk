"""Viewer v2 against a synthetic benchmark tree it can be held to.

The fixture is a two-page corpus whose three arms disagree at known places, so
every derived value the viewer embeds -- boundary reasons, difference points,
query pairing, evidence offsets -- has a hand-computable expected value.
"""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from amsc.viewer_v2 import build_viewer, display_html, heading_plain

P1 = "Alpha bravo **kalin** metin."
P2 = "Charlie delta metin burada devam eder."
P3 = "Echo foxtrot kanit cumlesi tam burada."
T1 = "|A|B|\n|--|--|\n|1|2|"


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def _unit(uid, text, page, unit_type="paragraph", **extra):
    row = {
        "document_id": "doc",
        "unit_id": uid,
        "order": int(uid.split("-")[1]),
        "text": text,
        "type": unit_type,
        "heading_level": extra.get("level"),
        "section_path": extra.get("path") or ["**1. GIRIS**"],
        "source": {"page": page, "block": extra.get("block", 0)},
    }
    if "role" in extra:
        row["semantic_role"] = extra["role"]
    if "opens" in extra:
        row["opens_section"] = extra["opens"]
    return row


def _chunk(cid, unit_ids, tokens, pages, heading="**1. GIRIS**"):
    return {
        "chunk_id": cid,
        "text": "fixture",
        "unit_ids": unit_ids,
        "token_count": tokens,
        "pages": pages,
        "section_paths": [["**1. GIRIS**"]],
        "heading": heading,
        "split_strategies": ["whole"],
    }


def _segments(cid, rows):
    return {
        "chunk_id": cid,
        "coverage": {},
        "unmapped_unit_ids": [],
        "segments": [
            {
                "unit_id": uid,
                "unit_start": start,
                "unit_end": end,
                "chunk_start": 0,
                "chunk_end": end - start,
                "method": method,
            }
            for uid, start, end, method in rows
        ],
    }


def _retrieval(arm, hit1, mrr, chunks):
    return {
        "candidate_id": arm,
        "chunk_count": chunks,
        "hit_at_1": hit1,
        "hit_at_3": hit1,
        "hit_at_5": hit1,
        "mrr": mrr,
        "evidence_coverage_at_5": hit1,
        "source_evidence_coverage": 1.0,
        "query_count": 2,
    }


def _result(rank, cid, matched, pages, tokens=30):
    return {
        "rank": rank,
        "chunk_id": cid,
        "matched_evidence_unit_ids": matched,
        "pages": pages,
        "token_count": tokens,
        "bm25_score": 1.0 / rank,
    }


def make_tree(root, *, hit1_structure=0.3333):
    """A complete, minimal chunk-benchmark output tree plus its canonical."""
    units = [
        _unit("h-1", "**1. GIRIS**", 1, "heading", level=1, role="section", opens=True),
        _unit("p-1", P1, 1, block=1),
        _unit("p-2", P2, 1, block=2),
        _unit("h-2", "Ara Etiket", 2, "heading", level=3, role="item", opens=False),
        _unit("p-3", P3, 2, block=1),
        _unit("t-1", T1, 2, "table", block=2),
    ]
    units_path = root / "data" / "doc.units.v3.jsonl"
    _write_jsonl(units_path, units)
    sha = hashlib.sha256(units_path.read_bytes()).hexdigest()

    gold = {
        "queries": [
            {
                "query_id": "q1",
                "question": "Kanit cumlesi nerede?",
                "expected_answer": "Echo foxtrot.",
                "evidence_unit_ids": ["p-3"],
                "evidence_pages": [2],
                "evidence_type": "narrative",
                "difficulty": "simple",
            },
            {
                "query_id": "q2",
                "question": "Alpha bravo nedir?",
                "expected_answer": "Kalin metin.",
                "evidence_unit_ids": ["p-1"],
                "evidence_pages": [1],
                "evidence_type": "narrative",
                "difficulty": "simple",
            },
        ]
    }
    _write_json(root / "gold.json", gold)

    tree = root / "bench"
    _write_json(
        tree / "resolved-config.json",
        {
            "arms": {
                "markdown": {"kind": "markdown_recursive"},
                "hybrid": {"kind": "hybrid_h1"},
                "structure-only": {"kind": "structure_first"},
            },
            "source": {
                "units": "data/doc.units.v3.jsonl",
                "units_sha256": sha,
                "gold_queries": "gold.json",
            },
        },
    )
    _write_json(tree / "manifest.json", {"canonical_sha256": sha})
    _write_json(
        tree / "benchmark-summary.json",
        {
            "status": "fixture",
            "query_count": 2,
            "parser_baseline_finding_count": 5,
            "interpretation_guardrail": "GUARDRAIL-SENTINEL",
            "arm_diagnostics": {"hybrid": {"arbitrated_boundary_count": 7}},
            "evidence_type_hit_at_5": {
                "narrative": {
                    "query_count": 2,
                    "markdown": 1,
                    "hybrid": 1,
                    "structure-only": 2,
                }
            },
            "query_comparison": {
                "missed_by_all_at_5": [],
                "pairwise_hit_at_5": {},
            },
            "timing": {},
        },
    )

    arms = {
        "markdown": {
            "chunks": [
                _chunk("doc:md-chunk-0001", ["h-1", "p-1"], 20, [1]),
                _chunk("doc:md-chunk-0002", ["p-1", "p-2"], 25, [1]),
                _chunk("doc:md-chunk-0003", ["h-2", "p-3", "t-1"], 30, [2]),
            ],
            "mapping": [
                _segments(
                    "doc:md-chunk-0001",
                    [("h-1", 0, len("**1. GIRIS**"), "offset"), ("p-1", 0, 12, "offset")],
                ),
                _segments(
                    "doc:md-chunk-0002",
                    [("p-1", 12, len(P1), "offset"), ("p-2", 0, len(P2), "offset")],
                ),
                _segments(
                    "doc:md-chunk-0003",
                    [
                        ("h-2", 0, len("Ara Etiket"), "offset"),
                        ("p-3", 0, len(P3), "offset"),
                        ("t-1", 0, len(T1), "offset"),
                    ],
                ),
            ],
            "retrieval": _retrieval("markdown", 0.1111, 0.4444, 3),
            "q1": {"first_relevant_rank": None, "results": [_result(1, "doc:md-chunk-0002", [], [1])]},
            "q2": {"first_relevant_rank": 1, "results": [_result(1, "doc:md-chunk-0001", ["p-1"], [1])]},
        },
        "hybrid": {
            "chunks": [
                _chunk("doc:h-chunk-0001", ["p-1"], 15, [1]),
                _chunk("doc:h-chunk-0002", ["p-2", "h-2", "p-3", "t-1"], 45, [1, 2]),
            ],
            "mapping": [
                _segments("doc:h-chunk-0001", [("p-1", 0, len(P1), "provenance")]),
                _segments(
                    "doc:h-chunk-0002",
                    [
                        ("p-2", 0, len(P2), "provenance"),
                        ("h-2", 0, len("Ara Etiket"), "provenance"),
                        ("p-3", 0, len(P3), "provenance"),
                        ("t-1", 0, len(T1), "provenance"),
                    ],
                ),
            ],
            "retrieval": _retrieval("hybrid", 0.2222, 0.5555, 2),
            "q1": {
                "first_relevant_rank": 4,
                "results": [
                    _result(1, "doc:h-chunk-0001", [], [1]),
                    _result(2, "doc:h-chunk-0001", [], [1]),
                    _result(3, "doc:h-chunk-0001", [], [1]),
                    _result(4, "doc:h-chunk-0002", ["p-3"], [1, 2]),
                ],
            },
            "q2": {"first_relevant_rank": 1, "results": [_result(1, "doc:h-chunk-0001", ["p-1"], [1])]},
        },
        "structure-only": {
            "chunks": [
                _chunk("doc:s-chunk-0001", ["p-1", "p-2"], 35, [1]),
                _chunk("doc:s-chunk-0002", ["h-2", "p-3", "t-1#f1"], 40, [2]),
            ],
            "mapping": [
                _segments(
                    "doc:s-chunk-0001",
                    [("p-1", 0, len(P1), "provenance"), ("p-2", 0, len(P2), "provenance")],
                ),
                _segments(
                    "doc:s-chunk-0002",
                    [
                        ("h-2", 0, len("Ara Etiket"), "provenance"),
                        ("p-3", 0, len(P3), "provenance"),
                        ("t-1", 0, len(T1), "sequential"),
                    ],
                ),
            ],
            "retrieval": _retrieval("structure-only", hit1_structure, 0.6666, 2),
            "q1": {"first_relevant_rank": 1, "results": [_result(1, "doc:s-chunk-0002", ["p-3"], [2])]},
            "q2": {"first_relevant_rank": 1, "results": [_result(1, "doc:s-chunk-0001", ["p-1"], [1])]},
        },
    }

    for arm, payload in arms.items():
        arm_dir = tree / arm
        _write_jsonl(arm_dir / "chunks.jsonl", payload["chunks"])
        _write_json(arm_dir / "mapping.json", {"chunks": payload["mapping"], "health": {}})
        _write_jsonl(
            arm_dir / "query-results.jsonl",
            [
                {
                    "query_id": qid,
                    "question": "soru",
                    "source_evidence_coverage": 1.0,
                    **payload[qid],
                }
                for qid in ("q1", "q2")
            ],
        )
        _write_json(arm_dir / "retrieval.json", payload["retrieval"])
        _write_json(
            arm_dir / "structural_quality.json",
            {
                "chunk_count": len(payload["chunks"]),
                "token_count": {"median": 30, "p90_nearest_rank": 40, "max": 45},
                "size_bands": {"below_min_count": 0, "above_soft_max_count": 0},
                "structure": {"heading_led_ratio": 1.0, "multi_section_count": 0},
                "fragmentation": {
                    "mid_sentence_split_count": 0,
                    "table_units_fragmented": 0,
                    "list_units_fragmented": 0,
                },
                "duplication": {"duplicate_token_mass_ratio": 1.0},
            },
        )
        _write_json(
            arm_dir / "timing.json",
            {"chunk_ms_median": 1.0, "index_build_ms": 1.0, "search_p50_ms": 0.1, "search_p90_ms": 0.2},
        )
    return tree


def build(tmp_path, **kwargs):
    tree = make_tree(tmp_path, **kwargs)
    output = tmp_path / "out" / "index.html"
    build_viewer({"doc": tree}, output, root=tmp_path)
    return output.read_text(encoding="utf-8")


def embedded(html_text):
    match = re.search(
        r'<script id="viewer-data" type="application/json">(.*?)</script>',
        html_text,
        re.S,
    )
    return json.loads(match.group(1).replace("<\\/", "</"))


# --- the four modes ---------------------------------------------------------


def test_all_four_modes_are_present(tmp_path):
    html_text = build(tmp_path)
    for mode in ("presentation", "query", "debug", "benchmark"):
        assert f'data-mode="{mode}"' in html_text
    for label in ("Sunum", "Sorgu", "Debug", "Benchmark"):
        assert f">{label}</button>" in html_text


def test_benchmark_numbers_are_read_from_the_artifacts_not_hardcoded(tmp_path):
    first = build(tmp_path, hit1_structure=0.3333)
    assert "0.1111" in first and "0.3333" in first and "0.5555" in first
    assert "GUARDRAIL-SENTINEL" in first

    changed = build(tmp_path / "second", hit1_structure=0.9876)
    assert "0.9876" in changed and "0.3333" not in changed


# --- query / gold pairing ---------------------------------------------------


def test_query_gold_pairing_matches_the_artifacts(tmp_path):
    data = embedded(build(tmp_path))["docs"]["doc"]

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

    hybrid = data["arms"]["hybrid"]["q"]["q1"]
    assert hybrid["f"] == 4
    markdown = data["arms"]["markdown"]["q"]["q1"]
    assert markdown["f"] is None


def test_evidence_segments_slice_the_evidence_text_exactly(tmp_path):
    data = embedded(build(tmp_path))["docs"]["doc"]
    arm = data["arms"]["structure-only"]
    rank1_chunk = arm["q"]["q1"]["res"][0]["c"]

    segments = [row for row in arm["seg"]["p-3"] if row[0] == rank1_chunk]
    assert segments == [[rank1_chunk, 0, len(P3), "provenance"]]
    unit = next(u for u in data["units"] if u["i"] == "p-3")
    start, end = segments[0][1], segments[0][2]
    assert unit["x"][start:end] == P3


# --- differences ------------------------------------------------------------


def test_difference_points_are_exactly_the_disagreements(tmp_path):
    data = embedded(build(tmp_path))["docs"]["doc"]
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


def test_the_build_is_deterministic(tmp_path):
    first = build(tmp_path / "a")
    second = build(tmp_path / "b")
    assert first == second


# --- presentation never shows raw markup ------------------------------------


def test_presentation_rendering_carries_no_raw_markdown(tmp_path):
    data = embedded(build(tmp_path))["docs"]["doc"]
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
    data = embedded(build(tmp_path))["docs"]["doc"]
    reasons = {
        arm: [chunk["rs"] for chunk in payload["chunks"]]
        for arm, payload in data["arms"].items()
    }
    assert reasons["markdown"] == ["doc_start", "md_overlap", "md_heading"]
    assert reasons["hybrid"] == ["doc_start", "budget_split"]
    assert reasons["structure-only"] == ["doc_start", "label_split"]


# --- debug keeps the technical surface --------------------------------------


def test_debug_data_keeps_the_technical_surface(tmp_path):
    data = embedded(build(tmp_path))["docs"]["doc"]
    heading = next(u for u in data["units"] if u["i"] == "h-2")
    assert heading["r"] == "item" and heading["o"] is False and heading["l"] == 3
    assert heading["b"] == 0 and heading["s"] == ["**1. GIRIS**"]

    arm = data["arms"]["structure-only"]
    methods = {row[3] for rows in arm["seg"].values() for row in rows}
    assert {"provenance", "sequential"} <= methods
    assert any("#f1" in uid for chunk in arm["chunks"] for uid in chunk["u"])


# --- failure modes ----------------------------------------------------------


def test_a_missing_artifact_is_a_clear_error(tmp_path):
    tree = make_tree(tmp_path)
    (tree / "hybrid" / "chunks.jsonl").unlink()

    with pytest.raises(ValueError, match=r"chunks\.jsonl.*missing"):
        build_viewer({"doc": tree}, tmp_path / "out.html", root=tmp_path)


def test_a_canonical_that_moved_is_refused(tmp_path):
    tree = make_tree(tmp_path)
    units = tmp_path / "data" / "doc.units.v3.jsonl"
    units.write_text(
        units.read_text(encoding="utf-8") + "\n", encoding="utf-8", newline="\n"
    )

    with pytest.raises(ValueError, match="refuses to pair"):
        build_viewer({"doc": tree}, tmp_path / "out.html", root=tmp_path)


def test_writing_into_evaluation_is_refused(tmp_path):
    tree = make_tree(tmp_path)
    with pytest.raises(ValueError, match="evaluation"):
        build_viewer({"doc": tree}, tmp_path / "evaluation" / "x.html", root=tmp_path)


# --- continuation layer in the viewer ---------------------------------------


def test_continuation_links_are_embedded_per_chunk(tmp_path):
    data = embedded(build(tmp_path))["docs"]["doc"]

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


def test_technical_and_structural_boundaries_render_differently(tmp_path):
    html_text = build(tmp_path)
    # Two visual classes exist and carry different treatments.
    assert ".chunkline.tech .rule{border-top:2px dashed" in html_text
    assert '"struct"' in html_text and '"tech"' in html_text
    # The technical connector text and the continuation label are present.
    assert "içerik devam ediyor" in html_text
    assert "Önceki chunk'ın devamı — boyut sınırı nedeniyle ayrıldı" in html_text
    assert "yeni bölüm" in html_text


def test_the_expansion_toggle_and_mode_switch_are_present(tmp_path):
    html_text = build(tmp_path)
    assert 'id="contchk"' in html_text
    assert "Devam zinciri (local expansion)" in html_text
    assert "TOKEN_BUDGET_CONTINUATION" in html_text
    # Presentation-mode product naming for the chunking mode switch.
    assert "Standard" in html_text and "Structure-only" in html_text
    assert "hızlı ve deterministic" in html_text
    # The embedding-assisted hybrid is framed as a research arm, and the
    # product's LLM mode is described without being a measured arm.
    assert "araştırma kolu" in html_text
    assert "Deep Analysis" in html_text
    assert "zor chunk sınırlarını backend'de LLM ile değerlendirir" in html_text
    # The old product framing is gone, and no confidence-detector language
    # or key-bearing call ever reaches the client.
    assert "Enhanced" not in html_text
    assert "Semantic Assist" not in html_text
    assert "güven/belirsizlik dedektörü değildir" in html_text
    assert "belirsiz yapısal sınırları" not in html_text
    assert "OPENROUTER" not in html_text and "api_key" not in html_text
    # The expansion simulation is labelled as such and never re-ranks.
    assert "benchmark sonucunu değiştirmez" in html_text
