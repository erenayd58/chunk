from __future__ import annotations

import json
import re

from amsc.chunk_mapping import map_chunks
from amsc.chunk_viewer import build_payload, render_html, write_viewer

from _chunk_fixtures import chunk, heading, unit


def corpus():
    units = [
        heading("h-1", "One", 1),
        unit("p-1", "first body", order=2, section=("One",)),
        heading("h-2", "Two", 3),
        unit("p-2", "second body", order=4, section=("Two",)),
    ]
    rows = [
        chunk("c-1", "One\n\nfirst body", ["p-1"], heading="One", token_count=4, pages=[1]),
        chunk("c-2", "Two\n\nsecond body", ["p-2"], heading="Two", token_count=4, pages=[1]),
    ]
    return units, rows, map_chunks(units, rows)


def payload():
    units, rows, mapping = corpus()
    return build_payload(units, {"structure-only": (rows, mapping)}, document_id="doc")


# ------------------------------------------------------------------ payload


def test_units_are_grouped_into_the_pages_they_came_from():
    units = [
        unit("p-1", "one", order=1),
        unit("p-2", "two", order=2),
    ]
    units[0].source.page = 3
    units[1].source.page = 4
    rows = [chunk("c-1", "one\n\ntwo", ["p-1", "p-2"])]

    data = build_payload(
        units, {"a": (rows, map_chunks(units, rows))}, document_id="doc"
    )

    assert [page["page"] for page in data["pages"]] == [3, 4]
    assert [item["id"] for item in data["pages"][0]["units"]] == ["p-1"]


def test_every_segment_is_carried_with_its_chunk_and_its_method():
    data = payload()

    segments = data["segments"]["structure-only"]
    assert segments["p-1"][0]["c"] == "c-1"
    assert segments["h-1"][0]["c"] == "c-1"
    assert {entry["m"] for entries in segments.values() for entry in entries} == {
        "provenance"
    }


def test_chunk_metadata_the_legend_shows_is_present():
    data = payload()

    meta = data["chunks"]["structure-only"]["c-1"]
    assert meta["i"] == 0
    assert meta["tokens"] == 4
    assert meta["heading"] == "One"
    assert meta["pages"] == [1]


def test_an_unmapped_unit_carries_no_segment_at_all():
    units = [unit("p-1", "shown", order=1), unit("p-2", "hidden", order=2)]
    rows = [chunk("c-1", "shown", ["p-1", "p-2"])]

    data = build_payload(
        units, {"a": (rows, map_chunks(units, rows))}, document_id="doc"
    )

    assert "p-2" not in data["segments"]["a"]
    assert any(item["id"] == "p-2" for item in data["pages"][0]["units"])


# --------------------------------------------------------------------- html


def test_the_page_is_self_contained():
    document = render_html(payload())

    assert "<script src=" not in document
    assert "<link" not in document
    assert not re.search(r'(?:src|href)\s*=\s*["\']https?://', document)


def test_the_embedded_payload_parses_and_cannot_close_the_script_element():
    units = [unit("p-1", "before </script> after", order=1)]
    rows = [chunk("c-1", "before </script> after", ["p-1"])]
    document = render_html(
        build_payload(units, {"a": (rows, map_chunks(units, rows))}, document_id="doc")
    )

    body = document.split('<script type="application/json" id="data">')[1].split(
        "</script>"
    )[0]
    assert "</script>" not in body
    assert json.loads(body)["pages"][0]["units"][0]["text"] == "before </script> after"


def test_all_three_arms_become_tabs():
    units, rows, mapping = corpus()
    document = render_html(
        build_payload(
            units,
            {
                "markdown": (rows, mapping),
                "hybrid": (rows, mapping),
                "structure-only": (rows, mapping),
            },
            document_id="doc",
        )
    )

    data = json.loads(
        document.split('<script type="application/json" id="data">')[1].split("</script>")[0]
    )
    assert data["arms"] == ["markdown", "hybrid", "structure-only"]


def test_the_viewer_says_what_it_is_not():
    assert "yerine geçmez" in render_html(payload())


# --------------------------------------------------------------- inspector


def test_every_unit_carries_its_whole_section_path_not_just_the_leaf():
    units = [
        heading("h-1", "Chapter", 1),
        heading("h-2", "Year", 2),
        unit("p-1", "body", order=3, section=("Chapter", "Year")),
    ]
    rows = [chunk("c-1", "Chapter\n\nYear\n\nbody", ["p-1"], heading="Chapter\n\nYear")]

    data = build_payload(units, {"a": (rows, map_chunks(units, rows))}, document_id="doc")

    body = next(item for item in data["pages"][0]["units"] if item["id"] == "p-1")
    assert body["section"] == ["Chapter", "Year"]


def test_the_page_carries_an_inspector_that_renders_the_breadcrumb():
    document = render_html(payload())

    assert 'id="inspector"' in document
    assert "renderInspector" in document
    # The separator the breadcrumb is joined with, so a two-level path reads as
    # "Chapter > Year" rather than the leaf alone.
    assert "›" in document


def test_the_inspector_reports_an_unmapped_unit_as_unmapped():
    assert '"UNMAPPED"' in render_html(payload())


def test_writing_creates_the_file_and_returns_its_path(tmp_path):
    units, rows, mapping = corpus()

    destination = write_viewer(
        tmp_path / "viewer" / "doc.html",
        units,
        {"structure-only": (rows, mapping)},
        document_id="doc",
    )

    assert destination.is_file()
    assert destination.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


# ----------------------------------------------------------- semantic roles


def test_a_heading_carries_the_role_that_decided_its_section_path():
    from amsc.models import SemanticRole

    units = [
        heading("h-1", "Chapter", 1),
        unit("p-1", "body", order=2, section=("Chapter",)),
    ]
    units[0].semantic_role = SemanticRole.ITEM
    units[0].opens_section = False
    rows = [chunk("c-1", "Chapter\n\nbody", ["p-1"], heading="Chapter")]

    data = build_payload(units, {"a": (rows, map_chunks(units, rows))}, document_id="doc")

    entry = data["pages"][0]["units"][0]
    assert entry["role"] == "item"
    assert entry["opens"] is False
    assert entry["level"] == 2


def test_a_canonical_without_roles_carries_no_role_key():
    data = payload()

    for item in data["pages"][0]["units"]:
        assert "role" not in item and "opens" not in item


def test_the_inspector_reports_whether_a_heading_opened_a_section():
    document = render_html(payload())

    assert "opens_section" in document
    assert "semantic_role" in document
