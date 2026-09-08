"""The chunk contract and the plugin path: what a chunker owes, and nothing more.

Three things are proved here.

**Discovery.** A ``.py`` file dropped into ``amsc/chunking/plugins/`` is a
chunking method -- registered, listed, dispatchable -- with no other edit
anywhere. The tests write a real file into the real directory and take it away
again, because a test that only proves discovery over a temporary package
proves the mechanism and not the path an author would actually take.

**Derivation.** A chunker gives text and provenance; the framework works out
the chunk id, the token count, the pages, the section paths, the heading and
how the units were cut. Provenance is either the unit ids the chunker packed
or a character span in the rendering it was handed, and the span is resolved
by intersecting character ranges -- which is why a document that repeats a
paragraph still attributes each chunk to the occurrence it actually holds.
Nothing here searches for text.

**The boundary.** A row that does not satisfy the method's own declaration
fails at :func:`amsc.chunking.registry.partition`, naming the method and the
chunk, rather than reaching a consumer and surfacing as a ``KeyError`` -- which
is what it did before this module existed. The other half of the same claim:
a method that declares nothing beyond the core four is read by every consumer
without complaint, so no chunker is obliged to produce a field it has no
opinion about merely because another chunker does.
"""

from __future__ import annotations

import importlib
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from amsc.chunking import contract, discovery, mapping as chunk_mapping
from amsc.chunking import registry as methods
from amsc.chunking import relations as chunk_relations
from amsc.chunking.contract import Capability, Chunk, ChunkResult, ContractError, chunker
from amsc.chunking.markdown import render_markdown
from amsc.document.models import UnitType
from amsc.quality import chunks as chunk_quality

from _chunk_fixtures import heading, unit, words

BUDGET = dict(min_tokens=50, target_tokens=150, soft_max_tokens=160, hard_max_tokens=1000)
PLUGIN_DIR = Path(importlib.import_module(discovery.PLUGIN_PACKAGE).__file__).parent


class Counter:
    counter_id = "test:whitespace@1"

    def count(self, text: str) -> int:
        return len(text.split())

    def split(self, text: str, max_tokens: int) -> list[str]:
        pieces = text.split()
        return [" ".join(pieces[i:i + max_tokens]) for i in range(0, len(pieces), max_tokens)] or [""]


COUNTER = Counter()


def corpus(*bodies: str, title: str = "A", pages=(1, 1, 1, 1)):
    """A heading and its paragraphs, each on a page, in one section."""
    units = [heading("h-1", title, 1)]
    for index, body in enumerate(bodies, start=1):
        made = unit(f"p-{index}", body, order=index + 1, section=(title,))
        made = made.model_copy(update={"source": made.source.model_copy(
            update={"page": pages[index - 1] if index - 1 < len(pages) else None})})
        units.append(made)
    return units


@contextmanager
def registered(*built):
    """Register methods for one test and take them away again."""
    for method in built:
        methods.register(method)
    try:
        yield built[0] if len(built) == 1 else built
    finally:
        for method in built:
            if methods.is_known(method.key):
                methods.unregister(method.key)


def run(method, units, **options):
    with registered(method):
        return methods.partition(method.key, units, counter=COUNTER, budget=BUDGET, **options)


# ---------------------------------------------------------------- discovery

@contextmanager
def dropped_in(name: str, source: str):
    """Write a plugin file into the real plugin directory, then take it back.

    The point of the whole exercise is that this is all an author does, so the
    test does exactly that and nothing else -- no temporary package, no
    injected loader.
    """
    path = PLUGIN_DIR / f"{name}.py"
    assert not path.exists(), f"{path} already exists; the test would clobber it"
    path.write_text(source, encoding="utf-8")
    importlib.invalidate_caches()
    added = ()
    try:
        added = methods.discover()
        yield added
    finally:
        for method in added:
            if methods.is_known(method.key):
                methods.unregister(method.key)
        sys.modules.pop(f"{discovery.PLUGIN_PACKAGE}.{name}", None)
        path.unlink(missing_ok=True)
        shutil.rmtree(PLUGIN_DIR / "__pycache__", ignore_errors=True)
        importlib.invalidate_caches()


