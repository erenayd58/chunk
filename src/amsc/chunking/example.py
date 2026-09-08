"""The smallest complete chunking method -- the template for a new one.

Copy this file into ``amsc/chunking/plugins/``, change the partition, write a
test. That is the whole procedure: the file *is* the registration. Nothing in
the Viewer, the benchmark or the console has to learn the method's name, and
no central list has to be edited.

**What a chunker owes.** Two things per chunk: the text, and where the text
came from. Here that is the units it packed; a method that chunks a rendering
instead declares :attr:`Capability.OFFSETS`, asks for ``document`` and returns
``span=(start, end)`` -- see the note at the bottom. Everything else on the row
is derived by :mod:`amsc.chunking.contract`: the chunk id, the token count, the
pages, the section paths, the heading, how the units were cut. The old version
of this template built an eight-key dictionary by hand, and every copy of it
had to remember all eight.

**What a chunker declares.** ``capabilities`` says which optional fields the
rows carry. Left unsaid, it is the four the structural family has always
emitted, which is why this example says nothing about them and still produces
the rows every screen reads. Narrow it if your method genuinely has no
opinion -- a method that declares no ``HIERARCHY`` is not broken anywhere,
because every consumer of an optional field reads it defensively.

**What the framework hands you.** Only what the partition asks for by name.
This one names ``counter`` and ``budget``; a method that wants everything
writes ``**options`` and gets the boundary embedder and the rest with it.

The method here packs consecutive content units into a chunk until the next
unit would push it past the shared target, cutting only at unit boundaries and
never crossing a heading. It is deliberately naive -- a partition any reader
can predict -- so a test can hold it to a hand-computed answer. It lives here
rather than in ``plugins/`` on purpose: the template ships **unregistered**, so
the extension path can be proved by a test without leaving a fifth product
method behind. ``docs/adding-a-chunker.md`` walks through it.
"""

from __future__ import annotations

from typing import Any, Iterator, Mapping, Sequence

from .contract import Chunk, chunker
from ..document.models import RawDocumentUnit, UnitType

RENDER_SEPARATOR = "\n\n"


@chunker(
    key="fixed-window",
    kind="fixed_window",
    label="Sabit Pencere",
    summary="Ardışık birimleri sabit sayıda pencereler halinde paketler; başlıkları geçmez.",
    #: The chunk id infix, so a row says which method wrote it. Optional --
    #: without it the ids read ``doc:fixed-window-chunk-0001``.
    chunk_infix="fw-chunk",
    #: Default option values for a live run; a caller may override them.
    options={"max_units": 3},
)
def fixed_window(
    units: Sequence[RawDocumentUnit],
    *,
    counter: Any,
    budget: Mapping[str, Any],
    max_units: int = 3,
) -> Iterator[Chunk]:
    """Pack up to ``max_units`` content units per chunk, within the target.

    Headings are not chunk content (the structural family leaves them out of
    ``unit_ids`` too); they close the open chunk so a window never crosses a
    section. A unit that alone exceeds the hard maximum is emitted on its own
    rather than split: this example makes no claim about oversized units.
    """
    target = int(budget["target_tokens"])
    open_units: list[RawDocumentUnit] = []

    def close() -> Iterator[Chunk]:
        if open_units:
            yield Chunk(
                text=RENDER_SEPARATOR.join(unit.text for unit in open_units),
                unit_ids=[unit.unit_id for unit in open_units],
            )
            open_units.clear()

    for unit in units:
        if unit.type == UnitType.HEADING:
            yield from close()
            continue
        projected = counter.count(RENDER_SEPARATOR.join(u.text for u in (*open_units, unit)))
        if open_units and (len(open_units) >= max_units or projected > target):
            yield from close()
        open_units.append(unit)
    yield from close()


#: The method the decorator built, for a test that wants to register it. A
#: plugin file needs no such name: :mod:`amsc.chunking.discovery` finds the
#: method on the function.
FIXED_WINDOW = fixed_window.chunk_method

#: A method that chunks a *rendering* rather than the units declares
#: ``Capability.OFFSETS``, names ``document`` (the framework builds and hands
#: it the rendered markdown, with every unit's character range in it) and
#: returns spans instead of unit ids::
#:
#:     @chunker(key="sliding", label="Sliding",
#:              capabilities=[Capability.PAGES, Capability.OFFSETS])
#:     def sliding(units, *, document, budget):
#:         text = document.text
#:         for start in range(0, len(text), 4000):
#:             yield Chunk(text=text[start:start + 4000], span=(start, min(start + 4000, len(text))))
#:
#: The units each span covers are then intersected out of the renderer's own
#: spans -- arithmetic, not a text search, so a document that repeats a
#: paragraph still attributes each chunk to the occurrence it actually holds.
