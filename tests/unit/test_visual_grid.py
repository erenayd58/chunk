from __future__ import annotations

from amsc.visual_grid import (
    PictureGeometry,
    VisualTextLine,
    deduplicate_lines,
    reconstruct_card_grid,
)

REGION = (0.0, 0.0, 400.0, 400.0)


def line(text, x0, y0, x1, y1, size):
    return VisualTextLine(text=text, bbox=(x0, y0, x1, y1), font_size=size)


def card(column, row, width=180.0, height=90.0):
    x0 = 10.0 + column * 200.0
    y0 = 10.0 + row * 100.0
    return (x0, y0, x0 + width, y0 + height)


def kpi(label, value, column, row, label_size=9.0, value_size=40.0,
        value_top=None):
    """One card: a small label near the top, a large value below it."""
    x0 = 10.0 + column * 200.0
    y0 = 10.0 + row * 100.0
    top = y0 + 30.0 if value_top is None else value_top
    return [
        line(label, x0 + 5.0, y0 + 5.0, x0 + 120.0, y0 + 16.0, label_size),
        line(value, x0 + 5.0, top, x0 + 150.0, top + value_size, value_size),
    ]


def test_two_column_grid_pairs_label_with_its_own_value():
    lines = (
        kpi("BIREYSEL UYE", "7.566.660", 0, 0)
        + kpi("TICARI UYE", "578.278", 1, 0)
        + kpi("TOPLAM UYE", "8.144.938", 0, 1)
        + kpi("KREDI NOTU", "486.769", 1, 1)
    )
    containers = (card(0, 0), card(1, 0), card(0, 1), card(1, 1))
    text = reconstruct_card_grid(
        PictureGeometry(region=REGION, lines=tuple(lines), containers=containers)
    )
    assert text == (
        "BIREYSEL UYE | 7.566.660\n"
        "TICARI UYE | 578.278\n"
        "TOPLAM UYE | 8.144.938\n"
        "KREDI NOTU | 486.769"
    )


def test_font_size_difference_inverting_the_vertical_centre_still_pairs():
    """The exact failure this module exists for.

    Two cards of one row carry values of different point size, so the right
    card's glyph box has the higher centre and a vertical flatten emits it
    first. The container assignment is unaffected.
    """
    left = kpi("RISK RAPORU", "11.000.144", 0, 0, value_size=40.0, value_top=50.0)
    right = kpi("CEK RAPORU", "1.214.733", 1, 0, value_size=49.0, value_top=36.0)

    left_value = left[1]
    right_value = right[1]
    left_centre = (left_value.bbox[1] + left_value.bbox[3]) / 2.0
    right_centre = (right_value.bbox[1] + right_value.bbox[3]) / 2.0
    assert right_centre < left_centre, "the inversion must actually be present"

    text = reconstruct_card_grid(
        PictureGeometry(
            region=REGION,
            lines=tuple(left + right),
            containers=(card(0, 0), card(1, 0)),
        )
    )
    assert text == "RISK RAPORU | 11.000.144\nCEK RAPORU | 1.214.733"


def test_overprint_copies_are_dropped():
    lines = kpi("BIREYSEL UYE", "7.566.660", 0, 0) + kpi("TICARI UYE", "578.278", 1, 0)
    shadow = line(
        "7.566.660",
        lines[1].bbox[0] + 2.8,
        lines[1].bbox[1],
        lines[1].bbox[2] + 2.8,
        lines[1].bbox[3],
        lines[1].font_size,
    )
    geometry = PictureGeometry(
        region=REGION,
        lines=tuple([*lines, shadow]),
        containers=(card(0, 0), card(1, 0)),
    )
    assert len(deduplicate_lines(geometry.lines)) == 4
    assert reconstruct_card_grid(geometry) == (
        "BIREYSEL UYE | 7.566.660\nTICARI UYE | 578.278"
    )


def test_the_same_label_on_two_distant_cards_is_not_a_duplicate():
    lines = kpi("TOPLAM", "111", 0, 0) + kpi("TOPLAM", "222", 1, 0)
    assert len(deduplicate_lines(tuple(lines))) == 4
    assert reconstruct_card_grid(
        PictureGeometry(
            region=REGION, lines=tuple(lines), containers=(card(0, 0), card(1, 0))
        )
    ) == "TOPLAM | 111\nTOPLAM | 222"