PLUGIN_SOURCE = '''
"""A method that exists only for the length of one test."""

from ..contract import Chunk, chunker


@chunker(key="drop-in", label="Drop In", summary="Her birim bir parça.")
def drop_in(units, **options):
    for unit in units:
        yield Chunk(text=unit.text, unit_ids=[unit.unit_id])
'''


def test_a_new_plugin_file_is_a_registered_method_with_no_other_edit():
    """The whole extension path: add a file, and every surface has it.

    No import is added anywhere, no tuple is edited, no list is updated. The
    file is the registration.
    """
    assert not methods.is_known("drop-in")
    with dropped_in("drop_in_probe", PLUGIN_SOURCE) as added:
        assert [m.key for m in added] == ["drop-in"]

        # The registry knows it, and its views are current.
        method = methods.get("drop-in")
        assert method.label == "Drop In" and method.kind == "drop_in"
        assert "drop-in" in methods.ORDER and methods.ORDER[-1] == "drop-in", (
            "a new method sorts after the shipped four, which claim 10..40"
        )
        assert methods.LABELS["drop-in"] == "Drop In"
        assert methods.KINDS["drop-in"] == "drop_in"
        assert methods.meta()["drop-in"]["kind"] == "drop_in"
        assert methods.by_kind("drop_in") is method
        assert "drop-in" in methods.partition_methods()
        assert "drop-in" not in methods.benchmark_arms(), (
            "the frozen benchmark's arm set is a finished experiment"
        )

        # And it runs, through the same dispatch every other method uses.
        rows = methods.partition("drop-in", corpus(words(5), words(5)),
                                 counter=COUNTER, budget=BUDGET).rows
        assert [row["unit_ids"] for row in rows] == [["h-1"], ["p-1"], ["p-2"]]
        assert rows[0]["chunk_id"] == "doc:drop-in-chunk-0001", (
            "the id infix defaults to the key, so a plugin need not invent one"
        )

    assert not methods.is_known("drop-in"), "and it is gone again"
    assert "drop-in" not in methods.ORDER


def test_the_shipped_methods_are_exactly_what_the_plugin_directory_declares():
    """There is no second source of methods -- no tuple beside the directory."""
    declared = {method.key for method in discovery.discover()}
    assert declared == set(methods.order())
    assert declared == {"markdown", "hybrid", "structure-only", "agentic"}
    files = {name.rsplit(".", 1)[-1] for name in discovery.plugin_module_names()}
    assert files == {"markdown", "hybrid", "standard", "deep"}


def test_discovering_twice_registers_nothing_twice():
    """A server may rescan the directory; rescanning is not re-registering."""
    before = methods.order()
    assert methods.discover() == ()
    assert methods.order() == before


def test_a_helper_in_the_plugin_directory_is_not_a_method():
    """An underscore-prefixed file is a helper, so a plugin may have one."""
    source = 'from ..contract import Chunk, chunker\n\nWHATEVER = 1\n'
    with dropped_in("_shared_probe", source) as added:
        assert added == ()
    assert "_shared_probe" not in " ".join(discovery.plugin_module_names())


def test_two_plugins_claiming_one_key_name_both_files():
    with dropped_in("drop_in_probe", PLUGIN_SOURCE):
        with pytest.raises(ValueError, match=r"two chunking plugins declare the key 'drop-in'"):
            with dropped_in("drop_in_twin", PLUGIN_SOURCE):
                pass


def test_a_plugin_that_cannot_be_imported_names_the_file():
    with pytest.raises(ImportError, match=r"broken_probe.*could not be imported"):
        with dropped_in("broken_probe", "import amsc_no_such_module\n"):
            pass


# ------------------------------------------------------- the minimum contract

