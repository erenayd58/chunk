from __future__ import annotations

from amsc.checkpoint_adapter import ExtractedPage, ExtractionResult
from amsc.checkpoint_layout import CheckpointLayoutProfile, LayoutBox
from amsc.prepare_full_checkpoint import apply_profile_to_spread_logical_pages


def test_full_profile_keeps_portrait_single_and_orders_spread_columns() -> None:
    profile = CheckpointLayoutProfile(
        profile_id="kkb-2024",
        spread_mode="left-right",
        logical_columns=2,
        reading_order="column-major-left-to-right",
    )
    portrait = ExtractedPage(
        page=1,
        markdown="Cover",
        logical_page_side="single",
        logical_page_width=595.0,
        layout_boxes=(
            LayoutBox(1, "text", (50, 50, 545, 100), 0, 5),
        ),
    )
    spread = ExtractedPage(
        page=2,
        markdown="abcdefgh",
        logical_page_side="left",
        logical_page_width=595.0,
        layout_boxes=(
            LayoutBox(
                3,
                "text",
                (310, 100, 540, 150),
                2,
                3,
                logical_bbox=(310, 100, 540, 150),
            ),
            LayoutBox(
                2,
                "text",
                (50, 200, 285, 250),
                1,
                2,
                logical_bbox=(50, 200, 285, 250),
            ),
            LayoutBox(
                1,
                "text",
                (50, 100, 285, 150),
                0,
                1,
                logical_bbox=(50, 100, 285, 150),
            ),
        ),
    )
    extraction = ExtractionResult(
        pages=(portrait, spread),
        selected_pages=(1, 2),
        page_count=2,
        pymupdf4llm_version="0.3.4",
    )

    result = apply_profile_to_spread_logical_pages(extraction, profile)

    assert result.pages[0] == portrait
    assert [box.index for box in result.pages[1].layout_boxes] == [1, 2, 3]
    assert result.layout_profile == profile
