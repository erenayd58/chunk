"""The Viewer: the read model, the page built from it, and the demo beside it.

:mod:`~amsc.viewer.corpus` is the reader every consumer of a packaged analysis
shares -- the console included. :mod:`~amsc.viewer.build` assembles the page
from that corpus and :mod:`~amsc.viewer.template` is its shell; the page reads
:mod:`amsc.chunking.registry` at request time, so a new chunking method needs
no rebuild here.

:mod:`~amsc.viewer.server` and :mod:`amsc.viewer.chat` are the standalone demo
process. It is product code, but it runs *beside* the console rather than
inside it, and the console import boundary says so.
"""