@chunker(key="t-minimal", kind="t_minimal", label="Minimal", capabilities=[])
def minimal(units, **options):
    """Everything a chunker must do: say the text, and say where it came from."""
    return [Chunk(text=u.text, unit_ids=[u.unit_id]) for u in units]


def test_a_minimal_chunker_gives_text_and_provenance_and_nothing_else():
    rows = run(minimal.chunk_method, corpus(words(4), words(4))).rows

    assert [set(row) for row in rows] == [set(contract.CORE_FIELDS)] * 3, (
        "a method that declares no capabilities emits the four core fields"
    )
    assert rows[1] == {
        "chunk_id": "doc:t-minimal-chunk-0002",
        "text": rows[1]["text"],
        "unit_ids": ["p-1"],
        "token_count": 4,
    }


def test_the_framework_derives_the_row_from_the_provenance():
    """The four optional fields a default declaration carries, all derived."""
    units = corpus(words(3), words(3), pages=(4, 7))

    @chunker(key="t-derive", kind="t_derive", label="Derive")
    def whole_section(us, **options):
        yield Chunk(
            text="\n\n".join(u.text for u in us),
            unit_ids=[u.unit_id for u in us],
        )

    row = run(whole_section.chunk_method, units).rows[0]

    assert row["chunk_id"] == "doc:t-derive-chunk-0001"
    assert row["token_count"] == COUNTER.count(row["text"]) == 7
    assert row["unit_ids"] == ["h-1", "p-1", "p-2"]
    assert row["pages"] == [4, 7], "pages come from the content units, headings aside"
    assert row["section_paths"] == [["A"]]
    assert row["heading"] == "A", "the heading unit the chunk carries"
    assert row["split_strategies"] == ["whole"], "no fragment id, so nothing was cut"


def test_a_partition_is_handed_only_what_it_names():
    """``def chunk(units, *, counter)`` is a complete partition.

    The framework offers a counter, a budget, an embedder and the method's own
    options; a method takes what it named and is not obliged to absorb the
    rest in ``**kwargs``.
    """
    seen: dict[str, object] = {}

    @chunker(key="t-asks", kind="t_asks", label="Asks", options={"flavour": "salt"})
    def asks(units, *, counter, flavour):
        seen["counter"] = counter
        seen["flavour"] = flavour
        return [Chunk(text=units[0].text, unit_ids=[units[0].unit_id])]

    run(asks.chunk_method, corpus(words(3)))
    assert seen == {"counter": COUNTER, "flavour": "salt"}


def test_a_chunker_may_record_diagnostics_without_building_a_row():
    @chunker(key="t-diag", kind="t_diag", label="Diag")
    def diag(units, **options):
        return ChunkResult(
            [Chunk(text=units[0].text, unit_ids=[units[0].unit_id])],
            {"looked_at": len(units)},
        )

    result = run(diag.chunk_method, corpus(words(3), words(3)))
    assert result.diagnostics == {"looked_at": 3} and len(result.rows) == 1


# ------------------------------------------- provenance by offset, not search

@chunker(
    key="t-offset",
    kind="t_offset",
    label="Offset",
    capabilities=[Capability.PAGES, Capability.HIERARCHY, Capability.PROVENANCE,
                  Capability.OFFSETS],
)
def by_offset(units, *, document):
    """One chunk per content unit, located by its range in the rendering."""
    for u in units:
        if u.type is UnitType.HEADING:
            continue
        start, end = document.spans[u.unit_id]
        yield Chunk(text=document.text[start:end], span=(start, end))


def test_a_span_is_resolved_to_its_units_arithmetically():
    units = corpus(words(3, "a"), words(3, "b"), pages=(2, 5))
    spans = render_markdown(units).spans

    result = run(by_offset.chunk_method, units)

    assert [row["unit_ids"] for row in result.rows] == [["p-1"], ["p-2"]]
    assert [(row["char_start"], row["char_end"]) for row in result.rows] == [
        spans["p-1"], spans["p-2"],
    ]
    assert [row["pages"] for row in result.rows] == [[2], [5]]
    assert result.spans == dict(spans), (
        "the rendering travels with the result, so the chunk mapper can use "
        "its offset rung"
    )


