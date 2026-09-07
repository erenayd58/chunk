"""The per-signal repairs :mod:`amsc.canonical.prepare` composes, in order.

Each module here fixes one class of parser defect on an already-adapted unit
stream -- heading levels, lead-in headings, numbered headings, running
headers, sentence-shaped headings, over-joined headings, semantic roles,
table captions. Each is independently testable, each takes units and returns
units, and none knows about the others.
"""