def test_a_picture_without_containers_falls_back():
    """A bar chart: text but no card rectangles."""
    lines = tuple(
        line(text, 10.0 + index * 40.0, 300.0, 40.0 + index * 40.0, 312.0, 8.0)
        for index, text in enumerate(["2020", "2021", "2022", "73", "89", "136"])
    )
    assert reconstruct_card_grid(
        PictureGeometry(region=REGION, lines=lines, containers=())
    ) is None


def test_uncovered_text_falls_back():
    """A donut chart: some cards, but a legend outside all of them."""
    lines = (
        kpi("KADIN", "270", 0, 0)
        + kpi("ERKEK", "439", 1, 0)
        + [line("Egitim Dagilimi", 10.0, 380.0, 200.0, 392.0, 8.0)]
    )
    assert reconstruct_card_grid(
        PictureGeometry(
            region=REGION,
            lines=tuple(lines),
            containers=(card(0, 0), card(1, 0)),
        )
    ) is None


def test_uniform_font_size_falls_back():
    """An organisation chart: two lines per box, one point size."""
    lines = (
        kpi("Ad Soyad", "Genel Mudur", 0, 0, label_size=8.0, value_size=8.0)
        + kpi("Ad Soyad", "Genel Mudur Yrd", 1, 0, label_size=8.0, value_size=8.0)
    )
    assert reconstruct_card_grid(
        PictureGeometry(
            region=REGION,
            lines=tuple(lines),
            containers=(card(0, 0), card(1, 0)),
        )
    ) is None


def test_a_container_holding_three_lines_falls_back():
    lines = kpi("A", "111", 0, 0) + kpi("B", "222", 1, 0)
    extra = line("dipnot", 15.0, 90.0, 100.0, 98.0, 7.0)
    assert reconstruct_card_grid(
        PictureGeometry(
            region=REGION,
            lines=tuple([*lines, extra]),
            containers=(card(0, 0), card(1, 0)),
        )
    ) is None


def test_a_single_card_is_not_a_grid():
    assert reconstruct_card_grid(
        PictureGeometry(
            region=REGION,
            lines=tuple(kpi("A", "111", 0, 0)),
            containers=(card(0, 0),),
        )
    ) is None


def test_the_picture_frame_is_not_a_card():
    """A rectangle covering the whole region is the frame, not a container."""
    lines = kpi("A", "111", 0, 0) + kpi("B", "222", 1, 0)
    assert reconstruct_card_grid(
        PictureGeometry(
            region=REGION,
            lines=tuple(lines),
            containers=(REGION, card(0, 0), card(1, 0)),
        )
    ) == "A | 111\nB | 222"


def test_label_badges_are_too_small_to_be_containers():
    lines = kpi("A", "111", 0, 0) + kpi("B", "222", 1, 0)
    badge = (10.0, 10.0, 130.0, 30.0)  # 20pt tall
    assert reconstruct_card_grid(
        PictureGeometry(
            region=REGION,
            lines=tuple(lines),
            containers=(badge, card(0, 0), card(1, 0)),
        )
    ) == "A | 111\nB | 222"


def test_nested_decoration_holding_one_line_is_ignored():
    lines = kpi("A", "111", 0, 0) + kpi("B", "222", 1, 0)
    inner = (12.0, 35.0, 170.0, 95.0)  # wraps only the value of the first card
    assert reconstruct_card_grid(
        PictureGeometry(
            region=REGION,
            lines=tuple(lines),
            containers=(inner, card(0, 0), card(1, 0)),
        )
    ) == "A | 111\nB | 222"


def test_rows_are_ordered_top_to_bottom_and_left_to_right():
    """Cards of one row need not share a top edge to the point."""
    lines = (
        kpi("A", "1", 0, 0)
        + kpi("B", "2", 1, 0)
        + kpi("C", "3", 0, 1)
        + kpi("D", "4", 1, 1)
    )
    containers = (
        card(1, 1),
        (10.0, 8.0, 190.0, 98.0),   # row 0 left, two points higher
        card(1, 0),
        card(0, 1),
    )
    assert reconstruct_card_grid(
        PictureGeometry(region=REGION, lines=tuple(lines), containers=containers)
    ) == "A | 1\nB | 2\nC | 3\nD | 4"


def test_no_geometry_means_no_reconstruction():
    assert reconstruct_card_grid(None) is None
    assert reconstruct_card_grid(PictureGeometry(region=REGION)) is None
