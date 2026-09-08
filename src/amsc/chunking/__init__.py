"""The chunking methods, the contract they satisfy, and the one registry that names them.

Four modules make the extension path, and they are layered so a method can
import what it needs without the registry importing itself:

* :mod:`~amsc.chunking.method` -- the types (``ChunkMethod``, ``Capability``,
  ``PartitionResult``). A leaf: it imports nothing, which is what lets a
  method import it and the registry import the method.
* :mod:`~amsc.chunking.contract` -- what a chunker owes and what the framework
  derives: ``Chunk``, the ``@chunker`` decorator, the normalisation that turns
  chunks into rows, and the one validation every method's rows pass through.
* :mod:`~amsc.chunking.discovery` -- imports ``plugins/`` and collects what it
  declares.
* :mod:`~amsc.chunking.registry` -- the single authoritative list: the Viewer,
  the console, the benchmark and the packager all read it.

**Adding a method is adding a file** to :mod:`amsc.chunking.plugins` (copy
:mod:`~amsc.chunking.example`, the unregistered template) and writing a test.
The engines behind the shipped methods -- :mod:`~amsc.chunking.markdown`,
:mod:`~amsc.chunking.structural`, :mod:`~amsc.chunking.hybrid` -- live here
rather than in ``plugins/`` because they are frozen benchmark code that the
research modules also import; each has a thin declaration in the plugin
directory.

Deep Analysis is registered but does not live here: it is an orchestration
over a baseline partition, and it lives in :mod:`amsc.deep`.
:mod:`amsc.chunking.adaptive` is the frozen V1-V4 research lineage, which
predates the registry and is not part of it.
"""
