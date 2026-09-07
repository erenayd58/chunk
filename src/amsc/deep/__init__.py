"""Deep Analysis: an orchestration, not a partition function.

A Deep run is the Standard partition as a baseline, then a proposer, a
deterministic selector, a double-order verifier, table enrichment, a status
and a report, and a deterministic fallback. That is why it is a package of its
own rather than one more module in :mod:`amsc.chunking`, and why
``amsc.chunking.registry.partition`` refuses it by name.

* :mod:`~amsc.deep.selector` -- the deterministic quality-driven selector and
  ``DeepConfig``, the objective everything else serves
* :mod:`~amsc.deep.proposer` / :mod:`~amsc.deep.verifier` -- where a model is
  consulted, and how its answer is checked in both orders
* :mod:`~amsc.deep.pipeline` -- ``chunk_document``, the production entry point
* :mod:`~amsc.deep.arm` / :mod:`~amsc.deep.run` -- packaging a finished run as
  a Viewer arm and as a directory tree
"""
