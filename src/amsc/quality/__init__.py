"""How good is this parse, this boundary, this set of chunks?

* :mod:`~amsc.quality.lint` -- structural QA over a canonical document and the
  chunks made from it; diagnostic, text-agnostic, parser-facing
* :mod:`~amsc.quality.boundaries` -- the deterministic boundary contract Deep
  Analysis optimises against
* :mod:`~amsc.quality.chunks` -- chunk-set quality, net of a parser baseline,
  so two chunkers over one document are comparable
* :mod:`~amsc.quality.evaluation` -- the frozen authoritative boundary and
  chunk metrics; changing a number here invalidates the benchmark record
"""
