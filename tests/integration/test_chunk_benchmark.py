"""End-to-end benchmark run on a small corpus, with no model anywhere near it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import pytest

from amsc.chunk_benchmark import (
    ARMS,
    BM25OnlyIndex,
    ChunkBenchmarkConfig,
    normalize_unit_ids_for_retrieval,
    run_benchmark,
    to_documents,
)
from amsc.chunk_mapping import map_chunks
from amsc.io import load_jsonl_units
from amsc.models import UnitType
from amsc.retrieval_pipeline import RetrievalDocument, RetrievalHit
from amsc.tokenization import TiktokenTokenCounter

DOCUMENT_ID = "fixture-doc"
SECTION_COUNT = 8
PARAGRAPHS_PER_SECTION = 3


class DeterministicFixtureEmbedder:
    """Unit vectors derived from the text itself.

    No model is loaded and no network is touched, but the hybrid arm's
    arbitration path really runs -- and the same text always gets the same
    vector, which is what lets the reproducibility test mean something.
    """

    def embed_units(self, texts):
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()[:8]
            vector = np.frombuffer(digest, dtype=np.uint8).astype(np.float64) - 127.5
            vectors.append(vector / np.linalg.norm(vector))
        return SimpleNamespace(vectors=np.asarray(vectors, dtype=np.float64))


def _units() -> list[dict]:
    units: list[dict] = []
    order = 0
    for section in range(SECTION_COUNT):
        title = f"BOLUM {section}"
        order += 1
        units.append(
            {
                "document_id": DOCUMENT_ID,
                "unit_id": f"h-{order:05d}",
                "order": order,
                "text": title,
                "type": "heading",
                "heading_level": 2,
                "section_path": [title],
                "source": {"page": section + 1},
            }
        )
        for paragraph in range(PARAGRAPHS_PER_SECTION):
            order += 1
            words = " ".join(
                f"kelime{section}x{paragraph}n{index}" for index in range(18)
            )
            units.append(
                {
                    "document_id": DOCUMENT_ID,
                    "unit_id": f"p-{order:05d}",
                    "order": order,
                    "text": f"Bolum {section} paragraf {paragraph}. {words}.",
                    "type": "paragraph",
                    "section_path": [title],
                    "source": {"page": section + 1},
                }
            )
    return units


def _gold(units: list[dict], units_sha: str) -> dict:
    content = [unit for unit in units if unit["type"] != "heading"]
    queries = []
    for index, unit in enumerate(content[:20], start=1):
        queries.append(
            {
                "query_id": f"q{index:03d}",
                "question": f"Bolum {unit['section_path'][0]} icin {unit['text'][:40]}?",
                "evidence_unit_ids": [unit["unit_id"]],
                "evidence_pages": [unit["source"]["page"]],
                "expected_answer": None,
                "evidence_type": "narrative",
                "difficulty": "direct",
            }
        )
    return {
        "schema_version": "1.0",
        "document_id": DOCUMENT_ID,
        "source_units_file": "data/fixture.units.jsonl",
        "source_units_sha256": units_sha,
        "annotation_status": "manual_v2_development_checkpoint",
        "authoring_method": "generated fixture; never a claim about a real corpus",
        "queries": queries,
    }


def _write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8", newline="\n")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    units = _units()
    body = "".join(
        json.dumps(unit, ensure_ascii=False, sort_keys=True) + "\n" for unit in units
    )
    _write(tmp_path / "data" / "fixture.units.jsonl", body)
    units_sha = hashlib.sha256(
        (tmp_path / "data" / "fixture.units.jsonl").read_bytes()
    ).hexdigest()
    _write(
        tmp_path / "evaluation" / "gold.json",
        json.dumps(_gold(units, units_sha), ensure_ascii=False, indent=2) + "\n",
    )
    _write(
        tmp_path / "configs" / "bench.yaml",
        f"""benchmark:
  version: chunk-benchmark-v1
  status: development_checkpoint
source:
  units: data/fixture.units.jsonl
  units_sha256: {units_sha}
  gold_queries: evaluation/gold.json
arms:
  markdown:
    kind: markdown_recursive
    chunk_size_tokens: 120
    chunk_overlap_tokens: 20
  hybrid:
    kind: hybrid_h1
  structure-only:
    kind: structure_first
tokens:
  min_tokens: 20
  target_tokens: 120
  soft_max_tokens: 400
  hard_max_tokens: 900
bm25:
  k1: 1.5
  b: 0.75
  fold: turkish_diacritics_v1
boundary_embedding:
  config: configs/v4.yaml
evaluation:
  top_ks: [1, 3, 5]
  latency_repetitions: 3
  chunking_repetitions: 2
  token_counter_encoding: cl100k_base
