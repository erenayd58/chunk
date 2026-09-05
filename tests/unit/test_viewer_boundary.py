"""The Viewer boundary in this repository: one reader, two pages, no artifacts.

After Phase 6 the Viewer is three layers with one direction of dependency:

    amsc.methods          which methods exist, what each one is
        |
    amsc.viewer_corpus    the reader: artifact trees -> one payload shape
        |                 (also what chat_rag's packager calls)
        +-- amsc.viewer_v3   the product page          (built by start-demo)
        +-- amsc.viewer_v2   the research/fallback page
        |
    amsc.viewer_server    the service: serves a page, relays the console

These tests pin the parts of that a refactor can quietly undo: that the pages
do not read each other, that the reader is genuinely shared rather than
copied, that the product build needs nothing but tracked source, and that no
generated Viewer output is in version control.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from amsc import viewer_corpus, viewer_v2, viewer_v3

REPO = Path(__file__).resolve().parents[2]

#: Everything a Viewer build writes. None of it belongs in the repository.
GENERATED = ("index.html", "catalog.json")


def _payload(html_text: str) -> dict:
    match = re.search(
        r'<script id="viewer-data" type="application/json">(.*?)</script>', html_text, re.S
    )
    assert match, "the page must embed its data in the viewer-data script tag"
    return json.loads(match.group(1).replace("<\\/", "</"))


# ------------------------------------------------------------ one reader


def test_the_reader_is_shared_not_copied():
    """Both pages call the same objects, so a change reaches both at once."""
    assert viewer_v2.load_corpus is viewer_corpus.load_corpus
    assert viewer_v3.load_corpus is viewer_corpus.load_corpus
    assert viewer_v2.catalog is viewer_corpus.catalog
    assert viewer_v3.catalog is viewer_corpus.catalog
    # The compatibility re-exports on the v2 module are the reader's own
    # objects too: callers that still import them cannot drift.
    for name in ("ARM_KINDS", "ARM_ORDER", "ARM_LABELS", "display_html", "heading_plain"):
        assert getattr(viewer_v2, name) is getattr(viewer_corpus, name), name


def test_neither_page_reads_the_other():
    """The pages are siblings over the reader, not a chain.

    Viewer v3 importing Viewer v2 is how the 230 KB v2 template ended up being
    loaded by everything that touched a payload, the RAG console included.
    """
    v3_source = (REPO / "src" / "amsc" / "viewer_v3.py").read_text(encoding="utf-8")
    assert "viewer_v2" not in v3_source.replace("Viewer v2", "").replace(
        ":mod:`amsc.viewer_v2`", ""
    ), "viewer_v3 must not import viewer_v2"

    result = subprocess.run(
        [sys.executable, "-c",
         "import amsc.viewer_v3, sys; "
         "print(','.join(sorted(m for m in sys.modules if 'viewer_v2' in m)))"],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == "", (
        f"building Viewer v3 pulled in Viewer v2 modules: {result.stdout.strip()}"
    )


def test_the_reader_renders_no_page():
    """The reader is a data layer: it must not know about a template."""
    source = (REPO / "src" / "amsc" / "viewer_corpus.py").read_text(encoding="utf-8")
    assert "TEMPLATE" not in source
    assert "viewer_v2_template" not in source and "viewer_v3_template" not in source
    assert not hasattr(viewer_corpus, "build_viewer")


def test_the_catalog_names_the_build_that_wrote_it(tmp_path):
    """One catalog writer, two builders -- and the file says which one ran."""
    from test_viewer_v2 import make_tree

    tree = make_tree(tmp_path)
    viewer_v2.build_viewer({"doc": tree}, tmp_path / "v2" / "index.html", root=tmp_path)
    viewer_v3.build_viewer({"doc": tree}, tmp_path / "v3" / "index.html", root=tmp_path)

    v2 = json.loads((tmp_path / "v2" / "catalog.json").read_text(encoding="utf-8"))
    v3 = json.loads((tmp_path / "v3" / "catalog.json").read_text(encoding="utf-8"))
    assert v2["generator"] == "amsc.viewer_v2"
    assert v3["generator"] == "amsc.viewer_v3"
    # Same writer, so the rest is the same document index.
    assert v2["documents"] == v3["documents"]


# -------------------------------------------------- the product build


def test_the_product_shell_builds_from_tracked_source_alone(tmp_path):
    """The build a fresh clone makes: no trees, no artifacts, no corpus.

    This is what ``start-demo.ps1`` runs when the page is missing, and it is
    the only build a clean checkout can make -- the frozen research trees are
    git-ignored output that is not in version control.
    """
    output = tmp_path / "viewer-v3" / "index.html"
    result = subprocess.run(
        [sys.executable, "-m", "amsc.viewer_v3", "--output", str(output)],
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
    for required in ("src/amsc/viewer_corpus.py", "src/amsc/viewer_v3.py",
                     "src/amsc/viewer_v3_template.py", "src/amsc/viewer_server.py",
                     "src/amsc/methods.py"):
        assert required in tracked, required
