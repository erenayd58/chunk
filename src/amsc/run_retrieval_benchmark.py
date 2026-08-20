from __future__ import annotations

import argparse
import json
from pathlib import Path

from .retrieval_benchmark import run_retrieval_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Phase 4 retrieval benchmark")
    parser.add_argument(
        "--config", default="configs/retrieval-benchmark-v1.yaml"
    )
    parser.add_argument(
        "--output", default="evaluation/kkb-2024/retrieval-benchmark/results"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_retrieval_benchmark(
        config_path=Path(args.config), output_dir=Path(args.output)
    )
    print(
        json.dumps(
            {
                "query_count": summary["query_count"],
                "candidates": {
                    candidate_id: {
                        "hit_at_5": metrics["hit_at_5"],
                        "mrr": metrics["mrr"],
                    }
                    for candidate_id, metrics in summary["candidates"].items()
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