""",
    )
    return tmp_path


def run(workspace: Path, output: str = "artifacts/out") -> dict:
    return run_benchmark(
        config_path=workspace / "configs" / "bench.yaml",
        output_dir=workspace / output,
        boundary_embedder=DeterministicFixtureEmbedder(),
        measure_parse_time=False,
        measure_cold_embedding_time=False,
    )


# ------------------------------------------------------------------ the run


def test_the_run_produces_every_planned_artifact(workspace: Path):
    run(workspace)
    output = workspace / "artifacts" / "out"

    for name in (
        "benchmark-summary.json",
        "benchmark-report.md",
        "resolved-config.json",
        "manifest.json",
        "parser-baseline.json",
        "query-comparison.jsonl",
    ):
        assert (output / name).is_file(), name
    for arm in ARMS:
        for name in (
            "chunks.jsonl",
            "timing.json",
            "retrieval.json",
            "query-results.jsonl",
            "structural_quality.json",
            "mapping.json",
        ):
            assert (output / arm / name).is_file(), f"{arm}/{name}"
        assert not (output / arm / "metrics.json").exists()


def test_only_the_three_arms_are_compared(workspace: Path):
    summary = run(workspace)

    assert summary["compared_arms"] == list(ARMS)
    assert set(summary["retrieval_metrics"]) == set(ARMS)
    for key in summary["query_comparison"]["pairwise_hit_at_5"]:
        assert "v4" not in key


def test_a_second_run_is_byte_identical_apart_from_timing(workspace: Path):
    run(workspace, "artifacts/first")
    run(workspace, "artifacts/second")

    for arm in ARMS:
        for name in ("chunks.jsonl", "structural_quality.json", "retrieval.json"):
            first = (workspace / "artifacts" / "first" / arm / name).read_bytes()
            second = (workspace / "artifacts" / "second" / arm / name).read_bytes()
            assert first == second, f"{arm}/{name} is not reproducible"
    first_report = (workspace / "artifacts" / "first" / "query-comparison.jsonl").read_bytes()
    second_report = (workspace / "artifacts" / "second" / "query-comparison.jsonl").read_bytes()
    assert first_report == second_report


def test_every_chunk_of_every_arm_can_be_scored(workspace: Path):
    run(workspace)
    output = workspace / "artifacts" / "out"

    for arm in ARMS:
        rows = [
            json.loads(line)
            for line in (output / arm / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert rows
        assert all(row["unit_ids"] for row in rows)


def test_the_parser_baseline_is_shared_and_excluded_from_every_arm(workspace: Path):
    summary = run(workspace)
    baseline = json.loads(
        (workspace / "artifacts" / "out" / "parser-baseline.json").read_text(encoding="utf-8")
    )

    assert baseline["finding_count"] == summary["parser_baseline_finding_count"]
    for arm in ARMS:
        qa = summary["structural_quality"][arm]["structural_qa"]
        assert qa["parser_baseline_finding_count"] == baseline["finding_count"]


# ---------------------------------------------------------------- the guards


def test_writing_into_evaluation_is_refused(workspace: Path):
    with pytest.raises(ValueError, match="evaluation/"):
        run(workspace, "evaluation/somewhere")


def test_an_output_directory_containing_an_input_is_refused(workspace: Path):
    with pytest.raises(ValueError, match="contains an input"):
        run(workspace, "data")


def test_a_top_k_the_metric_function_cannot_report_is_refused(workspace: Path):
    config = (workspace / "configs" / "bench.yaml").read_text(encoding="utf-8")
    (workspace / "configs" / "bench.yaml").write_text(
        config.replace("top_ks: [1, 3, 5]", "top_ks: [1, 3, 10]"),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValueError, match=r"exactly \[1, 3, 5\]"):
        run(workspace)


def test_a_canonical_corpus_that_drifted_is_refused(workspace: Path):
    path = workspace / "data" / "fixture.units.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8", newline="\n")

    with pytest.raises(ValueError, match="SHA256 mismatch"):
        run(workspace)


def test_the_arm_set_is_fixed(workspace: Path):
    config = (workspace / "configs" / "bench.yaml").read_text(encoding="utf-8")
    (workspace / "configs" / "bench.yaml").write_text(
        config.replace("  structure-only:\n    kind: structure_first\n", ""),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValueError, match="compared arms are exactly"):
        ChunkBenchmarkConfig.from_yaml(workspace / "configs" / "bench.yaml")


# ------------------------------------------------------- retrieval details


def test_fragment_ids_are_reduced_but_kept():
    row = {"chunk_id": "c-1", "text": "x", "unit_ids": ["t-1#f1", "t-1#f2", "p-2"]}

    normalized = normalize_unit_ids_for_retrieval(row)

    assert normalized["unit_ids"] == ["t-1", "p-2"]
    assert normalized["fragment_unit_ids"] == ["t-1#f1", "t-1#f2", "p-2"]
    assert row["unit_ids"] == ["t-1#f1", "t-1#f2", "p-2"]


def test_a_chunk_that_carries_content_but_no_ids_stops_the_run(workspace: Path):
    units = load_jsonl_units(workspace / "data" / "fixture.units.jsonl")
    counter = TiktokenTokenCounter("cl100k_base")
    paragraph = next(unit for unit in units if unit.type == UnitType.PARAGRAPH)
    # The text is really there; only the provenance was lost -- exactly the
    # fragment-id failure the guard exists for.
    rows = [{"chunk_id": "c-1", "text": paragraph.text, "unit_ids": [paragraph.unit_id]}]
    mapping = map_chunks(units, rows)
    rows[0]["unit_ids"] = ["ghost"]

    with pytest.raises(AssertionError, match="never be scored"):
        to_documents(rows, units, counter, mapping=mapping)


def test_a_chunk_made_only_of_headings_is_scored_zero_not_treated_as_a_defect(
    workspace: Path,
):
    """A size-first splitter really can emit one; it answers nothing, correctly."""
    units = load_jsonl_units(workspace / "data" / "fixture.units.jsonl")
    counter = TiktokenTokenCounter("cl100k_base")
    heading_unit = next(unit for unit in units if unit.type == UnitType.HEADING)
    rows = [{"chunk_id": "c-1", "text": heading_unit.text, "unit_ids": [], "heading": heading_unit.text}]
    mapping = map_chunks(units, rows)

    documents = to_documents(rows, units, counter, mapping=mapping)

    assert documents[0].unit_ids == ()


def test_the_index_returns_the_frozen_hit_type_so_repetitions_compare_equal():
    documents = [
        RetrievalDocument(chunk_id="c-1", text="findeks uyelik", unit_ids=("p-1",), pages=(1,), token_count=2),
        RetrievalDocument(chunk_id="c-2", text="baska bir konu", unit_ids=("p-2",), pages=(2,), token_count=3),
    ]
    index = BM25OnlyIndex(documents, k1=1.5, b=0.75, fold="turkish_diacritics_v1")

    first = index.search("findeks", None, top_k=2)
    second = index.search("findeks", None, top_k=2)

    assert first == second
    assert all(isinstance(hit, RetrievalHit) for hit in first)
    assert first[0].chunk_id == "c-1"
    assert first[0].dense_rank is None
    assert isinstance(first[0].rank, int) and isinstance(first[0].bm25_rank, int)
    json.dumps([hit.rank for hit in first])


def test_the_turkish_fold_lets_an_undotted_query_match():
    documents = [
        RetrievalDocument(chunk_id="c-1", text="Üyelik şartları", unit_ids=("p-1",), pages=(1,), token_count=2),
        RetrievalDocument(chunk_id="c-2", text="bambaska", unit_ids=("p-2",), pages=(2,), token_count=1),
    ]
    index = BM25OnlyIndex(documents, k1=1.5, b=0.75, fold="turkish_diacritics_v1")

    assert index.search("uyelik", None, top_k=1)[0].chunk_id == "c-1"


# ------------------------------------------------- the frozen chunker itself


def test_the_harness_adds_nothing_to_the_structure_first_chunker():
    """Gate: the structure-only arm must be the frozen chunker, verbatim.

    The benchmark reduces fragment ids before writing a corpus, which is the one
    transformation it is allowed to apply. Everything else -- ordering, text,
    token counts, headings, section paths -- has to survive untouched, or the
    arm is measuring the harness rather than the chunker.
    """
    from amsc.structural_chunker import chunk_units

    units = load_jsonl_units("data/kkb-2024.units.jsonl")
    counter = TiktokenTokenCounter("cl100k_base")

    direct = chunk_units(units, counter=counter)
    through_harness = [normalize_unit_ids_for_retrieval(row) for row in direct]

    assert len(through_harness) == len(direct)
    for original, written in zip(direct, through_harness):
        for key in (
            "chunk_id",
            "text",
            "token_count",
            "pages",
            "section_paths",
            "heading",
            "split_strategies",
        ):
            assert written[key] == original[key], key
        assert written["unit_ids"] == [
            unit_id.split("#")[0]
            for index, unit_id in enumerate(original["unit_ids"])
            if unit_id.split("#")[0]
            not in [item.split("#")[0] for item in original["unit_ids"][:index]]
        ]