def test_repeated_text_maps_to_the_occurrence_the_chunk_actually_holds():
    """The reason provenance is never inferred from the text.

    Both paragraphs read the same. A chunker that found its units by searching
    for the chunk's text would attribute the second chunk to the first
    paragraph -- wrong page, wrong section, wrong highlight. Intersecting
    character ranges cannot make that mistake.
    """
    same = "aynı satır burada"
    units = corpus(same, same, pages=(3, 9))

    rows = run(by_offset.chunk_method, units).rows

    assert rows[0]["text"] == rows[1]["text"] == same
    assert [row["unit_ids"] for row in rows] == [["p-1"], ["p-2"]]
    assert [row["pages"] for row in rows] == [[3], [9]]
    assert rows[0]["char_start"] < rows[1]["char_start"]

    # And the shared mapper agrees, by the same arithmetic.
    located = chunk_mapping.map_chunks(units, rows, unit_spans=render_markdown(units).spans)
    assert [c.unit_ids() for c in located.chunks] == [("p-1",), ("p-2",)]
    assert {s.method for c in located.chunks for s in c.segments} == {chunk_mapping.MAP_OFFSET}


def test_a_span_that_covers_part_of_a_unit_says_so():
    units = corpus(words(10, "a"))
    start, end = render_markdown(units).spans["p-1"]

    @chunker(key="t-half", kind="t_half", label="Half",
             capabilities=[Capability.PROVENANCE, Capability.OFFSETS])
    def half(us, *, document):
        yield Chunk(text=document.text[start:start + 5], span=(start, start + 5))

    row = run(half.chunk_method, units).rows[0]
    assert row["split_strategies"] == ["partial"], "the unit was cut, and the row says so"
    assert row["unit_ids"] == ["p-1"] and end > start + 5


def test_a_fragment_id_is_a_partial_unit_too():
    units = corpus(words(4))

    @chunker(key="t-frag", kind="t_frag", label="Frag")
    def frag(us, **options):
        yield Chunk(text=us[1].text, unit_ids=["p-1#f2"])

    row = run(frag.chunk_method, units).rows[0]
    assert row["unit_ids"] == ["p-1#f2"], "the fragment id is kept as written"
    assert row["split_strategies"] == ["partial"]
    assert row["section_paths"] == [["A"]], "and it still resolves to its unit"


def test_a_span_without_the_offsets_capability_is_refused():
    @chunker(key="t-nospan", kind="t_nospan", label="No span")
    def nospan(us, **options):
        yield Chunk(text=us[0].text, span=(0, 4))

    with pytest.raises(ContractError, match="must declare Capability.OFFSETS"):
        run(nospan.chunk_method, corpus(words(3)))


# ------------------------------------------------------------- capabilities

def test_an_undeclared_capability_puts_no_field_on_the_row():
    @chunker(key="t-pages", kind="t_pages", label="Pages only",
             capabilities=[Capability.PAGES])
    def pages_only(us, **options):
        yield Chunk(text=us[1].text, unit_ids=[us[1].unit_id])

    row = run(pages_only.chunk_method, corpus(words(3), pages=(6,))).rows[0]
    assert set(row) == set(contract.CORE_FIELDS) | {"pages"}
    assert row["pages"] == [6]


def test_scores_ride_along_when_the_method_declares_them():
    @chunker(key="t-score", kind="t_score", label="Scored",
             capabilities=[Capability.SEMANTIC_SCORES])
    def scored(us, **options):
        yield Chunk(text=us[1].text, unit_ids=[us[1].unit_id], scores={"cohesion": 0.5})

    row = run(scored.chunk_method, corpus(words(3))).rows[0]
    assert row["scores"] == {"cohesion": 0.5}


