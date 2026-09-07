"""The chunking-method registry, and the extension path it exists for.

Two things are proved here. First, that the registry is the one place a
method's identity lives and that every consumer reads it: the Viewer
builder, the reader's arm gate, the benchmark's dispatch and config
validation, the relation deriver. Second -- the proof that matters --
that a *fifth* method added through the intended path (write a partition,
register it) reaches all of them with no other edit, and that unregistering
it makes it unknown everywhere again. The fifth method is the shipped
example (:mod:`amsc.chunking.example`), registered only for the length of a
test.

**What is pinned and what is not.** The four shipped methods' wire identity
-- key, engine kind, product label -- is a product contract: renaming one
breaks a console, a packaged manifest and a Viewer arm at once, so each is
written down here. The *number* of registered methods is not a contract, and
nothing below asserts one: the tests are invariants over whatever is
registered (keys and kinds unique, a non-deep method has a partition, a deep
one has a baseline that is a registered partition, ``meta()`` describes every
key), so adding a valid fifth method needs no edit to this file. The one list
that is deliberately exact is the frozen benchmark's arm set, which is a
contract about a completed experiment.

Dispatch is also held to the engines it replaced: running Markdown,
Standard and Hybrid through the registry yields exactly the rows the engine
functions yield when called directly, so the refactor moved no boundary.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from types import SimpleNamespace

import pytest

from amsc.chunking import relations as chunk_relations
from amsc.deep import arm as deep_arm
from amsc.chunking import hybrid as hybrid_chunker
from amsc.chunking import markdown as markdown_chunker
from amsc.chunking import registry as methods
from amsc.chunking import structural as structural_chunker
from amsc.viewer import corpus as viewer_corpus
from amsc.viewer import build as viewer_v3
from amsc.research.benchmark.chunkers import ArmConfig, TokenBudget, run_arm
from amsc.chunking.example import FIXED_WINDOW, partition_fixed_window
from amsc.document.models import RawDocumentUnit

from conftest import StaticBoundaryEmbedder
from _chunk_fixtures import heading, unit, words
from _viewer_fixtures import make_tree

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
#: The wire identity of the methods the library ships: key -> (kind, label).
#: A rename here is a rename in a console's request, a packaged manifest and a
#: Viewer arm at once, so it is written down. A statement about these four,
#: never about how many methods are registered.
SHIPPED = {
    "markdown": ("markdown_recursive", "Markdown"),
    "hybrid": ("hybrid_h1", "Hybrid"),
    "structure-only": ("structure_first", "Standard"),
    "agentic": ("deep_analysis", "Deep Analysis"),
}


def test_the_shipped_methods_keep_their_wire_identity():
    """The four keys, kinds and labels, and the order they are listed in.

    Deliberately not an equality against the whole registry: a fifth method
    registered beside them is valid and must not fail this.
    """
    for key, (kind, label) in SHIPPED.items():
        assert methods.is_known(key), f"the shipped method {key!r} is gone"
        assert methods.get(key).kind == kind
        assert methods.LABELS[key] == label
    listed = [key for key in methods.order() if key in SHIPPED]
    assert listed == ["markdown", "hybrid", "structure-only", "agentic"]
    assert methods.benchmark_arms() == ("markdown", "hybrid", "structure-only"), (
        "the frozen benchmark's arm set is a contract about a finished experiment"
    )
    for key, capability in (("agentic", "uses_model"), ("hybrid", "needs_embedder"),
                            ("markdown", "sized")):
        assert getattr(methods.get(key), capability) is True, f"{key}.{capability}"
    for key in SHIPPED:
        if key != "agentic":
            assert methods.get(key).uses_model is False, key
    for key in SHIPPED:
        if key != "hybrid":
            assert methods.get(key).needs_embedder is False, key


def test_the_registry_holds_together_whatever_is_in_it():
    """The invariants a registration has to satisfy -- over every method
    registered, not over a list of four. This is what a new method is held to
    instead of being written into a snapshot."""
    registered = methods.methods()
    keys = [m.key for m in registered]
    kinds = [m.kind for m in registered]
    assert keys == list(methods.ORDER) == list(methods.kinds())
    assert len(keys) == len(set(keys)), f"two methods share a key: {keys}"
    assert len(kinds) == len(set(kinds)), f"two methods share an engine kind: {kinds}"

    partitions = set(methods.partition_methods())
    for method in registered:
        assert method.key and method.kind, method
        assert method.label.strip(), f"{method.key} has no product name"
        assert method.summary.strip(), f"{method.key} has no summary"
        assert isinstance(method.options, Mapping), method.key
        if method.deep:
            assert method.partition is None, f"{method.key} is deep and a partition"
            assert method.key not in partitions
            assert method.baseline in partitions, (
                f"{method.key} starts from {method.baseline!r}, which is not a "
                "registered partition method"
            )
            assert not method.benchmark_arm, "an orchestration is not a benchmark arm"
        else:
            assert callable(method.partition), f"{method.key} has no partition callable"
            assert method.key in partitions
            assert method.baseline is None
        # Capability combinations a consumer relies on.
        assert not (method.needs_embedder and method.deep), method.key
        assert not (method.sized and method.deep), method.key
        assert methods.by_kind(method.kind) is method
        assert methods.kind_arbitrates(method.kind) is method.arbitrated_cuts

    deep = methods.deep_method()
    assert deep is None or deep.deep
    assert [m.key for m in registered if m.deep] == ([deep.key] if deep else []), (
        "at most one orchestration: the page finds it by the flag, not by name"
    )
    assert set(methods.benchmark_arms()) <= partitions

    described = methods.meta()
    assert list(described) == keys, "meta() describes exactly what is registered"
    for method in registered:
        assert described[method.key] == {
            "kind": method.kind, "deep": method.deep, "baseline": method.baseline,
            "needsEmbedder": method.needs_embedder, "usesModel": method.uses_model,
            "benchmarkArm": method.benchmark_arm,
        }
        assert all(not callable(value) for value in described[method.key].values())


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
    with pytest.raises(methods.NotAPartition, match=r"deep\.pipeline"):
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
    before = methods.order()
    clash = methods.ChunkMethod(key="twin", kind="structure_first", label="T", summary="",
                                partition=lambda *a, **k: None)
    with pytest.raises(ValueError, match="which 'structure-only' already uses"):
        methods.register(clash)
    with pytest.raises(ValueError, match="already registered"):
        methods.register(methods.STANDARD)
    assert methods.order() == before, "nothing slipped in"


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

    # The reader's arm gate: an arm packaged under its kind is read.
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
    assert viewer_corpus.ARM_KINDS["fixed-window"] == "fixed_window"
    payload = viewer_corpus.load_corpus(tree, tmp_path, extra_arm_dirs={"fixed-window": tmp_path / "fw"})
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


def test_a_page_built_before_the_method_existed_still_lists_it_when_served(fifth, tmp_path):
    """The Viewer exposure rule: no manual rebuild.

    A built page carries the registry as it was at build time -- that is all a
    file opened from disk can have. Served, it asks the server for the registry
    as it is *now*, so a method registered after the page was built is listed
    without anyone remembering ``python -m amsc.viewer.build``. Proved from both
    ends: the stale page really is stale, and the route really is current.
    """
    from amsc.viewer import server as viewer_server

    methods.unregister(FIXED_WINDOW.key)          # build the page without it
    output = tmp_path / "v3" / "index.html"
    viewer_v3.build_viewer({}, output, root=tmp_path)
    methods.register(FIXED_WINDOW)                # ...then register it

    embedded = _payload(output.read_text(encoding="utf-8"))
    assert "fixed-window" not in embedded["methodOrder"], "the built page is stale, as expected"

    served = viewer_server.method_registry_payload()
    assert served["order"] == list(methods.ORDER) and served["order"][-1] == "fixed-window"
    assert served["labels"] == dict(methods.LABELS)
    assert served["summaries"] == dict(methods.SUMMARIES)
    assert served["meta"] == methods.meta()

    # The page asks for it, and prefers what it gets over what it was built with.
    page = output.read_text(encoding="utf-8")
    assert '"/api/methods"' in page and "refreshMethods" in page
    assert "DATA.methodOrder = m.order" in page


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
        viewer_corpus.load_corpus(tree, tmp_path, extra_arm_dirs={"fixed-window": tmp_path / "fw"})
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
