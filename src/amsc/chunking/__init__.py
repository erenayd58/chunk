"""The chunking methods, and the one registry that names them.

:mod:`~amsc.chunking.method` holds the types a method module needs and imports
nothing, so a method can import it and :mod:`~amsc.chunking.registry` can
import the method. The registry is the single authoritative list: the Viewer,
the console, the benchmark and the packager all read it.

Adding a normal method means writing a module beside
:mod:`~amsc.chunking.markdown`, :mod:`~amsc.chunking.structural` and
:mod:`~amsc.chunking.hybrid` (copy :mod:`~amsc.chunking.example`), listing its
``ChunkMethod`` in the registry, and writing a test.

Deep Analysis is registered here but does not live here: it is an
orchestration over a baseline partition, and it lives in :mod:`amsc.deep`.
:mod:`amsc.chunking.adaptive` is the frozen V1-V4 research lineage, which
predates the registry and is not part of it.
"""
