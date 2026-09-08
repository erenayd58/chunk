"""The plugin directory: one ``.py`` file per chunking method.

A file dropped here is a chunking method. :mod:`amsc.chunking.discovery`
imports every module in this package and registers every
:class:`~amsc.chunking.method.ChunkMethod` it declares, so nothing has to be
added to a list, imported anywhere, or named in a config. The Viewer, the
console, the packager and the benchmark all read the registry, so they all see
it at once.

Writing one::

    # amsc/chunking/plugins/semantic_v2.py
    from ..contract import Capability, Chunk, chunker

    @chunker(key="semantic-v2", label="Semantic V2",
             summary="...", capabilities=[Capability.PAGES, Capability.HEADINGS])
    def semantic_v2(units, *, counter, budget, **options):
        return [Chunk(text=..., unit_ids=[...]), ...]

:mod:`amsc.chunking.example` is the complete, copyable version, and
``docs/adding-a-chunker.md`` walks through it. The four modules already here
are the shipped methods: each is a thin declaration over an engine that lives
in :mod:`amsc.chunking` or :mod:`amsc.deep`, because the engines are frozen
benchmark code and the declaration is what the registry needs.

A module whose name starts with ``_`` is skipped, so a shared helper can live
here without being mistaken for a method.
"""