def test_custom_fields_survive_when_the_method_declares_them():
    """A method-specific field is an extension, not a leak: the row still
    says what it is, because the method declared that it carries extras."""

    @chunker(key="t-custom", kind="t_custom", label="Custom",
             capabilities=[Capability.PAGES, Capability.CUSTOM_METADATA])
    def custom(us, **options):
        yield Chunk(
            text=us[1].text,
            unit_ids=[us[1].unit_id],
            extra={"table_view": {"rows": 3}, "confidence": 0.9},
        )

    row = run(custom.chunk_method, corpus(words(3))).rows[0]
    assert row["table_view"] == {"rows": 3} and row["confidence"] == 0.9
    assert set(row) == set(contract.CORE_FIELDS) | {"pages", "table_view", "confidence"}


def test_a_field_given_without_its_capability_fails_at_the_boundary():
    """Each of these is the same mistake: producing a field the method says it
    does not produce. Each names the capability that would allow it."""
    cases = {
        "Capability.PAGES": Chunk(text="x", unit_ids=["p-1"], pages=[1]),
        "Capability.HEADINGS": Chunk(text="x", unit_ids=["p-1"], heading="H"),
        "Capability.HIERARCHY": Chunk(text="x", unit_ids=["p-1"], section_paths=[["A"]]),
        "Capability.PROVENANCE": Chunk(text="x", unit_ids=["p-1"], split_strategies=["whole"]),
        "Capability.SEMANTIC_SCORES": Chunk(text="x", unit_ids=["p-1"], scores={"a": 1}),
        "Capability.CUSTOM_METADATA": Chunk(text="x", unit_ids=["p-1"], extra={"mine": 1}),
    }
    for wanted, chunk in cases.items():
        @chunker(key="t-bare", kind="t_bare", label="Bare", capabilities=[])
        def bare(us, _chunk=chunk, **options):
            yield _chunk

        with pytest.raises(ContractError, match=wanted.replace(".", r"\.")):
            run(bare.chunk_method, corpus(words(3)))


def test_a_custom_field_may_not_shadow_a_contract_field():
    @chunker(key="t-shadow", kind="t_shadow", label="Shadow",
             capabilities=[Capability.CUSTOM_METADATA])
    def shadow(us, **options):
        yield Chunk(text=us[1].text, unit_ids=[us[1].unit_id], extra={"unit_ids": ["nope"]})

    with pytest.raises(ContractError, match="would overwrite contract fields"):
        run(shadow.chunk_method, corpus(words(3)))


def test_a_derived_field_may_not_be_supplied_by_hand():
    with pytest.raises(ContractError, match="which the framework derives"):
        Chunk.of({"text": "x", "unit_ids": ["p-1"], "chunk_id": "mine"})


def test_the_capability_vocabulary_is_closed():
    with pytest.raises(ValueError, match="unknown chunker capability 'telemetry'"):
        methods.ChunkMethod(key="x", kind="x", label="X", summary="",
                            partition=lambda *a, **k: None, capabilities=["telemetry"])


# ------------------------------------------------- failures at the boundary

@pytest.mark.parametrize(
    "chunk, message",
    [
        (Chunk(text="", unit_ids=["p-1"]), "needs text"),
        (Chunk(text="x"), "give exactly one provenance"),
        (Chunk(text="x", unit_ids=["p-1"], span=(0, 3)), "give exactly one provenance"),
        (Chunk(text="x", unit_ids=["ghost"]), "not in the canonical corpus"),
    ],
)
def test_a_chunk_that_cannot_be_placed_fails_where_it_was_made(chunk, message):
    """Naming the method and the chunk -- not a KeyError three consumers later."""

    @chunker(key="t-bad", kind="t_bad", label="Bad")
    def bad(us, _chunk=chunk, **options):
        yield _chunk

    with pytest.raises(ContractError, match=message) as failure:
        run(bad.chunk_method, corpus(words(3)))
    assert "'t-bad' chunk 1" in str(failure.value)


