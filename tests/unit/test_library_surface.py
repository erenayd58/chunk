"""The declared library surface, checked against the real import graph.

:mod:`amsc.surface` says which modules are product, which are research, which
are legacy and which are unused. These tests make that declaration true rather
than aspirational, and they do it from the imports themselves -- the point is
that nobody has to keep a list of product modules up to date.

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
MODULES = frozenset(p.stem for p in SRC.glob("*.py") if p.stem != "__init__")


# ------------------------------------------------------------------ the graph


def _targets(node: ast.AST) -> set[str]:
    """The ``amsc`` submodules one import statement names."""
    out: set[str] = set()
    if isinstance(node, ast.ImportFrom):
        if node.level and node.module:              # from .pkg import x
            out.add(node.module.split(".")[0])
        elif node.level and not node.module:        # from . import a, b
            out |= {alias.name for alias in node.names}
        elif node.module and node.module.startswith("amsc."):
            out.add(node.module.split(".", 1)[1].split(".")[0])
    elif isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.startswith("amsc."):
                out.add(alias.name.split(".", 1)[1].split(".")[0])
    return out


def _graphs() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    eager: dict[str, set[str]] = defaultdict(set)
    full: dict[str, set[str]] = defaultdict(set)
    for name in sorted(MODULES | {"__init__"}):
        tree = ast.parse((SRC / f"{name}.py").read_text(encoding="utf-8"))
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
            for target in _targets(node):
                if target in MODULES and target != name:
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


def test_the_product_path_reaches_no_research_or_legacy_module():
    """The one rule. Every failure names the import chain that broke it."""
    forbidden = sorted(PRODUCT & (surface.RESEARCH | surface.LEGACY | surface.UNUSED))
    assert forbidden == [], "\n".join(
        ["product code reached modules it must not:"]
        + [f"  {_why(name, surface.ENTRY_POINTS, EAGER)}" for name in forbidden]
    )


def test_the_product_path_reaches_no_viewer_service_module():
    """The console runs beside the Viewer's server, never inside it.

    Reaching ``rag_index`` from the console would drag the frozen benchmark's
    BM25 fold table -- and with it ``chunk_benchmark`` -- onto the ingest path.
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
    assert surface.classify("amsc.deep_arm") == "product"
    assert surface.classify("chunk_benchmark") == "research"
    assert surface.classify("viewer_v2") == "legacy"
    assert surface.classify("viewer_server") == "service"
    assert surface.console_may_import("amsc.viewer_corpus")
    assert not surface.console_may_import("amsc.chunk_benchmark")


def test_the_mixed_modules_are_on_the_product_path_and_named():
    """``MIXED`` documents the traps; it must describe real ones."""
    for name in surface.MIXED:
        assert name in PRODUCT, f"{name} is documented as mixed but is not product"
        assert surface.MIXED[name].strip(), name


# ------------------------------------------------- what the declaration claims


def test_the_unused_module_really_has_no_caller():
    """``UNUSED`` is evidence, not opinion -- checked against both repos."""
    for name in surface.UNUSED:
        callers = sorted(module for module, deps in FULL.items() if name in deps)
        assert callers == [], f"{name} is declared unused but {callers} import it"

        hits = subprocess.run(
            ["git", "grep", "-l", "-e", name, "--", ":!src/amsc/" + name + ".py",
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

    for module in sorted(MODULES | {"__init__"}):
        if colour[module] == 0:
            walk(module, [module])
    assert cycles == [], "module-level import cycles: " + "; ".join(sorted(set(cycles)))


# ------------------------------------------------------- the surface in fact


def test_importing_the_console_surface_loads_no_research_module():
    """The graph says so; this proves it by actually importing, in a clean
    interpreter, which is the only check a lazy import cannot fool."""
    forbidden = sorted(surface.RESEARCH | surface.LEGACY | surface.UNUSED | surface.SERVICE)
    probe = (
        "import importlib, sys, json\n"
        f"for name in {sorted(surface.CONSOLE_API)!r}:\n"
        "    importlib.import_module('amsc.' + name)\n"
        "loaded = {m.split('.')[1] for m in sys.modules if m.startswith('amsc.') and '.' in m}\n"
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
