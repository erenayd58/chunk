from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from amsc.checkpoint_adapter import (
    ExtractedPage,
    MarkdownAtomicUnitParser,
    SectionHierarchyBuilder,
)
from amsc.checkpoint_layout import (
    CheckpointLayoutProfile,
    ExplicitLogicalPageColumnOrderer,
    LayoutBox,
    load_checkpoint_layout_profile,
)
from amsc.checkpoint_qa import build_qa_summary, render_qa_preview
from amsc.models import RawDocumentUnit
from amsc.models import UnitType


def _profile() -> CheckpointLayoutProfile:
    return CheckpointLayoutProfile(
        profile_id="kkb-2024",
        spread_mode="left-right",
        logical_columns=2,
        reading_order="column-major-left-to-right",
    )


def _box(
    index: int,
    bbox: tuple[float, float, float, float],
    start: int = 0,
    end: int = 1,
    layout_class: str = "text",
) -> LayoutBox:
    return LayoutBox(
        index=index,
        layout_class=layout_class,
        bbox=bbox,
        markdown_start=start,
        markdown_end=end,
        logical_bbox=bbox,
    )


def test_checked_in_kkb_profile_is_explicit_and_strict(tmp_path: Path) -> None:
    profile_path = Path(__file__).parents[2] / "configs/checkpoint-kkb-2024.yaml"
    profile = load_checkpoint_layout_profile(profile_path)

    assert profile == _profile()
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text(
        "profile_id: bad\n"
        "spread_mode: left-right\n"
        "logical_columns: auto\n"
        "reading_order: column-major-left-to-right\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_checkpoint_layout_profile(invalid)


def test_page_40_left_regression_orders_columns_by_bbox_not_markdown_pos() -> None:
    # Raw PyMuPDF4LLM order is horizontal stripes: 3,4,5,6,7,8. The KKB
    # checkpoint profile must finish the left column (3,4,7,8) first.
    raw = [
        _box(1, (51, 77, 545, 270)),
        _box(2, (51, 281, 504, 317)),
        _box(3, (51, 371, 286, 435)),
        _box(4, (51, 447, 286, 522)),
        _box(5, (306, 370, 542, 425)),
        _box(6, (306, 436, 542, 522)),
        _box(7, (51, 533, 286, 630)),
        _box(8, (51, 641, 286, 695)),
    ]

    ordered = ExplicitLogicalPageColumnOrderer(_profile()).order(
        raw, logical_page_width=595.275
    )

    assert [box.index for box in ordered] == [1, 2, 3, 4, 7, 8, 5, 6]
    assert [box.logical_column for box in ordered] == [
        "full_width",
        "full_width",
        "left",
        "left",
        "left",
        "left",
        "right",
        "right",
    ]
    assert [box.reading_order_index for box in ordered] == list(range(1, 9))


def test_full_width_boxes_keep_their_vertical_band_position() -> None:
    boxes = [
        _box(5, (310, 100, 540, 160)),
        _box(4, (50, 100, 285, 160)),
        _box(9, (50, 220, 545, 260), layout_class="section-header"),
        _box(7, (50, 300, 285, 360)),
        _box(8, (310, 300, 540, 360)),
        _box(10, (50, 430, 545, 600), layout_class="picture"),
    ]

    ordered = ExplicitLogicalPageColumnOrderer(_profile()).order(
        boxes, logical_page_width=595.0
    )

    assert [box.index for box in ordered] == [4, 5, 9, 7, 8, 10]
    assert [box.layout_band for box in ordered] == [0, 0, 0, 1, 1, 1]
    assert ordered[-1].layout_class == "picture"
    assert ordered[-1].bbox == (50, 430, 545, 600)


def test_parser_preserves_layout_order_and_picture_provenance() -> None:
    segments = [
        "Left top.",
        "Right top.",
        (
            "**----- Start of picture text -----**<br>\n"
            "Planlanan FTE 100<br>Gerçekleşen 96<br>"
            "**----- End of picture text -----**<br>"
        ),
    ]
    markdown = "".join(segments)
    starts = [0, len(segments[0]), len(segments[0]) + len(segments[1])]
    raw = [
        _box(2, (310, 100, 540, 160), starts[1], starts[2]),
        _box(1, (50, 100, 285, 160), starts[0], starts[1]),
        _box(
            3,
            (50, 250, 545, 500),
            starts[2],
            len(markdown),
            layout_class="picture",
        ),
    ]
    ordered = ExplicitLogicalPageColumnOrderer(_profile()).order(
        raw, logical_page_width=595.0
    )
    page = ExtractedPage(
        page=40,
        markdown=markdown,
        logical_page_side="left",
        logical_page_width=595.0,
        layout_boxes=ordered,
    )

    blocks = MarkdownAtomicUnitParser().parse_page(page)
    units = SectionHierarchyBuilder().build(blocks, document_id="kkb-2024")

    assert [unit.text for unit in units] == [
        "Left top.",
        "Right top.",
        "Planlanan FTE 100\nGerçekleşen 96",
    ]
    assert [unit.source.layout_box_index for unit in units] == [1, 2, 3]
    visual = units[-1]
    assert visual.unit_id == "v-00003"
    assert visual.source.content_origin == "visual"
    assert visual.source.picture_bbox == [50.0, 250.0, 545.0, 500.0]
    assert visual.source.layout_bbox_logical == [50.0, 250.0, 545.0, 500.0]
    assert visual.source.logical_column == "full_width"
    assert visual.source.reading_order_policy == "column-major-left-to-right"


def test_table_box_keeps_layout_bbox_and_class_provenance() -> None:
    markdown = "| Metric | Value |\n| --- | --- |\n| FTE | 96 |"
    ordered = ExplicitLogicalPageColumnOrderer(_profile()).order(
        [
            _box(
                12,
                (310, 180, 540, 300),
                0,
                len(markdown),
                layout_class="table",
            )
        ],
        logical_page_width=595.0,
    )
    blocks = MarkdownAtomicUnitParser().parse_page(
        ExtractedPage(
            page=42,
            markdown=markdown,
            logical_page_side="right",
            layout_boxes=ordered,
        )
    )
    units = SectionHierarchyBuilder().build(blocks, document_id="kkb-2024")

    assert units[0].type == UnitType.TABLE
    assert units[0].source.raw_layout_class == "table"
    assert units[0].source.layout_box_index == 12
    assert units[0].source.layout_bbox_logical == [310.0, 180.0, 540.0, 300.0]
    assert units[0].source.logical_column == "right"


def test_qa_separates_canonical_integrity_from_layout_review() -> None:
    units = [
        RawDocumentUnit.model_validate(
            {
                "document_id": "kkb-2024",
                "unit_id": f"p-{order:05d}",
                "order": order,
                "text": text,
                "type": "paragraph",
                "section_path": [],
                "source": {
                    "page": 40,
                    "block": order,
                    "logical_page_side": "left",
                    "layout_box_index": box_index,
                    "layout_reading_order_index": order,
                    "layout_band": 0,
                    "logical_column": column,
                    "layout_bbox_logical": bbox,
                    "reading_order_policy": "column-major-left-to-right",
                },
            }
        )
        for order, (text, box_index, column, bbox) in enumerate(
            [
                ("Bu çözümle,", 3, "left", [50, 100, 285, 150]),
                ("Tamamlanmış sağ kolon cümlesi.", 5, "right", [310, 100, 540, 150]),
            ],
            start=1,
        )
    ]

    summary = build_qa_summary(units)
    preview = render_qa_preview(units)

    assert summary["canonical_order_integrity"] == {"ok": True, "problems": []}
    assert summary["layout_reading_order_review"]["geometry_conformance"][
        "ok"
    ] is True
    assert summary["layout_reading_order_review"]["manual_review_candidates"][
        "paragraphs_ending_with_comma_semicolon_or_incomplete_sentence"
    ][0]["unit_id"] == "p-00001"
    assert "PAGE 40 / LEFT" in preview
    assert "canonical_order_integrity" in preview
    assert "layout_reading_order_review" in preview
