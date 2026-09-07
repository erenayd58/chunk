"""Boundary embedding: the sentence vectors a chunker cut decision uses.

Retrieval embedding is a **separate interface with a separate cache
namespace** and lives in :mod:`amsc.retrieval.embeddings`. Nothing here may
import it and nothing there may import this: a retrieval evaluator that reached
into the boundary embedder would silently share a cache with the chunker it is
supposed to be measuring.
"""
