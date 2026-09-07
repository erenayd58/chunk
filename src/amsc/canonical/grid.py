"""Rebuild label -> value pairs inside a KPI card grid from page geometry.

PyMuPDF4LLM flattens the text it finds inside a picture region by vertical
position. When two cards in the same row use different font sizes their glyph
boxes have different vertical centres, so the flattener can emit the right
card's value before the left card's -- the labels stay in column order while
the values swap. The result reads as a plausible pairing and is wrong, which is
the worst failure mode for a retrieval corpus.

The pairing is not lost, only the serialization is: a KPI card is drawn as a
rectangle holding exactly one small label and one large value. This module
rebuilds the pairs from that geometry.

It is deliberately narrow. Every gate below must hold or the caller keeps the
original flattened text untouched:

  * at least two disjoint container rectangles inside the picture region
  * every chosen container holds exactly two deduplicated text lines
  * those two lines differ in font size by a clear factor -- the typographic
    signature of a label above a headline figure
  * no text line is left outside a container

Bar charts, donut charts and organisation charts fail these gates by
construction (no containers, uncovered lines, or uniform font size), so no new
guess is produced for them. Nothing here is document specific: no heading,
label or figure is matched by text.
"""

from __future__ import annotations

from dataclasses import dataclass

BBox = tuple[float, float, float, float]

#: A container narrower or shorter than this is a label badge or a rule, not a
#: card. Conservative gate, not a tuned parameter.
MIN_CONTAINER_SIDE = 24.0
#: A rectangle covering nearly the whole picture is the frame, not a card.
MAX_CONTAINER_AREA_RATIO = 0.9
#: One container is a single figure, not a grid; a grid needs at least two.
MIN_CONTAINERS = 2
#: A KPI card sets its value several times larger than its label. Requiring a
#: clear separation keeps two-line captions of uniform size out.
MIN_FONT_SIZE_RATIO = 1.5


@dataclass(frozen=True)
class VisualTextLine:
    """One text line inside a picture region, with its geometry."""

    text: str
    bbox: BBox
    font_size: float


@dataclass(frozen=True)
class PictureGeometry:
    """Everything the reconstruction needs, captured while the PDF is open."""

    region: BBox
    lines: tuple[VisualTextLine, ...] = ()
    containers: tuple[BBox, ...] = ()


def _normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def _span_overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _area(box: BBox) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _centre(box: BBox) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _centre_inside(box: BBox, region: BBox) -> bool:
    x, y = _centre(box)
    return region[0] <= x <= region[2] and region[1] <= y <= region[3]


def _is_overprint(a: BBox, b: BBox) -> bool:
    """True when two boxes overlap enough to be the same glyphs drawn twice."""
    intersection = _span_overlap(a[0], a[2], b[0], b[2]) * _span_overlap(
        a[1], a[3], b[1], b[3]
    )
    smaller = min(_area(a), _area(b))
    return smaller > 0.0 and intersection / smaller > 0.5


def deduplicate_lines(
    lines: tuple[VisualTextLine, ...] | list[VisualTextLine],
) -> list[VisualTextLine]:
    """Drop shadow/overprint copies: same text drawn over the same place.

    Two cards legitimately carrying the same label sit far apart, so their
    boxes do not overlap and both survive.
    """
    ordered = sorted(
        lines,
        key=lambda line: (
            round(line.bbox[1], 2),
            round(line.bbox[0], 2),
            line.text,
        ),
    )
    kept: list[VisualTextLine] = []
    for line in ordered:
        text = _normalized(line.text)
        if not text:
            continue
        if any(
            _normalized(other.text) == text and _is_overprint(other.bbox, line.bbox)
            for other in kept
        ):
            continue
        kept.append(line)
    return kept


def _select_containers(
    region: BBox,
    containers: tuple[BBox, ...] | list[BBox],
    lines: list[VisualTextLine],
) -> tuple[list[tuple[BBox, tuple[int, ...]]], set[int]]:
    """Smallest disjoint rectangles that each hold two or more text lines."""
    region_area = _area(region)
    candidates: list[tuple[BBox, tuple[int, ...]]] = []
    for box in containers:
        if (
            box[2] - box[0] < MIN_CONTAINER_SIDE
            or box[3] - box[1] < MIN_CONTAINER_SIDE
        ):
            continue
        if region_area > 0.0 and _area(box) > region_area * MAX_CONTAINER_AREA_RATIO:
            continue
        held = tuple(
            index
            for index, line in enumerate(lines)
            if _centre_inside(line.bbox, box)
        )
        if len(held) < 2:
            continue
        candidates.append((box, held))

    candidates.sort(key=lambda item: (_area(item[0]), item[0][1], item[0][0]))
    chosen: list[tuple[BBox, tuple[int, ...]]] = []
    covered: set[int] = set()
    for box, held in candidates:
        if covered.intersection(held):
            continue
        chosen.append((box, held))
        covered.update(held)
    return chosen, covered


def _row_major(
    cards: list[tuple[BBox, str, str]],
) -> list[tuple[BBox, str, str]]:
    """Reading order: rows top to bottom, cards left to right inside a row.

    Cards of one row are grouped by vertical overlap rather than by a sorted
    top edge, because a row's cards are not always aligned to the pixel.
    """
    rows: list[list[tuple[BBox, str, str]]] = []
    for card in sorted(cards, key=lambda item: (item[0][1], item[0][0])):
        box = card[0]
        for row in rows:
            reference = row[0][0]
            shared = _span_overlap(reference[1], reference[3], box[1], box[3])
            smaller = min(reference[3] - reference[1], box[3] - box[1])
            if smaller > 0.0 and shared / smaller > 0.5:
                row.append(card)
                break
        else:
            rows.append([card])
    return [
        card
        for row in rows
        for card in sorted(row, key=lambda item: (item[0][0], item[0][1]))
    ]


def reconstruct_card_grid(geometry: PictureGeometry | None) -> str | None:
    """Return ``label | value`` lines, or ``None`` when confidence is short.

    ``None`` means "keep whatever the extractor already produced". It is the
    answer for every picture family that is not a card grid.
    """
    if geometry is None:
        return None
    lines = deduplicate_lines(geometry.lines)
    if len(lines) < MIN_CONTAINERS * 2:
        return None

    chosen, covered = _select_containers(geometry.region, geometry.containers, lines)
    if len(chosen) < MIN_CONTAINERS:
        return None
    if len(covered) != len(lines):
        # A line outside every card means the picture carries content the card
        # model does not explain -- an axis, a legend, a caption.
        return None

    cards: list[tuple[BBox, str, str]] = []
    for box, held in chosen:
        if len(held) != 2:
            return None
        first, second = sorted(
            (lines[index] for index in held),
            key=lambda line: (line.font_size, line.bbox[1], line.bbox[0]),
        )
        if first.font_size <= 0.0:
            return None
        if second.font_size < first.font_size * MIN_FONT_SIZE_RATIO:
            return None
        label, value = first.text.strip(), second.text.strip()
        if not label or not value:
            return None
        cards.append((box, label, value))

    return "\n".join(f"{label} | {value}" for _, label, value in _row_major(cards))
