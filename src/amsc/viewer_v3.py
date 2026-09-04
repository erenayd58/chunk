"""Viewer v3 -- the chunking inspection product page.

A separate product experience over the same data Viewer v2 reads: the same
``load_corpus`` payloads, the same catalog writer, the same server and the
same live-workspace endpoints. This module is a second **pure reader** with
its own template -- it changes nothing in Viewer v2, the pipeline or any API.

The page answers one question before all others: *where does a chunk start,
where does it end, and how do two methods cut the same content differently?*
Everything else (ids, strategies, decision records) is behind progressive
disclosure.

Build and serve (the existing server takes any viewer path; Viewer v2 keeps
its own build untouched). With no trees at all it builds the product shell --
a page that carries no corpus of its own and reads every document from the
RAG console at runtime, which is the only build a fresh clone can make,
because the frozen research trees are not in version control:

    py -3.11 -m amsc.viewer_v3 --output artifacts/viewer-v3/index.html

Adding trees embeds them, which is what the research build does:

    py -3.11 -m amsc.viewer_v3 `
      --benchmark kkb-2024=artifacts/chunk-benchmark-v5/kkb-2024 `
      --deep kkb-2024=artifacts/deep-analysis/kkb-2024-final `
      --output artifacts/viewer-v3/index.html

    py -3.11 -m amsc.viewer_server --viewer artifacts/viewer-v3/index.html --config configs/rag-poc.yaml

Opened as a file, the page shows the embedded corpus; served, it also lists
the RAG console's knowledge bases through the server's existing
``/api/workspace`` and ``/api/live-document`` relays.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

from .viewer_v2 import _catalog, load_corpus
from .viewer_v3_template import TEMPLATE

#: Product order and product names -- one name per method, everywhere.
METHOD_ORDER = ("markdown", "hybrid", "structure-only", "agentic")
METHOD_LABELS = {
    "markdown": "Markdown",
    "hybrid": "Hybrid",
    "structure-only": "Standard",
    "agentic": "Deep Analysis",
}
#: One sentence per method, for the picker. Presence in a document is always
#: read from the document's own arms; these sentences only describe a method
#: that is actually there.
METHOD_SUMMARIES = {
    "markdown": "Metni sabit boyutta keser; bölüm yapısına bakmaz.",
    "hybrid": "Yapıyı takip eder; bütçeyi aşan bölümlerde kesim yerini anlam benzerliğiyle seçer.",
    "structure-only": "Dokümanın başlık yapısını takip eder; yalnız çok büyüyen bölümler bölünür.",
    "agentic": "Standard'ın bıraktığı kötü sınırları arar ve düzeltir; kararsız yerlerde modele danışır.",
}


def build_viewer(
    benchmarks: Mapping[str, Path],
    output: Path,
    root: Path = Path("."),
    deep: Mapping[str, Path] | None = None,
    labels: Mapping[str, str] | None = None,
    write_catalog: bool = True,
) -> Path:
    """Build the single-file Viewer v3 for the given trees.

    Same inputs as the v2 build (minus the research-only ``--agentic`` slot):
    ``benchmarks`` maps a document id to a frozen chunk-benchmark tree,
    ``deep`` to a packaged Deep Analysis tree. Both may be empty, which builds
    the product shell: no embedded corpus, every document read live from the
    console. The per-document payload is
    exactly ``viewer_v2.load_corpus`` output, so a live document fetched at
    runtime through ``/api/live-document`` has the same shape as an embedded
    one and the page needs no second reader.
    """
    deep = dict(deep or {})
    labels = dict(labels or {})
    documents = list(benchmarks) + [doc for doc in deep if doc not in benchmarks]
    # No documents is a legitimate build, and the only one a clean checkout can
    # make: the frozen benchmark and Deep trees are git-ignored research output
    # that cannot be committed, so requiring one of them left the product's own
    # page buildable on exactly one machine. Nothing the page needs for a live
    # document comes from an embedded one -- the method order, labels and
    # summaries below are build-time constants, and every corpus-driven view
    # reads ``DATA.docOrder``, which is then simply empty. Served, the page
    # lists the console's knowledge bases and fetches their payloads over the
    # server's existing relays, which is what the product uses it for.
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
        "methodLabels": METHOD_LABELS,
        "methodSummaries": METHOD_SUMMARIES,
        "generator": "amsc.viewer_v3",
    }
    payload = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).replace("</", "<\\/")

    document = TEMPLATE.replace("__VIEWER_DATA__", payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    if write_catalog:
        catalog = _catalog(docs, benchmarks, deep, {}, Path(root))
        catalog["generator"] = "amsc.viewer_v3"
        (output.parent / "catalog.json").write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
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
        prog="python -m amsc.viewer_v3",
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
