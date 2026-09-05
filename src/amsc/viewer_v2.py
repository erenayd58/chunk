"""Viewer v2 -- the earlier single-file page, kept as the research build.

**Status: compatibility.** Viewer v3 (:mod:`amsc.viewer_v3`) is the product
page and the one ``start-demo.ps1`` serves. This module stays because it is
still load-bearing for two things v3 does not do: the research/benchmark
build with the ``--agentic`` provenance arm, and a manual fallback page you
can serve by hand (``--viewer artifacts/viewer-v2/index.html``). It is a
*page builder only* -- every payload it renders is read by
:mod:`amsc.viewer_corpus`, which both pages share.

The page emits one self-contained offline HTML file with four modes:

* **Sunum** -- what we did and what the difference is: the four chunking
  methods explained, the same page of a document compared across chunkers,
  every boundary with a human-language reason, and the Standard vs Deep
  Analysis results in a few numbers.
* **Sorgu** -- how it works in use: the frozen gold-query retrieval view
  (offline) and, when served by :mod:`amsc.viewer_server`, a live
  "ask the document" chat over the same chunks with source cards.
* **Debug** -- why the system decided what it decided: canonical units,
  section paths, mappings, the Deep Analysis decision trail (Standard cut,
  proposed cut, final cut, verifier verdict, smells before/after), parser
  findings and representation ceilings.
* **Benchmark** -- what the measurements say: the frozen three-arm
  benchmark untouched, and a separate, clearly-labelled Deep Analysis panel
  with structural, retrieval, LLM-usage and latency numbers.

Inputs, per document (all read by :mod:`amsc.viewer_corpus`):

* ``--benchmark DOC=DIR`` -- a frozen ``amsc.chunk_benchmark`` tree (three
  arms, gold queries, pinned canonical). Optional when ``--deep`` is given.
* ``--deep DOC=DIR`` -- an ``amsc.deep_run`` tree packaged by
  ``amsc.deep_arm`` (``arm/``, ``standard/``, ``boundary-decisions.json``).
  Adds the Agentic Chunker (Deep Analysis) as the fourth arm, or, without a
  benchmark tree, builds a Standard-vs-Deep document on its own.
* ``--agentic DOC=DIR`` -- the earlier ``amsc.agentic_chunker`` research
  tree, kept for provenance; it fills the same fourth-arm slot with its own
  reduced attribution and cannot be combined with ``--deep`` for one document.

Unlike v3, this build requires at least one tree: it has no product shell and
no live-workspace mode, so a page with no corpus would show nothing.

Beside the HTML it writes ``catalog.json`` -- the documents, arms and chunk
files the HTML shows -- which is what the chat server serves, so the live
chat and the page can never disagree about which chunks exist.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

from .viewer_corpus import (
    ARM_LABELS,
    ARM_ORDER,
    PRODUCT_ARM_ORDER,
    REFERENCE_PRICE_PER_M,
    catalog,
    load_corpus,
)
from .viewer_v2_template import TEMPLATE

#: Compatibility re-exports. The reader moved to :mod:`amsc.viewer_corpus`
#: and these names are kept here because callers and tests reach for them at
#: ``amsc.viewer_v2``. New code should import them from ``viewer_corpus``.
from .viewer_corpus import (  # noqa: E402,F401  (re-export, not use)
    ARM_KINDS,
    CHARS_PER_TOKEN,
    DOC_LABELS,
    REQUIRED_ARM_FILES,
    REQUIRED_DEEP_ARM_FILES,
    REQUIRED_TREE_FILES,
    display_html,
    heading_plain,
)


def build_viewer(
    benchmarks: Mapping[str, Path],
    output: Path,
    root: Path = Path("."),
    agentic: Mapping[str, Path] | None = None,
    deep: Mapping[str, Path] | None = None,
    labels: Mapping[str, str] | None = None,
    write_catalog: bool = True,
) -> Path:
    """Build the single-file viewer for the given trees.

    ``benchmarks`` maps a document id to a frozen chunk-benchmark tree;
    ``deep`` maps a document id to a packaged Deep Analysis tree (a document
    may appear only there); ``agentic`` maps a document id to the earlier
    research tree. Without ``deep``/``agentic`` the output is byte-identical
    to a three-arm build.
    """
    agentic = dict(agentic or {})
    deep = dict(deep or {})
    labels = dict(labels or {})
    # Benchmark-backed documents first, in the order given, then the
    # deep-only ones: the page opens on the richest document.
    documents = list(benchmarks) + [doc for doc in deep if doc not in benchmarks]
    if not documents:
        raise ValueError("at least one benchmark tree or packaged deep tree is required")
    unknown = sorted(set(agentic) - set(benchmarks))
    if unknown:
        raise ValueError(
            f"agentic trees given for unknown documents: {unknown}; every "
            "agentic tree needs its benchmark tree"
        )
    output = Path(output)
    if "evaluation" in output.parts:
        raise ValueError("refusing to write the viewer into evaluation/ (frozen)")

    docs = {
        doc: load_corpus(
            Path(benchmarks[doc]) if doc in benchmarks else None,
            Path(root),
            agentic_dir=agentic.get(doc),
            deep_dir=deep.get(doc),
            label=labels.get(doc),
        )
        for doc in documents
    }
    data = {
        "docs": docs,
        "docOrder": documents,
        "armOrder": list(ARM_ORDER),
        "armLabels": ARM_LABELS,
        "productArmOrder": list(PRODUCT_ARM_ORDER),
        "price": {**REFERENCE_PRICE_PER_M, "note": "list prices observed 2026-08-29; approximate"},
        "generator": "amsc.viewer_v2",
    }
    payload = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).replace("</", "<\\/")

    document = TEMPLATE.replace("__VIEWER_DATA__", payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    if write_catalog:
        index = catalog(docs, benchmarks, deep, agentic, Path(root), generator="amsc.viewer_v2")
        (output.parent / "catalog.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return output


def _parse_specs(parser: argparse.ArgumentParser, specs: Sequence[str], flag: str) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for spec in specs:
        doc, _, directory = spec.partition("=")
        if not directory:
            parser.error(f"{flag} expects DOC=DIR, got {spec!r}")
        out[doc] = Path(directory)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.viewer_v2",
        description=(
            "Build the self-contained Viewer v2 HTML (Sunum / Sorgu / Debug / "
            "Benchmark) from completed artifact trees"
        ),
    )
    parser.add_argument(
        "--benchmark",
        action="append",
        default=[],
        metavar="DOC=DIR",
        help="document id and its frozen chunk-benchmark tree, e.g. "
        "kkb-2024=artifacts/chunk-benchmark-v5/kkb-2024 (repeatable)",
    )
    parser.add_argument(
        "--deep",
        action="append",
        default=[],
        metavar="DOC=DIR",
        help="packaged Deep Analysis tree for a document, e.g. "
        "kkb-2024=artifacts/deep-analysis/kkb-2024-final (repeatable)",
    )
    parser.add_argument(
        "--agentic",
        action="append",
        default=[],
        metavar="DOC=DIR",
        help="earlier agentic-chunker research tree for a document (repeatable)",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="DOC=LABEL",
        help="display label for a document (repeatable)",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--no-catalog", action="store_true", help="do not write catalog.json")
    args = parser.parse_args(argv)

    benchmarks = _parse_specs(parser, args.benchmark, "--benchmark")
    deep = _parse_specs(parser, args.deep, "--deep")
    agentic = _parse_specs(parser, args.agentic, "--agentic")
    labels: dict[str, str] = {}
    for spec in args.label:
        doc, _, text = spec.partition("=")
        if not text:
            parser.error(f"--label expects DOC=LABEL, got {spec!r}")
        labels[doc] = text
    if not benchmarks and not deep:
        parser.error("at least one --benchmark or --deep is required")

    destination = build_viewer(
        benchmarks, args.output, root=args.root, agentic=agentic, deep=deep,
        labels=labels, write_catalog=not args.no_catalog,
    )
    documents = list(benchmarks) + [doc for doc in deep if doc not in benchmarks]
    print(json.dumps({"output": str(destination), "documents": documents}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
