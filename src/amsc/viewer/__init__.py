"""The Viewer: the shared read model, the page built from it, and the engine.

:mod:`~amsc.viewer.corpus` is the reader every consumer of a packaged analysis
shares -- the RAG console included, which is what keeps one payload shape
across both repositories.

:mod:`~amsc.viewer.build` assembles *this repository's* page from that corpus,
over its frozen benchmark trees, and :mod:`~amsc.viewer.template` is its shell.
It reads :mod:`amsc.chunking.registry` at build time, so a method registered
here is in the next build with no list to edit.

:mod:`amsc.viewer.chat` is the retrieval engine behind the Viewer's *Sorgu* --
one question, one document, several chunking methods at once. The console runs
it in process (it is console API), which is what a comparison of chunkers needs
and what no knowledge-base query can do.

There was a fourth: ``amsc.viewer.server``, an HTTP server on ``:8765`` that
served the page, ran that engine and relayed the console for a live document.
The Viewer became a screen of the console over ``/api/v1``, and Step 13 removed
the relay it called and the server with it.
"""
