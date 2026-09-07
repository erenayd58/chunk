"""The canonical document: what goes in, what comes out, how both are measured.

:mod:`~amsc.document.models` is the whole data contract -- the canonical
``RawDocumentUnit`` a parser emits and the ``ChunkingResult`` a chunker
returns, one connected Pydantic graph. :mod:`~amsc.document.io` reads and
writes those on disk, :mod:`~amsc.document.tokenization` counts their tokens.

Nothing here imports another ``amsc`` package: this is the bottom of the
dependency graph, and every other package sits on it.
"""
