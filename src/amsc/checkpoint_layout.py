from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
import yaml

from .visual_grid import PictureGeometry


LogicalColumn = Literal["left", "right", "full_width"]


class CheckpointLayoutProfile(BaseModel):
    """Explicit checkpoint-only page geometry policy.

    Column count is intentionally configured rather than inferred. The only
    supported profile is the two-column KKB checkpoint layout.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    spread_mode: Literal["left-right"]
    logical_columns: Literal[2]
    reading_order: Literal["column-major-left-to-right"]


def load_checkpoint_layout_profile(
    path: str | Path,
) -> CheckpointLayoutProfile:
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"Checkpoint layout profile does not exist: {source}")
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Checkpoint layout profile must be a YAML mapping")
    return CheckpointLayoutProfile.model_validate(payload)


@dataclass(frozen=True)
class LayoutBox:
    index: int
    layout_class: str
    # Physical PDF coordinates. Retained as ``bbox`` for compatibility with
    # the existing picture provenance contract.
    bbox: tuple[float, float, float, float]
    markdown_start: int
    markdown_end: int
    # Coordinates inside the cropped logical page. These, not Markdown
    # serialization offsets, drive explicit column ordering.
    logical_bbox: tuple[float, float, float, float] | None = None
    logical_column: LogicalColumn | None = None
    layout_band: int | None = None
    reading_order_index: int | None = None
    reading_order_policy: str | None = None
    # Text and container geometry inside a picture region. Captured only
    # when the extractor is asked for it, so the default extraction is
    # byte-identical to the frozen one.
    picture_geometry: PictureGeometry | None = None
    # Largest type size printed inside this box. Captured only when the
    # extractor is asked for it; the default extraction never reads it.
    font_size: float | None = None


class ExplicitLogicalPageColumnOrderer:
    """Order one logical page by configured two-column geometry.

    Boxes crossing the logical-page midpoint are row anchors. Anchors split
    the page into vertical bands. Inside each band, the left column is read
    top-to-bottom followed by the right column top-to-bottom. The anchor is
    then emitted at its vertical position. PyMuPDF4LLM Markdown offsets are
    never used as an ordering signal.
    """

    def __init__(self, profile: CheckpointLayoutProfile) -> None:
        self.profile = profile

    def order(
        self,
        boxes: tuple[LayoutBox, ...] | list[LayoutBox],
        *,
        logical_page_width: float,
    ) -> tuple[LayoutBox, ...]:
        if logical_page_width <= 0:
            raise ValueError("logical_page_width must be positive")
        divider = logical_page_width / 2.0
        classified = [self._classify(box, divider=divider) for box in boxes]
        anchors = sorted(
            (box for box in classified if box.logical_column == "full_width"),
            key=self._geometry_key,
        )
        remaining = [
            box for box in classified if box.logical_column != "full_width"
        ]

        ordered: list[LayoutBox] = []
        band = 0
        for anchor in anchors:
            anchor_mid_y = self._mid_y(anchor)
            before = [box for box in remaining if self._mid_y(box) < anchor_mid_y]
            remaining = [box for box in remaining if box not in before]
            ordered.extend(self._order_band(before, band=band))
            ordered.append(replace(anchor, layout_band=band))
            band += 1
        ordered.extend(self._order_band(remaining, band=band))

        policy = self.profile.reading_order
        return tuple(
            replace(
                box,
                reading_order_index=index,
                reading_order_policy=policy,
            )
            for index, box in enumerate(ordered, start=1)
        )

    def _classify(self, box: LayoutBox, *, divider: float) -> LayoutBox:
        x0, _, x1, _ = self._logical_bbox(box)
        if x0 < divider < x1:
            column: LogicalColumn = "full_width"
        elif (x0 + x1) / 2.0 < divider:
            column = "left"
        else:
            column = "right"
        return replace(box, logical_column=column)

    def _order_band(self, boxes: list[LayoutBox], *, band: int) -> list[LayoutBox]:
        left = sorted(
            (box for box in boxes if box.logical_column == "left"),
            key=self._geometry_key,
        )
        right = sorted(
            (box for box in boxes if box.logical_column == "right"),
            key=self._geometry_key,
        )
        return [replace(box, layout_band=band) for box in (*left, *right)]

    @classmethod
    def _geometry_key(cls, box: LayoutBox) -> tuple[float, float, float, float, int]:
        x0, y0, x1, y1 = cls._logical_bbox(box)
        return (y0, y1, x0, x1, box.index)

    @classmethod
    def _mid_y(cls, box: LayoutBox) -> float:
        _, y0, _, y1 = cls._logical_bbox(box)
        return (y0 + y1) / 2.0

    @staticmethod
    def _logical_bbox(box: LayoutBox) -> tuple[float, float, float, float]:
        return box.logical_bbox or box.bbox
