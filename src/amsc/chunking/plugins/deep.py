"""Deep Analysis: the one registered method that is not a partition.

It is an orchestration -- the Standard partition as a baseline, a proposer, a
deterministic selector, a double-order verifier, a status and report, table
enrichment, and a deterministic fallback -- living in :mod:`amsc.deep.pipeline`
and packaged by :mod:`amsc.deep.arm`. The registry *describes* it so every
layer can list it and tell it apart, and refuses to run it as a partition.

It declares ``CUSTOM_METADATA`` because its rows genuinely carry more than the
structural family's: a rendered ``search_text`` and ``table_view`` for the
tables it could read with certainty, which the console persists and the answer
model reads. Those are method-specific fields, and the declaration is what
says so out loud.
"""

from __future__ import annotations

from ..contract import Capability
from ..method import DEEP_KIND, ChunkMethod
# The module, not the method: importing the ``ChunkMethod`` itself would make
# this file look like a second declaration of Standard to the plugin loader.
from . import standard

DEEP = ChunkMethod(
    key="agentic",
    kind=DEEP_KIND,
    label="Deep Analysis",
    summary="Standard'ın bıraktığı kötü sınırları arar ve düzeltir; kararsız yerlerde modele danışır.",
    capabilities=[
        Capability.PAGES,
        Capability.HEADINGS,
        Capability.HIERARCHY,
        Capability.PROVENANCE,
        Capability.CUSTOM_METADATA,
    ],
    order=40,
    chunk_infix="d-chunk",
    deep=True,
    baseline=standard.STANDARD.key,
    uses_model=True,
    arbitrated_cuts=True,
)