def test_a_row_that_does_not_match_the_declaration_fails_too():
    """The check runs for rows a method built itself, not only derived ones --
    which is what holds the frozen engines to their declarations."""
    method = methods.get("structure-only")

    with pytest.raises(ContractError, match=r"missing \['token_count'\]"):
        contract.validate_rows(
            [{"chunk_id": "c1", "text": "t", "unit_ids": [], "pages": [], "heading": None,
              "section_paths": [], "split_strategies": []}],
            method=method,
        )
    with pytest.raises(ContractError, match=r"carries \['mine'\]"):
        contract.validate_rows(
            [{"chunk_id": "c1", "text": "t", "unit_ids": [], "token_count": 1, "pages": [],
              "heading": None, "section_paths": [], "split_strategies": [], "mine": 1}],
            method=method,
        )
    row = {"chunk_id": "c1", "text": "t", "unit_ids": [], "token_count": 1, "pages": [],
           "heading": None, "section_paths": [], "split_strategies": []}
    with pytest.raises(ContractError, match="is used twice"):
        contract.validate_rows([row, dict(row)], method=method)
    with pytest.raises(ContractError, match="unit_ids must be a list of strings"):
        contract.validate_rows([{**row, "unit_ids": [1]}], method=method)


def test_a_partition_that_returns_nonsense_says_so():
    @chunker(key="t-junk", kind="t_junk", label="Junk")
    def junk(us, **options):
        return 17

    with pytest.raises(ContractError, match="a partition returns Chunk objects"):
        run(junk.chunk_method, corpus(words(3)))


# --------------------------------------- what the shipped methods still are

@pytest.mark.parametrize("key", ["markdown", "structure-only", "hybrid"])
def test_a_shipped_method_declares_what_its_rows_actually_carry(key):
    """The declaration and the engine agree, over real output.

    This is the check the eight-key docstring used to stand in for. The
    engines are untouched frozen benchmark code; what changed is that their
    shape is now written down and verified rather than implied.
    """
    from conftest import StaticBoundaryEmbedder

    bodies = [words(60, f"s{i}") for i in range(4)]
    units = corpus(*bodies, pages=(1, 2, 3, 4))
    embedder = StaticBoundaryEmbedder(
        dict(zip(bodies, [[1.0, 0.0], [0.0, 1.0], [0.0, 1.0], [0.0, 1.0]]))
    )
    result = methods.partition(key, units, counter=COUNTER, budget=BUDGET,
                               boundary_embedder=embedder)
    method = methods.get(key)
    allowed = contract.fields_of(method)

    assert result.rows, key
    for row in result.rows:
        assert set(row) <= allowed, f"{key} produced fields it does not declare"
        assert set(contract.CORE_FIELDS) <= set(row)
    assert set(result.rows[0]) == allowed, f"{key} produced exactly what it declares"


def test_a_minimal_methods_rows_are_read_by_every_consumer():
    """The other half of "optional": a chunker that declares nothing extra is
    not a broken chunker anywhere.

    The consumers below all read the optional fields -- pages, heading,
    section paths -- and each is handed rows that have none of them. None may
    fail, because a field a method never claimed to produce is a field a
    consumer has to do without.
    """
    units = corpus(words(5, "a"), words(5, "b"))
    rows = run(minimal.chunk_method, units).rows
    assert all(set(row) == set(contract.CORE_FIELDS) for row in rows)

    located = chunk_mapping.map_chunks(units, rows)
    assert located.health["chunks"] == len(rows)

    measured = chunk_quality.measure(units, rows, located, counter=COUNTER)
    assert measured["chunk_count"] == len(rows)

    assert chunk_relations.derive_continuations(rows, kind="t_minimal") == []
    assert chunk_quality.schema_health(rows)
    assert chunk_quality.qa_view(rows)
