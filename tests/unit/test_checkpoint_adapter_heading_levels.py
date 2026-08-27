"""Adapter-level wiring of typographic heading levels.

The level rule itself is covered by ``test_heading_levels``; what matters here
is that the measured type size reaches the block stream, that the pass runs
only when it is asked for, and that it is the last thing to touch the headings.
"""

from __future__ import annotations

from pathlib import Path

from amsc.checkpoint_adapter import (
    ExtractedPage,
    ExtractionResult,
    LayoutBox,
    MarkdownAtomicUnitParser,
)
from amsc.prepare_full_checkpoint import extract_full_canonical_units


def page(*boxes: LayoutBox, markdown: str) -> ExtractedPage:
    return ExtractedPage(
        page=2,
        markdown=markdown,
        logical_page_side="single",
        physical_page_width=595.0,
        physical_page_height=842.0,
        logical_page_width=595.0,
        layout_boxes=boxes,
    )


MARKDOWN = (
    "## 8. KILOMETRE TASLARI\n\n"      # 0 .. 25
    "## 2012\n\n"                       # 25 .. 34
    "Nisan ayinda KRS hayata gecirildi.\n\n"  # 34 .. 70
    "## 9. BASKA BOLUM\n\n"             # 70 .. 90
    "Ikinci bolumun govdesi.\n"         # 90 ..
)


def sized_page() -> ExtractedPage:
    text = MARKDOWN
    chapter = text.index("## 8.")
    year = text.index("## 2012")
    body = text.index("Nisan")
    second = text.index("## 9.")
    tail = text.index("Ikinci")
    return page(
        LayoutBox(0, "section-header", (0, 0, 500, 30), chapter, year, font_size=20.0),
        LayoutBox(1, "section-header", (0, 40, 200, 60), year, body, font_size=9.0),
        LayoutBox(2, "text", (0, 70, 500, 110), body, second, font_size=9.0),
        LayoutBox(3, "section-header", (0, 120, 500, 150), second, tail, font_size=20.0),
        LayoutBox(4, "text", (0, 160, 500, 200), tail, len(text), font_size=9.0),
        markdown=text,
    )


class FakeExtractor:
    def __init__(self, extracted: ExtractedPage) -> None:
        self.extracted = extracted

    def extract(self, input_path, *, pages):  # noqa: ANN001 - test double
        return ExtractionResult(
            pages=(self.extracted,),
            selected_pages=(2,),
            page_count=1,
            pymupdf4llm_version="0.3.4",
        )


def units_for(extracted: ExtractedPage, **flags):
    return extract_full_canonical_units(
        input_path=Path("unused.pdf"),
        document_id="doc",
        extractor=FakeExtractor(extracted),
        **flags,
    ).units


# ------------------------------------------------------------------ wiring


def test_the_measured_type_size_reaches_every_block_of_its_box():
    blocks = MarkdownAtomicUnitParser().parse_page(sized_page())

    assert [block.font_size for block in blocks] == [20.0, 9.0, 9.0, 20.0, 9.0]


def test_a_box_with_no_measured_size_leaves_the_block_size_unset():
    text = "## Baslik\n\nGovde metni.\n"
    blocks = MarkdownAtomicUnitParser().parse_page(
        page(
            LayoutBox(0, "section-header", (0, 0, 500, 30), 0, text.index("Govde")),
            LayoutBox(1, "text", (0, 40, 500, 80), text.index("Govde"), len(text)),
            markdown=text,
        )
    )

    assert [block.font_size for block in blocks] == [None, None]


# ------------------------------------------------------------------- opt-in


def test_levels_are_untouched_unless_the_pass_is_asked_for():
    units = units_for(sized_page())

    assert [u.heading_level for u in units if u.type.value == "heading"] == [2, 2, 2]
    assert [list(u.section_path) for u in units] == [
        ["8. KILOMETRE TASLARI"],
        ["2012"],
        ["2012"],
        ["9. BASKA BOLUM"],
        ["9. BASKA BOLUM"],
    ]


def test_the_year_label_nests_under_its_chapter_once_the_pass_runs():
    units = units_for(sized_page(), assign_typographic_heading_levels=True)

    assert [u.heading_level for u in units if u.type.value == "heading"] == [2, 3, 2]
    assert [list(u.section_path) for u in units] == [
        ["8. KILOMETRE TASLARI"],
        ["8. KILOMETRE TASLARI", "2012"],
        ["8. KILOMETRE TASLARI", "2012"],
        ["9. BASKA BOLUM"],
        ["9. BASKA BOLUM"],
    ]


def test_a_page_set_in_one_size_is_identical_with_and_without_the_pass():
    text = "## Bir\n\nGovde bir.\n\n## Iki\n\nGovde iki.\n"
    flat = page(
        LayoutBox(0, "section-header", (0, 0, 500, 20), 0, text.index("Govde bir"), font_size=9.0),
        LayoutBox(1, "text", (0, 30, 500, 60), text.index("Govde bir"), text.index("## Iki"), font_size=9.0),
        LayoutBox(2, "section-header", (0, 70, 500, 90), text.index("## Iki"), text.index("Govde iki"), font_size=9.0),
        LayoutBox(3, "text", (0, 100, 500, 130), text.index("Govde iki"), len(text), font_size=9.0),
        markdown=text,
    )

    assert units_for(flat) == units_for(flat, assign_typographic_heading_levels=True)


def test_the_pass_runs_after_a_demotion_so_it_never_levels_a_removed_heading():
    """A lead-in demoted to body must not appear in the level stack at all."""
    text = "## 1. BOLUM\n\n## Uygulamayla;\n\n- birinci madde\n"
    lead_in = page(
        LayoutBox(0, "section-header", (0, 0, 500, 30), 0, text.index("## Uygulamayla"), font_size=20.0),
        LayoutBox(1, "section-header", (0, 40, 500, 60), text.index("## Uygulamayla"), text.index("- birinci"), font_size=9.0),
        LayoutBox(2, "text", (0, 70, 500, 100), text.index("- birinci"), len(text), font_size=9.0),
        markdown=text,
    )

    units = units_for(
        lead_in,
        demote_lead_in_headings=True,
        assign_typographic_heading_levels=True,
    )

    assert [(u.type.value, u.heading_level) for u in units] == [
        ("heading", 2),
        ("paragraph", None),
        ("list", None),
    ]
    assert [list(u.section_path) for u in units] == [["1. BOLUM"]] * 3
