from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cache import FileEmbeddingCache
from .chunker import V1Chunker, V2Chunker, V3Chunker
from .config import V1Config, V2Config, V3Config, V4Config, load_config
from .embeddings import (
    CachedSemanticBoundaryEmbedder,
    SentenceTransformerBoundaryEmbedder,
)
from .io import (
    load_jsonl_units,
    write_chunking_result,
    write_resolved_config,
)
from .tokenization import TiktokenTokenCounter
from .v4_chunker import V4Chunker


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amsc")
    subcommands = parser.add_subparsers(dest="command", required=True)

    validate = subcommands.add_parser("validate", help="Validate canonical JSONL")
    validate.add_argument("--input", required=True, type=Path)

    chunk = subcommands.add_parser(
        "chunk", help="Run the configured V1/V2/V3/V4 chunker"
    )
    chunk.add_argument("--input", required=True, type=Path)
    chunk.add_argument("--config", required=True, type=Path)
    chunk.add_argument("--output", required=True, type=Path)
    chunk.add_argument("--ablation", choices=["a1", "a2", "a3", "a4"])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    units = load_jsonl_units(args.input)
    if args.command == "validate":
        print(
            json.dumps(
                {
                    "status": "valid",
                    "document_id": units[0].document_id,
                    "unit_count": len(units),
                },
                ensure_ascii=False,
            )
        )
        return 0

    config = load_config(args.config)
    if args.ablation is not None:
        if not isinstance(config, V4Config):
            raise ValueError("--ablation is only valid with algorithm.version=v4")
        config = config.model_copy(
            update={
                "ablation": config.ablation.model_copy(
                    update={"composition": args.ablation}
                )
            }
        )
    token_counter = TiktokenTokenCounter(config.token_counter.encoding)
    embedder = SentenceTransformerBoundaryEmbedder.from_pretrained(
        config.boundary_embedding.model,
        revision=config.boundary_embedding.revision,
        device=config.boundary_embedding.device,
        prefix=config.boundary_embedding.prefix,
        prefix_policy=config.boundary_embedding.prefix_policy,
        max_input_tokens_override=(
            config.boundary_embedding.max_input_tokens_override
        ),
        normalize_embeddings=config.boundary_embedding.normalize_embeddings,
    )
    cached = CachedSemanticBoundaryEmbedder(
        embedder,
        FileEmbeddingCache(config.boundary_embedding.cache_dir),
    )
    if isinstance(config, V1Config):
        chunker_type = V1Chunker
    elif isinstance(config, V2Config):
        chunker_type = V2Chunker
    elif isinstance(config, V3Config):
        chunker_type = V3Chunker
    else:
        chunker_type = V4Chunker
    result = chunker_type(
        config=config,
        token_counter=token_counter,
        boundary_embedder=cached,
    ).chunk(units)  # type: ignore[arg-type]
    write_chunking_result(result, args.output)
    write_resolved_config(config, args.output)
    print(
        json.dumps(
            {
                "status": "ok",
                "document_id": result.document_id,
                "chunk_count": len(result.chunks),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
