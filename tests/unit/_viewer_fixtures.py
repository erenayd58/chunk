"""A synthetic benchmark tree the Viewer reader can be held to.

Two pages whose three arms disagree at known places, so every derived value
-- boundary reasons, difference points, query pairing, evidence offsets --
has a hand-computable expected value.
"""

from __future__ import annotations

import hashlib
import json


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
