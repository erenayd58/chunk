"""Maintained research and evaluation. Real callers, real value, off the product path.

Nothing a console or a Viewer request touches may import anything in here --
:mod:`amsc.surface` declares that and ``tests/unit/test_library_surface.py``
enforces it against the real import graph. These modules are runnable, tested
and frozen where a published number depends on them; they are simply not the
product.

The evidence they produced -- ``artifacts/``, ``evaluation/``, ``data/`` and
the goldens under ``tests/fixtures/`` -- is checked in and load-bearing. Do
not regenerate it to make a test pass.
"""
