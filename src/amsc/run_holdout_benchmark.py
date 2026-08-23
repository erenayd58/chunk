import argparse
import json
from pathlib import Path
from amsc.holdout_benchmark import run_retrieval_benchmark

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 5 Holdout Validation Benchmark")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/holdout-benchmark-v1.yaml"),
        help="Path to YAML configuration",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/holdout-kkb-2022/retrieval-benchmark/results"),
        help="Path to write evaluation results",
    )
    args = parser.parse_args(argv)
    
    summary = run_retrieval_benchmark(
        config_path=args.config,
        output_dir=args.output,
    )
    
    print(
        json.dumps(
            {
                "status": "ok",
                "benchmark_version": summary["benchmark_version"],
                "benchmark_status": summary["status"],
                "query_count": summary["query_count"],
                "output": str(args.output),
                "hit_at_5": {
                    candidate_id: metric["hit_at_5"]
                    for candidate_id, metric in summary["candidates"].items()
                },
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
