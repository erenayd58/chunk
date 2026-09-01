"""A structured reading of a chunk's table, for the answer model.

:mod:`amsc.table_search_text` derives a representation to be *searched*; this
module derives one to be *read*. They are different problems.

A layout model can leave a report's table in a shape where the association a
reader needs -- which value belongs to which row label, under which period --
is nowhere written on a single line. One column's whole run of values ends up
inside its own header cell; the row labels end up stacked inside the label
column's header; and the data row carrying the other period's values has no
label at all. Read literally, the only label-and-value pair sharing a line is
the wrong one, and a reader files the 2024 revenue beside the 2023 deduction.

So cells are parsed with their ``<br>`` stacks kept **in order**, the row-label
sequence and each column's value sequence are recovered, and the two are paired
by position::

    1 Ocak- 31 Aralik 2024: Satis gelirleri = 3.560.086.540; Satisiadeleri(-) = (16.923.281); ...
    1 Ocak- 31 Aralik 2023: Satis gelirleri = 1.772.898.429; Satisiadeleri(-) = (6.682.818); ...

Pairing happens **only when the counts line up exactly**. Where they do not,
nothing is produced at all: a guessed pairing would file a number under a
period it does not belong to, which is the one failure this exists to prevent.
The raw markdown is never rewritten, sits in the context beside this, and stays
the only thing a citation points at.

Everything here is structural -- stacks, counts, and whether an item reads as a
number. No wording is matched, so nothing is tied to one document or report.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from .chunk_benchmark import base_unit_id
from .models import RawDocumentUnit, UnitType
from .table_search_text import (
    MAX_HEADER_ROWS,
    _clean,
    _is_numeric,
    _is_separator,
)

#: A reading aid rides in the answer context, where every character comes out
#: of the budget the evidence itself needs. Past this the table is left to
#: speak for itself.
MAX_TABLE_VIEW_CHARS = 2400

#: How the reading introduces itself wherever it is rendered. A derived
#: reading is offered as one, never as the document's own words: the raw table
#: stays above it and remains what a citation points at. One wording, so the
#: product's chat and the Viewer's cannot drift apart.
CONTEXT_HEADER = (
    "[Tablo okuması — yukarıdaki tablodan türetilmiştir, dokümanın kendi metni "
    "değildir; alıntı ve sayfa bilgisi tablonun kendisine aittir]"
)


def _cell_items(cell: str) -> list[str]:
    """One cell as the ordered items the layout model stacked into it.

    ``<br>`` is the only thing separating a column's fifth value from its
    fourth, so here it is a delimiter rather than whitespace.
    """
    return [item for item in (_clean(part) for part in cell.split("<br>")) if item]


def _stack_grid(table_text: str) -> list[list[list[str]]]:
    """Rows -> cells -> ordered items. Separators and empty rows are dropped."""
    rows: list[list[list[str]]] = []
    for line in table_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|") or len(stripped) < 2:
            continue
        raw_cells = stripped[1:-1].split("|")
        flat = [_clean(cell) for cell in raw_cells]
        if _is_separator(flat):
            continue
        # A cell spanning several columns is emitted once per column it covers;
        # only its first occurrence carries the items.
        cells: list[list[str]] = []
        previous = None
        for raw, flat_cell in zip(raw_cells, flat):
            if flat_cell and flat_cell == previous:
                cells.append([])
            else:
                cells.append(_cell_items(raw))
                previous = flat_cell or previous
        if any(cells):
            rows.append(cells)
    return rows


def _names_and_values(items: Sequence[str]) -> tuple[list[str], list[str]] | None:
    """A header cell's stack split into its name and the values stuffed below.

    A column whose values were written into its own header cell reads as name
    items followed by number items. A name appearing *after* a number is a
    shape this cannot read, and it says so rather than guessing where the
    split falls.
    """
    names: list[str] = []
    values: list[str] = []
    for item in items:
        if _is_numeric(item):
            values.append(item)
        elif values:
            return None
        else:
            names.append(item)
    return names, values


def _header_end(grid: Sequence[Sequence[Sequence[str]]], start: int) -> int:
    """Where the header stops, from ``start``.

    The first row is the header. It may itself carry a column's values, so the
    run continues only while a following row carries no number at all -- which
    is what a header broken across lines looks like, and never what data does.
    """
    end = start + 1
    while end < len(grid) and end - start < MAX_HEADER_ROWS:
        if any(_is_numeric(item) for cell in grid[end] for item in cell):
            break
        end += 1
    return end


def view_lines(table_text: str) -> list[str] | None:
    """One table as ``column: label = value; ...`` lines, or ``None``.

    ``None`` means the table's own structure did not make the pairing certain.
    """
    grid = _stack_grid(table_text)
    if not grid:
        return None

    # Leading rows with a single filled cell are the table's caption and its
    # bands, not its header.
    start = 0
    while start < len(grid) and sum(1 for cell in grid[start] if cell) == 1:
        start += 1
    if start >= len(grid):
        return None

    end = _header_end(grid, start)
    width = max(len(row) for row in grid)
    merged: list[list[str]] = [[] for _ in range(width)]
    for row in grid[start:end]:
        for column, cell in enumerate(row):
            merged[column].extend(cell)

    split: list[tuple[list[str], list[str]]] = []
    for items in merged:
        parsed = _names_and_values(items)
        if parsed is None:
            return None
        split.append(parsed)

    label_names, label_values = split[0]
    if label_values:
        # Numbers in the label column's own header: there is no label sequence
        # to recover, so there is nothing certain to say.
        return None
    value_columns = [column for column in range(1, width) if split[column][0]]
    if not value_columns:
        return None
    for column in range(1, width):
        if column not in value_columns and split[column][1]:
            return None  # values under a column with no name
    column_name = {column: " ".join(split[column][0]) for column in value_columns}
    stuffed = {column: split[column][1] for column in value_columns}

    body = grid[end:]
    labels: list[str] = []
    sequence: dict[int, list[str]] = {column: [] for column in value_columns}
    borrowed = False
    index = 0
    while index < len(body):
        row = body[index]
        row_labels = list(row[0]) if row else []
        row_values = {
            column: list(row[column]) if column < len(row) else []
            for column in value_columns
        }
        if any(not _is_numeric(value)
               for values in row_values.values() for value in values):
            return None  # a word where a value should be: not a data row
        counts = {column: len(row_values[column]) for column in value_columns}
        carrying = [column for column in value_columns if counts[column]]
        if not carrying:
            # A band label, or a row whose values are printed elsewhere. It
            # names nothing numeric, so it is passed over rather than paired.
            index += 1
            continue
        size = counts[carrying[0]]
        if any(counts[column] not in (0, size) for column in carrying):
            return None  # the columns of one row disagree on how many values

        if size == 1 and row_labels:
            # One value in the row means one label, however many lines the
            # layout model wrapped that label over.
            labels.append(" ".join(row_labels))
        elif len(row_labels) == size:
            labels.extend(row_labels)
        elif not row_labels and not borrowed and len(label_names) in (size, size + 1):
            # The row the layout model left unlabelled: its labels are the ones
            # stacked at the end of the label column's own header, in order.
            # The stack may carry the table's own name ahead of them and
            # nothing else. One leading item is a title; a second means the
            # stack holds something this cannot account for, and an
            # unaccounted-for item is exactly how a value ends up filed under
            # the label above or below its own. Anything but that fit refuses.
            labels.extend(label_names[-size:])
            borrowed = True
        elif len(row_labels) == 1 and size > 1:
            # A band header carrying its members' values, with the members
            # named on the label-only rows beneath it.
            # The whole run of label-only rows beneath it, never just the
            # first ``size`` of them: a run longer than the value count means
            # the band does not account for every member it names, and a
            # member left over is a pairing this cannot be sure of.
            members: list[str] = []
            look = index + 1
            while look < len(body):
                following = body[look]
                if any(following[column] for column in value_columns
                       if column < len(following)):
                    break
                names = list(following[0]) if following else []
                if len(names) != 1:
                    break
                members.append(names[0])
                look += 1
            if len(members) != size:
                return None
            labels.extend(members)
            for column in carrying:
                sequence[column].extend(row_values[column])
            index = look
            continue
        else:
            return None
        for column in carrying:
            sequence[column].extend(row_values[column])
        index += 1

    if not labels:
        return None

    lines: list[str] = []
    for column in value_columns:
        values = stuffed[column] or sequence[column]
        if not values:
            continue  # a named column this table left empty
        if stuffed[column] and sequence[column]:
            return None  # values in two places: which run is the column's?
        if len(values) != len(labels):
            return None  # the counts do not line up, so nothing is claimed
        pairs = "; ".join(
            f"{label} = {value}" for label, value in zip(labels, values)
        )
        lines.append(f"{column_name[column]}: {pairs}")
    return lines or None


def table_view_for(tables: Sequence[RawDocumentUnit]) -> str | None:
    """The readable form of one chunk's table, or ``None``.

    Only a chunk carrying exactly one table gets a view: with two, a line of
    ``label = value`` pairs no longer says which table it came from, and an
    unattributed number is the problem rather than the fix.
    """
    if len(tables) != 1:
        return None
    lines = view_lines(tables[0].text)
    if not lines:
        return None
    text = "\n".join(lines)
    return text if len(text) <= MAX_TABLE_VIEW_CHARS else None


def enrich_rows(
    rows: Iterable[dict[str, Any]], units: Sequence[RawDocumentUnit]
) -> int:
    """Give every chunk whose one table can be read a ``table_view``, in place.

    Returns how many rows were enriched. ``text`` is never touched: this only
    ever adds a key, and a table that could not be read with certainty simply
    does not get one.
    """
    by_id = {unit.unit_id: unit for unit in units}
    enriched = 0
    for row in rows:
        tables: dict[str, RawDocumentUnit] = {}
        for unit_id in row.get("unit_ids") or []:
            unit = by_id.get(base_unit_id(str(unit_id)))
            if unit is not None and unit.type == UnitType.TABLE:
                tables.setdefault(unit.unit_id, unit)
        if not tables:
            continue
        text = table_view_for(list(tables.values()))
        if text:
            row["table_view"] = text
            enriched += 1
    return enriched
