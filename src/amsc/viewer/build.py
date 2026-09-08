"""Viewer v3 -- this repository's own page over its frozen benchmark corpus.

A **page builder only**: every document payload it embeds is read by
:mod:`amsc.viewer.corpus`, the reader it shares with the RAG console's
packaging worker, so the page and the console are looking at one shape.

The page answers one question before all others: *where does a chunk start,
where does it end, and how do two methods cut the same content differently?*
Everything else (ids, strategies, decision records) is behind progressive
disclosure.

**This is not the product's Viewer.** That is a screen of the RAG console,
built in ``chat_rag/frontend/app/viewer/``, reading ``/api/v1`` for a live
document. What is here reads *this* repository's frozen research trees, which
the console has no copy of and does not want one, and it is opened as a file:
the HTTP server that used to serve it (and relay the console for a live
document) went with the console's Flask surface in Step 13.

    py -3.11 -m amsc.viewer.build `
      --benchmark kkb-2024=artifacts/chunk-benchmark-v5/kkb-2024 `
      --deep kkb-2024=artifacts/deep-analysis/kkb-2024-final `
      --output artifacts/viewer-v3/index.html

With no trees at all it builds an empty shell, which is the only build a fresh
clone can make -- the frozen research trees are not in version control -- and
is what the tests use to check that the build reads the registry rather than a
list of its own.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

from ..chunking import registry
from .corpus import catalog, load_corpus
from .template import TEMPLATE

#: Product order, product names and one-line summaries -- read from the
#: method registry (``amsc.chunking.registry``), which is where a method is added. The
#: page embeds them at build time; presence in a document is always read
#: from the document's own arms, so these only describe a method that is
#: actually there. Live views: a method registered after import is listed.
METHOD_ORDER = registry.ORDER
METHOD_LABELS = registry.LABELS
METHOD_SUMMARIES = registry.SUMMARIES


def build_viewer(
    benchmarks: Mapping[str, Path],
    output: Path,
    root: Path = Path("."),
    deep: Mapping[str, Path] | None = None,
    labels: Mapping[str, str] | None = None,
    write_catalog: bool = True,
) -> Path:
    """Build the single-file Viewer v3 for the given trees.

    ``benchmarks`` maps a document id to a frozen chunk-benchmark tree,
    ``deep`` to a packaged Deep Analysis tree. Both may be empty, which builds
    an empty shell. The per-document payload is exactly
    ``viewer_corpus.load_corpus`` output -- the same reader the RAG console's
    packager calls, which is what keeps one payload shape across both
    repositories.
    """
    deep = dict(deep or {})
    labels = dict(labels or {})
    documents = list(benchmarks) + [doc for doc in deep if doc not in benchmarks]
    # No documents is a legitimate build, and the only one a clean checkout can
    # make: the frozen benchmark and Deep trees are git-ignored research output
    # that cannot be committed, so requiring one of them left this page
    # buildable on exactly one machine. The method order, labels and summaries
    # below are build-time constants read from the registry, and every
    # corpus-driven view reads ``DATA.docOrder``, which is then simply empty.
    output = Path(output)
    if "evaluation" in output.parts:
        raise ValueError("refusing to write the viewer into evaluation/ (frozen)")

    docs = {
        doc: load_corpus(
            Path(benchmarks[doc]) if doc in benchmarks else None,
            Path(root),
            deep_dir=deep.get(doc),
            label=labels.get(doc),
        )
        for doc in documents
    }
    data = {
        "docs": docs,
        "docOrder": documents,
        "methodOrder": list(METHOD_ORDER),
        "methodLabels": dict(METHOD_LABELS),
        "methodSummaries": dict(METHOD_SUMMARIES),
        # What the page needs to treat a method by what it *is* rather than
        # by its name: which one is the orchestration, which partition it
        # starts from, what it needs to run. A new partition method needs
        # nothing here; the page reads its capabilities like any other's.
        "methodMeta": registry.meta(),
        "generator": "amsc.viewer.build",
    }
    payload = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).replace("</", "<\\/")

    document = TEMPLATE.replace("__VIEWER_DATA__", payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    if write_catalog:
        index = catalog(docs, benchmarks, deep, Path(root), generator="amsc.viewer.build")
        (output.parent / "catalog.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return output


def _parse_specs(parser: argparse.ArgumentParser, specs: Sequence[str], flag: str) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for spec in specs:
        if "=" not in spec:
            parser.error(f"{flag} expects DOC=DIR, got {spec!r}")
        doc, _, path = spec.partition("=")
        out[doc.strip()] = Path(path.strip())
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.viewer.build",
        description="Build the Viewer v3 product page from completed artifact trees",
    )
    parser.add_argument("--benchmark", action="append", default=[], metavar="DOC=DIR")
    parser.add_argument("--deep", action="append", default=[], metavar="DOC=DIR")
    parser.add_argument("--label", action="append", default=[], metavar="DOC=LABEL")
    parser.add_argument("--output", type=Path, default=Path("artifacts/viewer-v3/index.html"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--no-catalog", action="store_true")
    args = parser.parse_args(argv)

    benchmarks = _parse_specs(parser, args.benchmark, "--benchmark")
    deep = _parse_specs(parser, args.deep, "--deep")
    labels = {
        doc: label
        for doc, label in (
            (spec.partition("=")[0].strip(), spec.partition("=")[2].strip()) for spec in args.label
        )
    }
    path = build_viewer(
        benchmarks,
        args.output,
        root=args.root,
        deep=deep,
        labels=labels,
        write_catalog=not args.no_catalog,
    )
    # The count is reported because zero is a meaningful, and easily
    # unintended, answer: it is the product shell rather than a failed build.
    embedded = len(set(benchmarks) | set(deep))
    print(json.dumps({"written": str(path), "embedded_documents": embedded}, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
