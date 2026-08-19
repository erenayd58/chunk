from __future__ import annotations

import argparse
import json
from pathlib import Path

from .checkpoint_adapter import prepare_checkpoint, unit_type_counts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.prepare_checkpoint",
        description="Prepare deterministic checkpoint-only canonical units from a PDF",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--pages",
        help="Optional 1-based inclusive pages, for example 40-55,61",
    )
    parser.add_argument(
        "--layout-profile",
        "--profile",
        dest="layout_profile",
        type=Path,
        help=(
            "Optional explicit checkpoint layout profile; for KKB use "
            "configs/checkpoint-kkb-2024.yaml"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = prepare_checkpoint(
            input_path=args.input,
            output_path=args.output,
            pages=args.pages,
            layout_profile=args.layout_profile,
        )
    except (RuntimeError, ValueError) as exc:
        _parser().error(str(exc))

    print(
        json.dumps(
            {
                "document_id": result.units[0].document_id,
                "manifest": str(result.manifest_path),
                "layout_profile": (
                    result.layout_profile.profile_id
                    if result.layout_profile is not None
                    else None
                ),
                "output": str(args.output),
                "pymupdf4llm_version": result.pymupdf4llm_version,
                "picture_count": result.picture_count,
                "selected_pages": list(result.selected_pages),
                "status": "ok",
                "unit_counts": unit_type_counts(result.units),
                "visual_atomic_unit_count": result.visual_atomic_unit_count,
                "visual_provenance": str(result.visual_provenance_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
