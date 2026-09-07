"""PDF in, canonical document out.

:mod:`~amsc.canonical.adapter` turns a pymupdf4llm parse into
``RawDocumentUnit`` rows, :mod:`~amsc.canonical.layout` and
:mod:`~amsc.canonical.grid` supply the page-geometry and reading-order
knowledge it needs, and :mod:`~amsc.canonical.prepare` composes the whole
document run -- the adapter followed by every repair in
:mod:`amsc.canonical.refine`.

Preparing a *research corpus* (selected pages, QA previews) is a different
job and lives in :mod:`amsc.research.corpus`.
"""
