"""The chunking-method registry, and the extension path it exists for.

Two things are proved here. First, that the registry is the one place a
method's identity lives and that every consumer reads it: the Viewer
builders, the Viewer v2 reader's arm gate, the benchmark's dispatch and
config validation, the relation deriver. Second -- the proof that matters --
that a *fifth* method added through the intended path (write a partition,
register it) reaches all of them with no other edit, and that unregistering
it makes it unknown everywhere again. The fifth method is the shipped
example (:mod:`amsc.example_chunker`), registered only for the length of a
test.

Dispatch is also held to the engines it replaced: running Markdown,
Standard and Hybrid through the registry yields exactly the rows the engine
functions yield when called directly, so the refactor moved no boundary.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from amsc import chunk_relations, deep_arm, hybrid_chunker, markdown_chunker, methods
from amsc import structural_chunker, viewer_v2, viewer_v3
from amsc.chunk_benchmark import ArmConfig, TokenBudget, run_arm
from amsc.example_chunker import FIXED_WINDOW, partition_fixed_window
from amsc.models import RawDocumentUnit

from conftest import StaticBoundaryEmbedder
from _chunk_fixtures import heading, unit, words
from test_viewer_v2 import make_tree

BUDGET = dict(min_tokens=50, target_tokens=150, soft_max_tokens=160, hard_max_tokens=1000)


class Counter:
    counter_id = "test:whitespace@1"

    def count(self, text: str) -> int:
        return len(text.split())

    def split(self, text: str, max_tokens: int) -> list[str]:
        tokens = text.split()
        return [" ".join(tokens[i:i + max_tokens]) for i in range(0, len(tokens), max_tokens)] or [""]


COUNTER = Counter()


def section_of(*bodies: str, title: str = "H"):
    units = [heading("h-1", title, 1)]
    for index, body in enumerate(bodies, start=1):
        units.append(unit(f"p-{index}", body, order=index + 1, section=(title,)))
    return units


def four_paragraphs():
    return [words(60, f"s{index}") for index in range(4)]


# ------------------------------------------------------------- identity
def test_the_four_shipped_methods_and_their_identity():
    assert methods.order() == ("markdown", "hybrid", "structure-only", "agentic")
    assert methods.kinds() == {
        "markdown": "markdown_recursive", "hybrid": "hybrid_h1",
        "structure-only": "structure_first", "agentic": "deep_analysis",
    }
    assert dict(methods.LABELS) == {
        "markdown": "Markdown", "hybrid": "Hybrid",
        "structure-only": "Standard", "agentic": "Deep Analysis",
    }
    assert methods.benchmark_arms() == ("markdown", "hybrid", "structure-only")
    assert methods.partition_methods() == ("markdown", "hybrid", "structure-only")
    assert [m.key for m in methods.methods() if m.uses_model] == ["agentic"]
    assert [m.key for m in methods.methods() if m.needs_embedder] == ["hybrid"]
    assert [m.key for m in methods.methods() if m.sized] == ["markdown"]
    kinds = [m.kind for m in methods.methods()]
    assert len(kinds) == len(set(kinds)), "no two methods share an engine kind"


def test_deep_analysis_is_an_orchestration_over_standard():
    deep = methods.deep_method()
    assert deep is not None and deep.key == "agentic" and deep.deep
    assert deep.partition is None and deep.baseline == "structure-only"
    assert deep.kind == deep_arm.ARM_KIND == methods.DEEP_KIND
    meta = methods.meta()
    assert meta["agentic"] == {"kind": "deep_analysis", "deep": True, "baseline": "structure-only",
                               "needsEmbedder": False, "usesModel": True, "benchmarkArm": False}
    assert meta["structure-only"]["deep"] is False and meta["structure-only"]["baseline"] is None


def test_an_unknown_method_fails_naming_the_known_ones():
    with pytest.raises(methods.UnknownMethod) as unknown:
        methods.get("turbo")
    assert "'turbo'" in str(unknown.value) and "'structure-only'" in str(unknown.value)
    assert isinstance(unknown.value, KeyError)
    with pytest.raises(methods.UnknownMethod, match="kind 'nope'"):
        methods.by_kind("nope")
    with pytest.raises(methods.UnknownMethod):
        methods.unregister("turbo")
    assert not methods.is_known("turbo")


def test_deep_analysis_is_described_but_cannot_be_run_as_a_partition():
    with pytest.raises(methods.NotAPartition, match="deep_pipeline"):
        methods.partition("agentic", section_of(words(20)), counter=COUNTER, budget=BUDGET)


def test_a_method_literal_is_validated_when_written():
    ok = dict(kind="k", label="L", summary="S", partition=lambda *a, **k: None)
    with pytest.raises(ValueError, match="orchestration is not a partition"):
        methods.ChunkMethod(key="x", deep=True, **ok)
    with pytest.raises(ValueError, match="needs a partition"):
        methods.ChunkMethod(key="x", kind="k", label="L", summary="S")
    with pytest.raises(ValueError, match="only a deep method has a baseline"):
        methods.ChunkMethod(key="x", baseline="structure-only", **ok)
    with pytest.raises(ValueError, match="needs both a key and a kind"):
        methods.ChunkMethod(key="", **ok)


def test_a_key_or_kind_collision_is_refused():
    clash = methods.ChunkMethod(key="twin", kind="structure_first", label="T", summary="",
                                partition=lambda *a, **k: None)
    with pytest.raises(ValueError, match="which 'structure-only' already uses"):
        methods.register(clash)
    with pytest.raises(ValueError, match="already registered"):
        methods.register(methods.STANDARD)
    assert methods.order() == ("markdown", "hybrid", "structure-only", "agentic"), "nothing slipped in"


# ------------------------------------------------- dispatch equals engines
def test_markdown_dispatch_is_the_markdown_engine():
    units = section_of(*four_paragraphs())
    result = methods.partition("markdown", units, counter=COUNTER, budget=BUDGET,
                               chunk_size_tokens=40, chunk_overlap_tokens=5)
    direct = markdown_chunker.chunk_units(units, counter=COUNTER, chunk_size_tokens=40,
                                          chunk_overlap_tokens=5, hard_max_tokens=1000)
    assert result.rows == direct
    assert result.spans == dict(markdown_chunker.render_markdown(units).spans)
    assert result.diagnostics == {"chunk_size_tokens": 40, "chunk_overlap_tokens": 5,
                                  "tuning_status": markdown_chunker.TUNING_STATUS}
    # The live defaults are the frozen benchmark's sizes.
    assert methods.MARKDOWN.options == {"chunk_size_tokens": 700, "chunk_overlap_tokens": 140}


def test_standard_dispatch_is_the_structural_engine():
    units = section_of(*four_paragraphs())
    result = methods.partition("structure-only", units, counter=COUNTER, budget=BUDGET)
    assert result.rows == structural_chunker.chunk_units(units, counter=COUNTER, **BUDGET)
    assert result.diagnostics == {"respect_semantic_roles": False} and result.spans is None


def test_hybrid_dispatch_is_the_hybrid_engine_and_the_embedder_is_loaded_lazily():
    bodies = four_paragraphs()
    units = section_of(*bodies)
    embedder = StaticBoundaryEmbedder(dict(zip(bodies, [[1.0, 0.0], [0.0, 1.0], [0.0, 1.0], [0.0, 1.0]])))
    loads = []

    def loader():
        loads.append(1)
        return embedder

    result = methods.partition("hybrid", units, counter=COUNTER, budget=BUDGET, boundary_embedder=loader)
    direct = hybrid_chunker.chunk_units(units, counter=COUNTER, boundary_embedder=embedder, **BUDGET)
    assert result.rows == direct.chunks and result.diagnostics == direct.diagnostics
    assert loads == [1], "the loader ran once, for the one method that needs it"
    assert result.diagnostics["arbitration_changed_boundary_count"] >= 1, "arbitration really ran"


def test_a_method_that_needs_no_embedder_never_asks_for_one():
    calls = []
    methods.partition("structure-only", section_of(words(20)), counter=COUNTER, budget=BUDGET,
                      boundary_embedder=lambda: calls.append(1))
    methods.partition("markdown", section_of(words(20)), counter=COUNTER, budget=BUDGET,
                      boundary_embedder=lambda: calls.append(1), chunk_size_tokens=10, chunk_overlap_tokens=2)
    assert calls == []


def test_hybrid_without_an_embedder_is_refused_clearly():
    with pytest.raises(ValueError, match="'hybrid' needs a boundary embedder"):
        methods.partition("hybrid", section_of(words(20)), counter=COUNTER, budget=BUDGET)


# ------------------------------------------------ the fifth chunker's path
@pytest.fixture
def fifth():
    """The example method, registered for one test and gone afterwards."""
    methods.register(FIXED_WINDOW)
    try:
        yield FIXED_WINDOW
    finally:
        methods.unregister(FIXED_WINDOW.key)


def test_the_example_partition_is_predictable():
    units = [heading("h-1", "A", 1)]
    for index in range(1, 6):
        units.append(unit(f"p-{index}", words(10, f"a{index}"), order=index + 1, section=("A",)))
    units.append(heading("h-2", "B", 7))
    units.append(unit("p-6", words(10, "b1"), order=8, section=("B",)))

    result = partition_fixed_window(units, counter=COUNTER, budget=BUDGET)

    assert [row["unit_ids"] for row in result.rows] == [["p-1", "p-2", "p-3"], ["p-4", "p-5"], ["p-6"]]
    assert result.rows[0]["chunk_id"] == "doc:fw-chunk-0001"
    assert result.rows[0]["token_count"] == 30 and result.rows[0]["section_paths"] == [["A"]]
    assert set(result.rows[0]) == {"chunk_id", "text", "unit_ids", "token_count", "pages",
                                   "section_paths", "heading", "split_strategies"}
    # The target is a ceiling too: two 100-word units do not share a window.
    big = section_of(words(100, "x"), words(100, "y"))
    assert [row["unit_ids"] for row in partition_fixed_window(big, counter=COUNTER, budget=BUDGET).rows] == [["p-1"], ["p-2"]]


def _payload(html_text: str) -> dict:
    match = re.search(r'<script id="viewer-data" type="application/json">(.*?)</script>', html_text, re.S)
    assert match
    return json.loads(match.group(1).replace("<\\/", "</"))


def test_a_registered_method_reaches_every_consumer_with_no_other_edit(fifth, tmp_path):
    # The registry's own views.
    assert "fixed-window" in methods.ORDER and methods.ORDER[-1] == "fixed-window"
    assert methods.LABELS["fixed-window"] == "Sabit Pencere"
    assert methods.get("fixed-window").partition is partition_fixed_window
    assert methods.benchmark_arms() == ("markdown", "hybrid", "structure-only"), "the frozen arm set is a contract, not a list"

    # The Viewer v3 builder: the shell build lists it, with its capabilities.
    output = tmp_path / "v3" / "index.html"
    viewer_v3.build_viewer({}, output, root=tmp_path)
    data = _payload(output.read_text(encoding="utf-8"))
    assert data["methodOrder"][-1] == "fixed-window"
    assert data["methodLabels"]["fixed-window"] == "Sabit Pencere"
    assert data["methodMeta"]["fixed-window"] == {"kind": "fixed_window", "deep": False, "baseline": None,
                                                  "needsEmbedder": False, "usesModel": False, "benchmarkArm": False}

    # The Viewer v2 reader's arm gate: an arm packaged under its kind is read.
    tree = make_tree(tmp_path)
    # The fixture tree's canonical, read row by row: its ``order`` values are
    # not unique (a fixture shortcut), which the strict loader refuses.
    units = [
        RawDocumentUnit.model_validate(json.loads(line))
        for line in (tmp_path / "data" / "doc.units.v3.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = partition_fixed_window(units, counter=COUNTER, budget=BUDGET).rows
    packaged = deep_arm.package_arm(rows, units=units, output_dir=tmp_path / "fw", counter=COUNTER)
    assert packaged["chunk_count"] == len(rows)
    assert viewer_v2.ARM_KINDS["fixed-window"] == "fixed_window"
    payload = viewer_v2.load_corpus(tree, tmp_path, extra_arm_dirs={"fixed-window": tmp_path / "fw"})
    assert payload["arms"]["fixed-window"]["kind"] == "fixed_window"
    assert len(payload["arms"]["fixed-window"]["chunks"]) == len(rows)
    assert all(chunk["rs"] for chunk in payload["arms"]["fixed-window"]["chunks"]), "boundary reasons are read"

    # The benchmark: its config accepts the kind and its dispatch runs it.
    arm = ArmConfig(kind="fixed_window")
    config = SimpleNamespace(arms={"structure-only": arm}, tokens=TokenBudget(**BUDGET))
    bench_rows, diagnostics, spans = run_arm("structure-only", config, units, COUNTER, boundary_embedder=None)
    assert bench_rows == rows and diagnostics == {"max_units": 3} and spans is None

    # The relation deriver: its cuts are greedy, because it declared no arbitration.
    assert chunk_relations._arbitrates("fixed_window") is False
    assert chunk_relations._arbitrates("hybrid_h1") and chunk_relations._arbitrates("deep_analysis")
    assert chunk_relations._arbitrates(chunk_relations.LEGACY_AGENTIC_KIND)


def test_once_unregistered_the_method_is_unknown_everywhere(tmp_path):
    methods.register(FIXED_WINDOW)
    methods.unregister(FIXED_WINDOW.key)

    assert "fixed-window" not in methods.ORDER and not methods.is_known("fixed-window")
    with pytest.raises(methods.UnknownMethod):
        methods.get("fixed-window")
    with pytest.raises(ValueError, match="unknown chunking method kind 'fixed_window'"):
        ArmConfig(kind="fixed_window")
    tree = make_tree(tmp_path)
    (tmp_path / "fw").mkdir()
    with pytest.raises(ValueError, match="unknown arm 'fixed-window'"):
        viewer_v2.load_corpus(tree, tmp_path, extra_arm_dirs={"fixed-window": tmp_path / "fw"})
    output = tmp_path / "v3" / "index.html"
    viewer_v3.build_viewer({}, output, root=tmp_path)
    assert "fixed-window" not in _payload(output.read_text(encoding="utf-8"))["methodOrder"]


# ---------------------------------------------- the benchmark's contract
def test_the_benchmark_config_validates_kinds_against_the_registry():
    assert ArmConfig(kind="markdown_recursive", chunk_size_tokens=700, chunk_overlap_tokens=140)
    with pytest.raises(ValueError, match="needs chunk_size and chunk_overlap"):
        ArmConfig(kind="markdown_recursive")
    with pytest.raises(ValueError, match="takes its sizes from the shared token budget"):
        ArmConfig(kind="structure_first", chunk_size_tokens=700, chunk_overlap_tokens=140)
    with pytest.raises(ValueError, match="no section machine"):
        ArmConfig(kind="markdown_recursive", chunk_size_tokens=700, chunk_overlap_tokens=140,
                  respect_semantic_roles=True)
    with pytest.raises(ValueError, match="orchestration, not a benchmark arm"):
        ArmConfig(kind="deep_analysis")
    with pytest.raises(ValueError, match="unknown chunking method kind"):
        ArmConfig(kind="quantum")
