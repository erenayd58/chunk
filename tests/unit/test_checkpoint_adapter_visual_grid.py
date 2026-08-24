"""Adapter-level wiring of the KPI card-grid reconstruction.

The reconstruction itself is covered by ``test_visual_grid``; what matters here
is that the picture block uses it only when geometry was captured and that it
falls back to the extractor's own text otherwise.
"""

from __future__ import annotations

from amsc.checkpoint_adapter import (
    ExtractedPage,
    LayoutBox,
    MarkdownAtomicUnitParser,
    PyMuPDF4LLMExtractor,
)
from amsc.visual_grid import PictureGeometry, VisualTextLine

PICTURE_MARKDOWN = (
    "**==> picture [400 x 200] intentionally omitted <==**\n\n"
    "**----- Start of picture text -----**<br>\n"
    "RISK RAPORU CEK RAPORU<br>1.214.733<br>11.000.144<br>\n"
    "**----- End of picture text -----**<br>\n"
)

REGION = (0.0, 0.0, 400.0, 200.0)
CONTAINERS = ((5.0, 10.0, 185.0, 100.0), (205.0, 10.0, 385.0, 100.0))


def kpi_lines() -> tuple[VisualTextLine, ...]:
    """Two cards whose values swap under a vertical flatten.

    The right card's value is set larger, so its glyph box centre (60.5) sits
    above the left card's (70.0) even though it is drawn lower on the card.
    """
    return (
        VisualTextLine("RISK RAPORU", (10.0, 15.0, 130.0, 26.0), 9.0),
        VisualTextLine("11.000.144", (10.0, 50.0, 160.0, 90.0), 40.0),
        VisualTextLine("CEK RAPORU", (210.0, 15.0, 330.0, 26.0), 9.0),
        VisualTextLine("1.214.733", (210.0, 36.0, 360.0, 85.0), 49.0),
    )


def picture_page(geometry: PictureGeometry | None) -> ExtractedPage:
    return ExtractedPage(
        page=36,
        markdown=PICTURE_MARKDOWN,
        logical_page_side="right",
        physical_page_width=1200,
        physical_page_height=842,
        layout_boxes=(
            LayoutBox(
                0,
                "picture",
                (0, 0, 400, 200),
                0,
                len(PICTURE_MARKDOWN),
                picture_geometry=geometry,
            ),
        ),
    )


def test_a_confident_card_grid_replaces_the_flattened_picture_text() -> None:
    geometry = PictureGeometry(
        region=REGION, lines=kpi_lines(), containers=CONTAINERS
    )

    blocks = MarkdownAtomicUnitParser().parse_page(picture_page(geometry))

    assert len(blocks) == 1
    visual = blocks[0]
    assert visual.text == "RISK RAPORU | 11.000.144\nCEK RAPORU | 1.214.733"
    assert visual.extraction_method == "layout_text_card_grid"
    assert visual.content_origin == "visual"
    assert visual.has_extracted_picture_text is True
    # Provenance keeps the extractor's own serialization, wrong pairing and all.
    assert visual.raw_extracted_picture_text == (
        "RISK RAPORU CEK RAPORU<br>1.214.733<br>11.000.144<br>"
    )


def test_geometry_without_containers_keeps_the_flattened_text() -> None:
    geometry = PictureGeometry(region=REGION, lines=kpi_lines(), containers=())

    blocks = MarkdownAtomicUnitParser().parse_page(picture_page(geometry))

    assert blocks[0].extraction_method == "layout_text"
    assert blocks[0].text == "RISK RAPORU CEK RAPORU\n1.214.733\n11.000.144"


def test_a_picture_without_geometry_is_unchanged() -> None:
    blocks = MarkdownAtomicUnitParser().parse_page(picture_page(None))

    assert blocks[0].extraction_method == "layout_text"
    assert blocks[0].text == "RISK RAPORU CEK RAPORU\n1.214.733\n11.000.144"


def test_the_extractor_captures_no_picture_geometry_by_default() -> None:
    assert PyMuPDF4LLMExtractor().capture_picture_geometry is False
    assert (
        PyMuPDF4LLMExtractor(capture_picture_geometry=True).capture_picture_geometry
        is True
    )
