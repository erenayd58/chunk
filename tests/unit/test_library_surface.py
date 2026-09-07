"""The declared library surface, checked against the real import graph.

:mod:`amsc.surface` says which modules are product, which are research, which
are legacy and which are unused. These tests make that declaration true rather
than aspirational, and they do it from the imports themselves -- the point is
that nobody has to keep a list of product modules up to date.

Modules are named by their dotted path below ``amsc`` (``chunking.registry``,
``research.benchmark.chunkers``), which is what makes a *package* an
architectural statement rather than a folder: ``amsc.research`` is off the
product path module by module, and this file is where that is proved.

Two graphs are used, and the difference matters:

* the **eager** graph -- module-level imports only. This is what actually
  loads when the console imports an entry point, so it is what the boundary is
  about. An import written inside a function is a deliberate statement that
  the dependency is for one code path, and the tests treat it that way.
* the **full** graph -- eager plus deferred. Used only for the reachability
  evidence behind ``UNUSED``, where a lazy import still counts as a caller.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path

import pytest

from amsc import surface

SRC = Path(__file__).resolve().parents[2] / "src" / "amsc"


def _dotted(path: Path) -> str:
    return ".".join(path.relative_to(SRC).with_suffix("").parts)


#: Every importable module, by dotted path. Package ``__init__`` files are not
#: modules for this purpose: they hold documentation and nothing else, which
#: ``test_no_package_init_imports_anything`` is what keeps true.
MODULES = frozenset(_dotted(p) for p in SRC.rglob("*.py") if p.name != "__init__.py")
INITS = tuple(sorted(SRC.rglob("__init__.py")))


# ------------------------------------------------------------------ the graph


def _resolve(base: tuple[str, ...], names: list[str]) -> set[str]:
    """``base`` if it is a module, else whichever of ``names`` under it are."""
    dotted = ".".join(base)
    if dotted and dotted in MODULES:
        return {dotted}
    return {c for c in (".".join(base + (name,)) for name in names) if c in MODULES}


def _targets(node: ast.AST, here: tuple[str, ...]) -> set[str]:
    """The ``amsc`` modules one import statement names, as dotted paths.

    ``here`` is the package the importing module lives in, which is what makes
    a relative import resolvable.
    """
    names = [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        if node.level:                                      # from ..pkg import x
            if node.level - 1 > len(here):
                return set()
            base = here[: len(here) - (node.level - 1)]
            if node.module:
                base += tuple(node.module.split("."))
            return _resolve(base, names)
        if node.module and node.module.startswith("amsc."):
            return _resolve(tuple(node.module.split(".")[1:]), names)
    elif isinstance(node, ast.Import):
        return {alias.name[len("amsc."):] for alias in node.names
                if alias.name.startswith("amsc.") and alias.name[len("amsc."):] in MODULES}
    return set()


def _graphs() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    eager: dict[str, set[str]] = defaultdict(set)
    full: dict[str, set[str]] = defaultdict(set)
    for name in sorted(MODULES):
        path = SRC.joinpath(*name.split(".")).with_suffix(".py")
        here = tuple(name.split(".")[:-1])
        tree = ast.parse(path.read_text(encoding="utf-8"))
        at_module_level = set()
        for statement in tree.body:
            if isinstance(statement, (ast.Import, ast.ImportFrom)):
                at_module_level.add(id(statement))
            elif isinstance(statement, ast.If):     # if TYPE_CHECKING: ...
                for inner in ast.walk(statement):
                    if isinstance(inner, (ast.Import, ast.ImportFrom)):
                        at_module_level.add(id(inner))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for target in _targets(node, here):
                if target != name:
                    full[name].add(target)
                    if id(node) in at_module_level:
                        eager[name].add(target)
    return eager, full


EAGER, FULL = _graphs()


def _reach(roots, graph) -> set[str]:
    seen: set[str] = set()
    queue = deque(roots)
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        queue.extend(graph.get(node, ()))
    return seen


def _why(target: str, roots, graph) -> str:
    """A shortest import chain from an entry point to ``target``, for the
    failure message: the point of the test is to say *which edge* broke it."""
    previous = {root: None for root in roots}
    queue = deque(roots)
    while queue:
        node = queue.popleft()
        for child in sorted(graph.get(node, ())):
            if child not in previous:
                previous[child] = node
                queue.append(child)
    if target not in previous:
        return f"{target} (no chain found)"
    chain, node = [], target
    while node is not None:
        chain.append(node)
        node = previous[node]
    return " <- ".join(chain)


PRODUCT = _reach(surface.ENTRY_POINTS, EAGER)


# ------------------------------------------------------------- the invariant


def test_the_graph_was_actually_built():
    """A resolver that resolves nothing would make every test below vacuous."""
    assert len(MODULES) > 70, sorted(MODULES)
    # The registry imports the types leaf and every registered method module,
    # and nothing else -- a fifth method adds a name here, never a package.
    assert "chunking.method" in EAGER["chunking.registry"]
    assert all(name.startswith("chunking.") for name in EAGER["chunking.registry"])
    assert "document.models" in EAGER["document.io"]
    assert "quality.boundaries" in EAGER["deep.pipeline"]
    assert len(PRODUCT) > 30, sorted(PRODUCT)


def test_the_product_path_reaches_no_research_or_legacy_module():
    """The one rule. Every failure names the import chain that broke it."""
    forbidden = sorted(PRODUCT & (surface.RESEARCH | surface.LEGACY | surface.UNUSED))
    assert forbidden == [], "\n".join(
        ["product code reached modules it must not:"]
        + [f"  {_why(name, surface.ENTRY_POINTS, EAGER)}" for name in forbidden]
    )


def test_the_product_path_reaches_no_viewer_service_module():
    """The console runs beside the Viewer's server, never inside it.

    Reaching ``viewer.chat.index`` from the console would drag the frozen
    benchmark's BM25 fold table -- and with it the whole chunk benchmark --
    onto the ingest path.
    """
    leaked = sorted(PRODUCT & surface.SERVICE)
    assert leaked == [], "\n".join(
        ["the console surface reached the Viewer service:"]
        + [f"  {_why(name, surface.ENTRY_POINTS, EAGER)}" for name in leaked]
    )


def test_every_module_off_the_product_path_is_declared():
    """A new module cannot arrive without a status.

    Modules *on* the product path need no declaration -- that is what keeps
    this from being a list to maintain. Everything else must be named in
    ``SERVICE``, ``RESEARCH``, ``LEGACY`` or ``UNUSED``, which is the one
    moment someone is asked to decide what a new module is.
    """
    undeclared = sorted(MODULES - PRODUCT - surface.DECLARED)
    assert undeclared == [], (
        "these modules are on no product path and carry no status; add each to "
        f"SERVICE, RESEARCH, LEGACY or UNUSED in amsc/surface.py: {undeclared}"
    )


def test_everything_under_the_research_package_is_declared_research():
    """The package name is a claim; this is the check behind it.

    A module dropped into ``amsc/research/`` is off the product path because
    ``surface`` says so, not because of where it sits -- and the two must not
    be allowed to disagree in either direction.
    """
    living_there = {name for name in MODULES if name.startswith("research.")}
    declared = surface.RESEARCH | surface.LEGACY
    assert sorted(living_there - declared) == [], "under amsc/research but not declared"
    assert sorted(declared - living_there) == [], "declared research but living elsewhere"


def test_no_module_carries_two_statuses():
    groups = {"SERVICE": surface.SERVICE, "RESEARCH": surface.RESEARCH,
              "LEGACY": surface.LEGACY, "UNUSED": surface.UNUSED}
    for left in groups:
        for right in groups:
            if left < right:
                overlap = sorted(groups[left] & groups[right])
                assert overlap == [], f"{left} and {right} both claim {overlap}"


def test_every_declared_name_is_a_real_module():
    """A rename must not leave a status pointing at nothing."""
    declared = surface.DECLARED | surface.ENTRY_POINTS | frozenset(surface.MIXED)
    missing = sorted(declared - MODULES)
    assert missing == [], f"amsc/surface.py names modules that do not exist: {missing}"


def test_the_console_api_is_a_subset_of_the_product_surface():
    assert surface.CONSOLE_API <= PRODUCT
    assert surface.DISPATCHED <= PRODUCT
    assert surface.classify("amsc.deep.arm") == "product"
    assert surface.classify("research.benchmark.chunkers") == "research"
    assert surface.classify("research.legacy_chat_rag") == "legacy"
    assert surface.classify("viewer.server") == "service"
    assert surface.console_may_import("amsc.viewer.corpus")
    assert not surface.console_may_import("amsc.research.benchmark.chunkers")


def test_the_mixed_modules_are_on_the_product_path_and_named():
    """``MIXED`` documents the traps; it must describe real ones."""
    for name in surface.MIXED:
        assert name in PRODUCT, f"{name} is documented as mixed but is not product"
        assert surface.MIXED[name].strip(), name


# ------------------------------------------------- what the declaration claims


def test_the_unused_module_really_has_no_caller():
    """``UNUSED`` is evidence, not opinion -- checked against both repos.

    Empty since Phase 8 deleted ``parent_expansion``; the check stays because
    it is what makes the status mean something the next time one is declared.
    """
    for name in surface.UNUSED:
        callers = sorted(module for module, deps in FULL.items() if name in deps)
        assert callers == [], f"{name} is declared unused but {callers} import it"

        own = "src/amsc/" + name.replace(".", "/") + ".py"
        hits = subprocess.run(
            ["git", "grep", "-l", "-F", "-e", name, "--", ":!" + own,
             ":!tests/unit/test_library_surface.py", ":!src/amsc/surface.py"],
            cwd=SRC.parents[1], capture_output=True, text=True,
        )
        assert hits.stdout.strip() == "", (
            f"{name} is declared unused but is mentioned in:\n{hits.stdout}"
        )


def test_the_research_modules_are_still_importable():
    """Research stays usable. Off the product path is not the same as broken."""
    for name in sorted(surface.RESEARCH | surface.LEGACY | surface.SERVICE):
        __import__(f"amsc.{name}")


def test_the_package_has_no_import_cycles():
    """A cycle is what makes a boundary impossible to reason about."""
    colour: dict[str, int] = defaultdict(int)          # 0 new, 1 open, 2 done
    cycles: list[str] = []

    def walk(node: str, stack: list[str]) -> None:
        colour[node] = 1
        for child in sorted(EAGER.get(node, ())):
            if colour[child] == 1:
                cycles.append(" -> ".join(stack[stack.index(child):] + [child]))
            elif colour[child] == 0:
                walk(child, stack + [child])
        colour[node] = 2

    for module in sorted(MODULES):
        if colour[module] == 0:
            walk(module, [module])
    assert cycles == [], "module-level import cycles: " + "; ".join(sorted(set(cycles)))


def test_no_package_init_imports_anything():
    """A package ``__init__`` documents the package; it does not load it.

    This is what makes ``import amsc.chunking.method`` cost one leaf module
    rather than a package's worth of engines, and it is why the tree can be
    reorganised without a re-export layer appearing to hold it together.
    """
    importing = []
    for init in INITS:
        tree = ast.parse(init.read_text(encoding="utf-8"))
        if any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree)):
            importing.append(str(init.relative_to(SRC.parents[1])))
    assert importing == [], f"package __init__ files that import: {importing}"


def test_dependencies_point_down_the_layering():
    """The document contract is the bottom of the graph, and stays there.

    Every other package may import :mod:`amsc.document`; it may import none of
    them. The same is true of the two leaves the boundary depends on:
    ``chunking.method`` (so a method module can import it) and ``providers``
    (so the transport belongs to nobody).
    """
    for leaf in ("document.models", "document.io", "document.tokenization",
                 "chunking.method", "providers"):
        outward = sorted(d for d in EAGER.get(leaf, ()) if not d.startswith("document."))
        assert outward == [], f"{leaf} imports upward: {outward}"


# ------------------------------------------------------- the surface in fact


def test_importing_the_console_surface_loads_no_research_module():
    """The graph says so; this proves it by actually importing, in a clean
    interpreter, which is the only check a lazy import cannot fool."""
    forbidden = sorted(surface.RESEARCH | surface.LEGACY | surface.UNUSED | surface.SERVICE)
    probe = (
        "import importlib, sys, json\n"
        f"for name in {sorted(surface.CONSOLE_API)!r}:\n"
        "    importlib.import_module('amsc.' + name)\n"
        "loaded = {m[len('amsc.'):] for m in sys.modules if m.startswith('amsc.')}\n"
        f"print(json.dumps(sorted(loaded & set({forbidden!r}))))\n"
    )
    result = subprocess.run([sys.executable, "-c", probe],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]", (
        f"importing the console surface loaded: {result.stdout.strip()}"
    )


@pytest.mark.parametrize("entry", sorted(surface.ENTRY_POINTS))
def test_every_entry_point_imports(entry):
    """The declared surface is importable -- no stale name, no broken module."""
    __import__(f"amsc.{entry}")


def test_every_research_and_legacy_module_still_has_a_caller():
    """The other half of ``UNUSED``: a declared status is not a hiding place.

    ``research`` and ``legacy`` both mean "off the product path but still
    reached by something". A module that no longer has an importer, an entry
    point or a test is neither -- it is unused, and saying so is the point.
    Deferred imports count, and so does being a documented ``python -m``
    runner, which is why the whole repository is searched rather than only
    the import graph.
    """
    orphans = []
    for name in sorted(surface.RESEARCH | surface.LEGACY | surface.SERVICE):
        if any(name in deps for deps in FULL.values()):
            continue
        own = "src/amsc/" + name.replace(".", "/") + ".py"
        hits = subprocess.run(
            ["git", "grep", "-l", "-F", "-e", name, "--",
             ":!" + own, ":!src/amsc/surface.py",
             ":!tests/unit/test_library_surface.py"],
            cwd=SRC.parents[1], capture_output=True, text=True,
        )
        if not hits.stdout.strip():
            orphans.append(name)
    assert orphans == [], (
        "declared research/legacy/service but nothing reaches them; they are "
        f"unused, not off-path: {orphans}"
    )


def test_the_provider_transport_is_not_a_research_module():
    """Phase 8's boundary move, stated as the invariant it bought.

    Deep Analysis reaches a provider through :mod:`amsc.providers`. If it ever
    reaches one through the v1 Agentic arm again, both research arms come back
    onto the product path with it -- which is the failure this whole file
    exists to name.
    """
    assert "providers" in PRODUCT
    for arm in ("research.agentic.chunker", "research.agentic.judge"):
        assert surface.classify(arm) == "research", arm
        assert arm not in PRODUCT, _why(arm, surface.ENTRY_POINTS, EAGER)
    assert EAGER["providers"] == set(), (
        "providers imports amsc modules: " + str(sorted(EAGER["providers"]))
    )
