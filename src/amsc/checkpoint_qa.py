from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from typing import Any, Sequence

from .models import RawDocumentUnit, UnitType


_TERMINAL_PUNCTUATION = frozenset(".!?…)]}'\"’”)」》")
_TRAILING_MARKDOWN = re.compile(r"(?:\*\*|__|`)+$")


def load_qa_units(path: str | Path) -> list[RawDocumentUnit]:
    units: list[RawDocumentUnit] = []
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                units.append(RawDocumentUnit.model_validate_json(line))
            except Exception as exc:
                raise ValueError(
                    f"Invalid canonical JSONL at line {line_number}: {exc}"
                ) from exc
    return units


def load_visual_records(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None or not Path(path).is_file():
        return []
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except Exception as exc:
                raise ValueError(
                    f"Invalid visual provenance JSONL at line {line_number}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise ValueError(
                    f"Visual provenance line {line_number} must be an object"
                )
            records.append(payload)
    return records


def build_qa_summary(
    units: Sequence[RawDocumentUnit],
    *,
    visual_records: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    ids = [unit.unit_id for unit in units]
    duplicate_ids = sorted(
        unit_id for unit_id, count in Counter(ids).items() if count > 1
    )
    orders = [unit.order for unit in units]
    expected_orders = list(range(1, len(units) + 1))
    order_problems = [
        {"position": position, "expected": expected, "actual": actual}
        for position, (expected, actual) in enumerate(
            zip(expected_orders, orders, strict=False), start=1
        )
        if expected != actual
    ]
    if len(orders) != len(expected_orders):
        order_problems.append(
            {"expected_count": len(expected_orders), "actual_count": len(orders)}
        )

    paragraphs = [unit for unit in units if unit.type == UnitType.PARAGRAPH]
    non_visual_paragraphs = [
        unit
        for unit in paragraphs
        if getattr(unit.source, "content_origin", None) != "visual"
    ]
    suspicious_short = [
        _unit_review_item(unit)
        for unit in non_visual_paragraphs
        if len(unit.text.split()) <= 8
    ]
    incomplete = [
        _unit_review_item(unit)
        for unit in non_visual_paragraphs
        if _looks_incomplete(unit.text)
    ]
    heading_counts = Counter(
        f"H{unit.heading_level}"
        for unit in units
        if unit.type == UnitType.HEADING
    )
    visual_units = [
        unit
        for unit in units
        if getattr(unit.source, "content_origin", None) == "visual"
    ]
    visual_without_text = [
        record.get("visual_provenance_id")
        for record in visual_records
        if not record.get("has_extracted_picture_text")
    ]

    layout_review = _layout_reading_order_review(units)
    layout_review["manual_review_candidates"] = {
        "suspicious_short_paragraphs": suspicious_short,
        "paragraphs_ending_with_comma_semicolon_or_incomplete_sentence": incomplete,
    }

    return {
        "total_units": len(units),
        "headings": sum(unit.type == UnitType.HEADING for unit in units),
        "paragraphs": len(paragraphs),
        "lists": sum(unit.type == UnitType.LIST for unit in units),
        "tables": sum(unit.type == UnitType.TABLE for unit in units),
        "visual_units": len(visual_units),
        "empty_section_path": sum(not unit.section_path for unit in units),
        "headings_by_level": dict(sorted(heading_counts.items())),
        "suspicious_short_paragraphs": suspicious_short,
        "paragraphs_ending_with_comma_semicolon_or_incomplete_sentence": incomplete,
        "visual_units_without_text": visual_without_text,
        "duplicate_unit_ids": duplicate_ids,
        "canonical_order_integrity": {
            "ok": not order_problems,
            "problems": order_problems,
        },
        "layout_reading_order_review": layout_review,
    }


def render_qa_preview(
    units: Sequence[RawDocumentUnit],
    *,
    visual_records: Sequence[dict[str, Any]] = (),
) -> str:
    summary = build_qa_summary(units, visual_records=visual_records)
    lines = [
        "# Checkpoint Canonical Units QA Preview",
        "",
        "## Automatic QA summary",
        "",
        "```json",
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Units in canonical PDF order",
        "",
    ]
    current_group: tuple[int | None, str] | None = None
    for unit in units:
        side = str(getattr(unit.source, "logical_page_side", "single"))
        group = (unit.source.page, side)
        if group != current_group:
            if current_group is not None:
                lines.append("")
            lines.extend(
                [
                    f"### PAGE {unit.source.page} / {side.upper()}",
                    "",
                ]
            )
            current_group = group
        lines.append(f"[{_unit_label(unit)}] {unit.unit_id}  {unit.text}")
        lines.append(
            "  section_path: "
            + json.dumps(unit.section_path, ensure_ascii=False)
        )
        layout_details = {
            "layout_box_index": getattr(unit.source, "layout_box_index", None),
            "logical_column": getattr(unit.source, "logical_column", None),
            "layout_band": getattr(unit.source, "layout_band", None),
            "layout_reading_order_index": getattr(
                unit.source, "layout_reading_order_index", None
            ),
        }
        if any(value is not None for value in layout_details.values()):
            lines.append(
                "  layout: "
                + json.dumps(layout_details, ensure_ascii=False, sort_keys=True)
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_qa_preview(
    *,
    canonical_path: str | Path,
    output_path: str | Path,
    visual_provenance_path: str | Path | None = None,
) -> Path:
    units = load_qa_units(canonical_path)
    records = load_visual_records(visual_provenance_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render_qa_preview(units, visual_records=records),
        encoding="utf-8",
        newline="\n",
    )
    return destination


def _layout_reading_order_review(
    units: Sequence[RawDocumentUnit],
) -> dict[str, Any]:
    grouped: dict[tuple[int | None, str], list[dict[str, Any]]] = {}
    for unit in units:
        source = unit.source
        order_index = getattr(source, "layout_reading_order_index", None)
        box_index = getattr(source, "layout_box_index", None)
        if order_index is None or box_index is None:
            continue
        key = (source.page, str(getattr(source, "logical_page_side", "single")))
        group = grouped.setdefault(key, [])
        identity = (box_index, order_index)
        if any(item["identity"] == identity for item in group):
            continue
        group.append(
            {
                "identity": identity,
                "layout_box_index": box_index,
                "layout_reading_order_index": order_index,
                "logical_column": getattr(source, "logical_column", None),
                "layout_band": getattr(source, "layout_band", None),
                "bbox": getattr(source, "layout_bbox_logical", None),
            }
        )

    violations: list[dict[str, Any]] = []
    reviewed_groups: list[str] = []
    column_rank = {"left": 0, "right": 1, "full_width": 2}
    for (page, side), boxes in grouped.items():
        group_name = f"page={page}/{side}"
        reviewed_groups.append(group_name)
        observed_indices = [box["layout_reading_order_index"] for box in boxes]
        if observed_indices != sorted(observed_indices):
            violations.append(
                {
                    "group": group_name,
                    "reason": "layout_reading_order_index_not_monotonic",
                    "observed": observed_indices,
                }
            )
        if all(
            box["layout_band"] is not None
            and box["logical_column"] in column_rank
            and isinstance(box["bbox"], (list, tuple))
            and len(box["bbox"]) == 4
            for box in boxes
        ):
            expected = sorted(
                boxes,
                key=lambda box: (
                    box["layout_band"],
                    column_rank[box["logical_column"]],
                    box["bbox"][1],
                    box["bbox"][3],
                    box["bbox"][0],
                    box["bbox"][2],
                    box["layout_box_index"],
                ),
            )
            expected_indices = [
                box["layout_reading_order_index"] for box in expected
            ]
            if observed_indices != expected_indices:
                violations.append(
                    {
                        "group": group_name,
                        "reason": "not_column_major_left_to_right",
                        "observed": observed_indices,
                        "expected": expected_indices,
                    }
                )

    profile_units = [
        unit
        for unit in units
        if getattr(unit.source, "reading_order_policy", None)
        == "column-major-left-to-right"
    ]
    missing = [
        unit.unit_id
        for unit in profile_units
        if getattr(unit.source, "layout_reading_order_index", None) is None
    ]
    return {
        "profile_applied": bool(profile_units),
        "geometry_conformance": {
            "ok": not violations and not missing,
            "violations": violations,
            "missing_order_provenance": missing,
            "reviewed_logical_pages": reviewed_groups,
        },
    }


def _unit_label(unit: RawDocumentUnit) -> str:
    if getattr(unit.source, "content_origin", None) == "visual":
        return "VISUAL"
    if unit.type == UnitType.HEADING:
        return f"H{unit.heading_level}"
    return {
        UnitType.PARAGRAPH: "P",
        UnitType.LIST: "LIST",
        UnitType.TABLE: "TABLE",
    }[unit.type]


def _looks_incomplete(text: str) -> bool:
    stripped = _TRAILING_MARKDOWN.sub("", text.rstrip()).rstrip()
    if not stripped:
        return True
    if stripped.endswith((",", ";", ":")):
        return True
    return stripped[-1] not in _TERMINAL_PUNCTUATION


def _unit_review_item(unit: RawDocumentUnit) -> dict[str, Any]:
    return {
        "unit_id": unit.unit_id,
        "page": unit.source.page,
        "logical_page_side": getattr(unit.source, "logical_page_side", "single"),
        "text": unit.text,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.checkpoint_qa",
        description="Render a human-readable QA preview for canonical units",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--visual-provenance", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    visual_path = args.visual_provenance
    if visual_path is None:
        candidate = args.input.with_suffix(".visual-provenance.jsonl")
        visual_path = candidate if candidate.is_file() else None
    write_qa_preview(
        canonical_path=args.input,
        output_path=args.output,
        visual_provenance_path=visual_path,
    )
    print(
        json.dumps(
            {"input": str(args.input), "output": str(args.output), "status": "ok"},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
