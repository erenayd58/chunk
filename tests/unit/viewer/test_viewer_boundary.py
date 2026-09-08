"""The Viewer boundary in this repository: one reader, one page, no artifacts.

    amsc.chunking.registry          which methods exist, what each one is
        |
    amsc.viewer.corpus    the reader: artifact trees -> one payload shape
        |                 (also what chat_rag's packager calls)
        +-- amsc.viewer.build   this repository's own page over its frozen
                                benchmark corpus, read from disk

There was a third: ``amsc.viewer.server``, an HTTP server on ``:8765`` that
served that page and relayed the RAG console's ``/api/demo/*`` routes for a
live document. The Viewer is a screen of the console now, over ``/api/v1``, and
Step 13 removed the relay and the server. What is left here builds a page, and
nothing in either repository starts a second process.

These tests pin the parts of that a refactor can quietly undo: that the reader
is genuinely shared rather than copied, that the page builder is the only
thing that knows about a template, that the build needs nothing but tracked
source, and that no generated Viewer output is in version control.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from amsc.viewer import corpus as viewer_corpus
from amsc.viewer import build as viewer_v3

REPO = Path(__file__).resolve().parents[3]

#: Everything a Viewer build writes. None of it belongs in the repository.
GENERATED = ("index.html", "catalog.json")


def _payload(html_text: str) -> dict:
    match = re.search(
        r'<script id="viewer-data" type="application/json">(.*?)</script>', html_text, re.S
    )
    assert match, "the page must embed its data in the viewer-data script tag"
    return json.loads(match.group(1).replace(r"<\/", "</"))


# ------------------------------------------------------------ one reader


def test_the_page_calls_the_shared_reader_rather_than_a_copy():
    assert viewer_v3.load_corpus is viewer_corpus.load_corpus
    assert viewer_v3.catalog is viewer_corpus.catalog


def test_the_reader_renders_no_page():
    """The reader is a data layer: it must not know about a template."""
    source = (REPO / "src" / "amsc" / "viewer" / "corpus.py").read_text(encoding="utf-8")
    assert "TEMPLATE" not in source
    assert "viewer_v3_template" not in source
    assert not hasattr(viewer_corpus, "build_viewer")


def test_the_reader_states_no_method_name_of_its_own():
    """Method identity is the registry's. A second table here is how the
    Viewer and the console came to call one method two different things."""
    from amsc.chunking import registry as methods

    assert viewer_corpus.ARM_LABELS is methods.LABELS
    assert viewer_corpus.ARM_KINDS is methods.KINDS
    assert tuple(viewer_corpus.PRODUCT_ARM_ORDER) == tuple(methods.ORDER)


def test_the_catalog_names_the_build_that_wrote_it(tmp_path):
    from _viewer_fixtures import make_tree

    tree = make_tree(tmp_path)
    viewer_v3.build_viewer({"doc": tree}, tmp_path / "v3" / "index.html", root=tmp_path)

    index = json.loads((tmp_path / "v3" / "catalog.json").read_text(encoding="utf-8"))
    assert index["generator"] == "amsc.viewer.build"
    assert "doc" in index["documents"]


# -------------------------------------------------- the product build


def test_the_product_shell_builds_from_tracked_source_alone(tmp_path):
    """The build a fresh clone makes: no trees, no artifacts, no corpus.

    This is what ``start-demo.ps1`` runs when the page is missing, and it is
    the only build a clean checkout can make -- the frozen research trees are
    git-ignored output that is not in version control.
    """
    output = tmp_path / "viewer-v3" / "index.html"
    result = subprocess.run(
        [sys.executable, "-m", "amsc.viewer.build", "--output", str(output)],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )

    assert json.loads(result.stdout)["embedded_documents"] == 0
    data = _payload(output.read_text(encoding="utf-8"))
    assert data["docOrder"] == [] and data["docs"] == {}
    # A shell with no corpus still carries everything the page needs to
    # describe a live document the console will hand it.
    assert data["methodOrder"] and data["methodLabels"] and data["methodMeta"]
    assert (output.parent / "catalog.json").is_file()


def test_the_shell_build_is_byte_identical_when_repeated(tmp_path):
    """The reproducibility gate builds it twice; so does this."""
    first, second = tmp_path / "a" / "index.html", tmp_path / "b" / "index.html"
    viewer_v3.build_viewer({}, first, root=tmp_path)
    viewer_v3.build_viewer({}, second, root=tmp_path)
    assert first.read_bytes() == second.read_bytes()


# -------------------------------------------------- nothing generated is tracked


def _versioned() -> list[str]:
    """Every path a clone would get: tracked, plus untracked-and-not-ignored.

    Not just ``git ls-files``: a generated page that has been added to the
    working tree but not committed yet is exactly the mistake this guards
    against, and it is invisible to the tracked list.
    """
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO, capture_output=True, text=True,
    )
    if result.returncode != 0:  # pragma: no cover - not a checkout
        pytest.skip("not a git checkout")
    return result.stdout.splitlines()


def test_no_generated_viewer_output_is_in_version_control():
    """A fresh clone must not inherit somebody's build.

    A committed ``index.html`` is a 12 MB file that goes stale the moment the
    template changes and that nobody notices is stale, because the page still
    opens.
    """
    tracked = _versioned()
    assert not [p for p in tracked if p.startswith("artifacts/")], "artifacts/ is build output"
    offenders = [p for p in tracked if Path(p).name in GENERATED]
    assert offenders == [], f"generated Viewer output is tracked: {offenders}"


def test_the_viewer_sources_that_are_tracked_are_the_ones_a_build_needs():
    """The inputs of the product build, named, so a move is noticed."""
    tracked = set(_versioned())
    for required in ("src/amsc/viewer/corpus.py", "src/amsc/viewer/build.py",
                     "src/amsc/viewer/template.py",
                     "src/amsc/chunking/registry.py", "src/amsc/chunking/method.py"):
        assert required in tracked, required
    assert "src/amsc/viewer/server.py" not in tracked, (
        "the Viewer's own server is gone; the Viewer is a screen of the console"
    )
