from __future__ import annotations

from dataclasses import dataclass

import pytest

from amsc.running_headers import (
    DEFAULT_MIN_PAGES,
    drop_running_headers,
    running_header_texts,
)


@dataclass
class Block:
    page: int
    text: str
    heading_level: int | None = None
    logical_page_side: str = "single"


def banner(page, text="BOLUM BASLIGI", side="single"):
    return Block(page=page, text=text, heading_level=2, logical_page_side=side)


def body(page, text="govde metni", side="single"):
    return Block(page=page, text=text, logical_page_side=side)


def test_heading_repeated_at_the_top_of_enough_pages_is_furniture():
    blocks = []
    for page in (1, 2, 3):
        blocks += [banner(page), body(page, f"sayfa {page} govdesi")]
    assert running_header_texts(blocks) == {"bolum basligi"}


def test_below_the_threshold_it_stays_a_real_heading():
    blocks = []
    for page in (1, 2):
        blocks += [banner(page), body(page)]
    assert running_header_texts(blocks) == set()


def test_a_heading_that_is_not_first_on_the_page_is_never_furniture():
    blocks = []
    for page in (1, 2, 3, 4):
        blocks += [body(page), banner(page), body(page, "devam")]
    assert running_header_texts(blocks) == set()


def test_repetition_is_counted_per_physical_page_not_per_logical_page():
    """Both halves of one spread must not count as two pages."""
    blocks = []
    for page in (1, 2):
        blocks += [
            banner(page, side="left"),
            body(page, side="left"),
            banner(page, side="right"),
            body(page, side="right"),
        ]
    # Four logical pages but only two physical ones, so below the threshold.
    assert running_header_texts(blocks) == set()


def test_matching_ignores_case_and_whitespace_only_differences():
    blocks = [
        banner(1, "  Bolum   Basligi "),
        body(1),
        banner(2, "BOLUM BASLIGI"),
        body(2),
        banner(3, "bolum basligi"),
        body(3),
    ]
    assert running_header_texts(blocks) == {"bolum basligi"}


def test_drop_removes_every_occurrence_and_keeps_all_body():
    blocks = []
    for page in (1, 2, 3):
        blocks += [banner(page), body(page, f"govde {page}")]
    blocks.append(banner(4, "GERCEK BASLIK"))
    blocks.append(body(4, "govde 4"))

    kept, furniture = drop_running_headers(blocks)
    assert furniture == {"bolum basligi"}
    assert [b.text for b in kept] == [
        "govde 1", "govde 2", "govde 3", "GERCEK BASLIK", "govde 4",
    ]


def test_drop_is_a_no_op_when_nothing_repeats():
    blocks = [banner(1, "A"), body(1), banner(2, "B"), body(2)]
    kept, furniture = drop_running_headers(blocks)
    assert furniture == set()
    assert [b.text for b in kept] == [b.text for b in blocks]


def test_a_body_block_with_the_same_text_is_not_dropped():
    blocks = []
    for page in (1, 2, 3):
        blocks += [banner(page), body(page)]
    blocks.append(body(4, "BOLUM BASLIGI"))
    kept, _ = drop_running_headers(blocks)
    assert any(b.text == "BOLUM BASLIGI" and b.heading_level is None for b in kept)


def test_threshold_must_be_at_least_two():
    with pytest.raises(ValueError):
        running_header_texts([banner(1)], min_pages=1)


def test_default_threshold_is_three_pages():
    assert DEFAULT_MIN_PAGES == 3


def test_markdown_emphasis_does_not_split_one_banner_into_two():
    """PyMuPDF4LLM emphasises the same banner on some pages and not others."""
    blocks = [
        banner(1, "**BOLUM BASLIGI**"),
        body(1),
        banner(2, "BOLUM BASLIGI"),
        body(2),
        banner(3, "_BOLUM BASLIGI_"),
        body(3),
    ]
    assert running_header_texts(blocks) == {"bolum basligi"}
    kept, furniture = drop_running_headers(blocks)
    assert furniture == {"bolum basligi"}
    assert all(block.heading_level is None for block in kept)


def test_a_banner_hidden_under_another_banner_is_still_caught():
    """Detection only sees the block that leads a page, so one pass is short.

    ``OUTER`` leads every page and ``INNER`` sits directly beneath it. Until
    ``OUTER`` is gone, ``INNER`` never leads anything.
    """
    blocks = []
    for page in (1, 2, 3):
        blocks += [
            banner(page, "OUTER"),
            banner(page, "INNER"),
            body(page, f"govde {page}"),
        ]

    kept, furniture = drop_running_headers(blocks)

    assert furniture == {"outer", "inner"}
    assert [b.text for b in kept] == ["govde 1", "govde 2", "govde 3"]


def test_iteration_stops_at_a_real_heading():
    blocks = []
    for page in (1, 2, 3):
        blocks += [banner(page, "OUTER"), banner(page, f"GERCEK {page}"),
                   body(page, f"govde {page}")]

    kept, furniture = drop_running_headers(blocks)

    assert furniture == {"outer"}
    assert [b.text for b in kept] == [
        "GERCEK 1", "govde 1", "GERCEK 2", "govde 2", "GERCEK 3", "govde 3",
    ]
