"""Viewer v3 -- a separate product page over the same fixture data.

Built from the exact synthetic tree Viewer v2's tests use, and held to the
product contract: its own output, the v2 corpus shape unchanged, no method
list hard-coded into the page, and no effect whatsoever on a v2 build.
"""

from __future__ import annotations

import json
import re

from test_viewer_v2 import make_tree

from amsc import viewer_v2
from amsc.viewer_v3 import METHOD_LABELS, build_viewer


def _build(tmp_path):
    tree = make_tree(tmp_path)
    output = tmp_path / "v3" / "index.html"
    build_viewer({"doc": tree}, output, root=tmp_path)
    return output


def _payload(html_text: str) -> dict:
    match = re.search(
        r'<script id="viewer-data" type="application/json">(.*?)</script>',
        html_text,
        re.S,
    )
    assert match, "the page must embed its data in the viewer-data script tag"
    return json.loads(match.group(1).replace("<\\/", "</"))


def test_the_build_writes_its_own_page_and_catalog(tmp_path):
    output = _build(tmp_path)
    html_text = output.read_text(encoding="utf-8")
    assert "__VIEWER_DATA__" not in html_text
    data = _payload(html_text)
    assert data["generator"] == "amsc.viewer_v3"
    catalog = json.loads((output.parent / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["generator"] == "amsc.viewer_v3"
    assert "doc" in catalog["documents"]


def test_the_payload_is_the_v2_corpus_shape_unchanged(tmp_path):
    data = _payload(_build(tmp_path).read_text(encoding="utf-8"))
    doc = data["docs"]["doc"]
    for key in ("units", "arms", "pages", "meta", "label"):
        assert key in doc
    # The arms are exactly what the tree holds -- nothing invented.
    assert set(doc["arms"]) == {"markdown", "hybrid", "structure-only"}
    for arm in doc["arms"].values():
        assert "chunks" in arm and "seg" in arm and "m" in arm


def test_methods_wear_product_names_not_engine_names(tmp_path):
    html_text = _build(tmp_path).read_text(encoding="utf-8")
    data = _payload(html_text)
    assert data["methodLabels"]["structure-only"] == "Standard"
    assert data["methodLabels"]["agentic"] == "Deep Analysis"
    static = html_text.split('<script id="viewer-data"')[0]
    # The page itself hard-codes no method list; names come from the payload.
    assert "Agentic Chunker" not in static
    assert "Structure-only" not in static
    assert METHOD_LABELS["structure-only"] == "Standard"


def test_the_query_screen_and_console_pill_are_in_the_shell(tmp_path):
    html_text = _build(tmp_path).read_text(encoding="utf-8")
    static = html_text.split('<script id="viewer-data"')[0]
    # The two modes, the console pill and the query affordances ship with the
    # shell; their values (models, counts, questions) come from the payload
    # and the server at runtime, never from the markup.
    assert 'id="tabs"' in static and "Sorgu" in static
    assert 'data-t="home"' in static and "Genel" in static
    assert 'data-t="bench"' in static and "Benchmark" in static
    assert 'data-t="debug"' in static and "Debug" in static
    assert 'id="pill"' in static
    assert "Parametreler" in html_text
    # Methods are picked as toggle chips (one = ask, several = compare those);
    # there is no all-or-nothing compare switch.
    assert "qmchips" in html_text
    assert "Tüm yöntemleri karşılaştır" not in html_text
    assert "qwen" not in html_text.split('<script id="viewer-data"')[0]


def test_the_build_is_deterministic(tmp_path):
    first = _build(tmp_path).read_bytes()
    second_out = tmp_path / "v3b" / "index.html"
    build_viewer({"doc": make_tree(tmp_path / "second")}, second_out, root=tmp_path / "second")
    # Same tree content, byte-identical page apart from nothing at all.
    assert first == (tmp_path / "v3" / "index.html").read_bytes()
    assert second_out.read_bytes() == first


def test_building_v3_leaves_a_v2_build_byte_identical(tmp_path):
    tree = make_tree(tmp_path)
    before = tmp_path / "v2-before.html"
    viewer_v2.build_viewer({"doc": tree}, before, root=tmp_path, write_catalog=False)
    _build(tmp_path)
    after = tmp_path / "v2-after.html"
    viewer_v2.build_viewer({"doc": tree}, after, root=tmp_path, write_catalog=False)
    assert before.read_bytes() == after.read_bytes()


def test_writing_into_evaluation_is_refused(tmp_path):
    tree = make_tree(tmp_path)
    try:
        build_viewer({"doc": tree}, tmp_path / "evaluation" / "x.html", root=tmp_path)
    except ValueError as error:
        assert "evaluation" in str(error)
    else:  # pragma: no cover
        raise AssertionError("expected the evaluation/ guard to refuse")
