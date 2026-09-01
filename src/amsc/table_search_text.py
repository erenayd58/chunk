"""A retrieval representation for the chunks that carry a table.

A table reaches a chunk as the markdown the layout model produced, and that
markdown is what both retrieval legs see. On a real report it looks like this::

    |**A5**|**A5**|**Kurumsal kapasiteyi gelistirmek.**|**Kurumsal kapa...
    |||||||
    |**Performans Gostergesi**||**(2023) Baslangic**|<br>**Hedeflenen De...
    ||**Hedefe**|||||

Merged cells repeat their value across every column they span, a header is
split over several rows, empty cells are kept as ``|||||||``, and ``<br>``
sits inside the text. There is almost nothing for BM25 to match and almost no
meaning for an embedding to carry, which is why a table answers questions it
plainly contains only when the question happens to quote it.

So a second representation is derived here, deterministically:

    Bolum: Insan Kaynaklari
    Tablo: Personelin ogrenim durumu
    Sutunlar: Ogrenim durumu, Kisi, Oran (%)
    Lisans: Kisi = 212; Oran (%) = 77
    Yuksek lisans: Kisi = 41; Oran (%) = 15

It exists **only** to be searched. The raw markdown stays in ``text``, which is
what the answer model reads and what a citation points at, so nothing here can
change an answer's wording or its provenance -- only whether the chunk is
found in the first place.

Everything is structural: rows, cells, and whether a cell reads as a number.
No wording is matched, so nothing here is tied to one document or one report.
The parse is deliberately forgiving -- a table it cannot read well still
yields its labels and values, which is already far more than the pipes were
giving retrieval.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from .chunk_benchmark import base_unit_id
from .models import RawDocumentUnit, UnitType

#: Retrieval-only text is still text: a runaway table would crowd the index
#: and, on the dense leg, dilute the very vector it is meant to sharpen.
MAX_SEARCH_TEXT_CHARS = 1800
#: A header that keeps growing is a table the parse has misread.
MAX_HEADER_ROWS = 4
#: A column name is a short noun phrase. A report's plan tables are laid out
#: as forms, where a whole sentence is merged across every column; read as a
#: header it would be repeated onto every row below it and swamp the index.
#: Past this width the column is treated as having no name, and its values are
#: kept on their own -- which is what a form's label/value rows want anyway.
#: The text itself is still header text the document printed, so it is kept on
#: a line of its own: only the repetition is refused, never the words.
MAX_HEADER_CHARS = 60

_EMPHASIS = re.compile(r"[*_]{1,3}")
_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")
_LEADERS = re.compile(r"[.…]{3,}")
#: One number as a cell writes it -- "4,3", "%122,8", "212" -- and the
#: parenthesised negative an accounting table uses for a deduction.
_NUMBER = r"[%+-]?\d[\d.,]*%?|\(\s*[%+-]?\d[\d.,]*%?\s*\)"
#: A cell that *is* value(s), rather than one that merely contains a digit. A
#: layout model joins a column's numbers into one cell, so a whitespace-
#: separated run of them is still data: "3.560.086.540 (16.923.281)" is one
#: column of a two-line row, not a column name. "(2023) Baslangic" stays a
#: label, because a cell is data only when *every* token in it is a number.
_NUMERIC_CELL = re.compile(rf"^(?:{_NUMBER})(?:\s+(?:{_NUMBER}))*$")


def _clean(cell: str) -> str:
    """One cell's text, with the serialisation taken off."""
    text = cell.replace("<br>", " ").replace("&nbsp;", " ")
    text = _EMPHASIS.sub("", text)
    # Leader dots join a label to its page number in a contents table; they
    # are typography, and left in they dominate the row.
    text = _LEADERS.sub(" ", text)
    return " ".join(text.split())


def _is_numeric(cell: str) -> bool:
    return bool(_NUMERIC_CELL.match(cell.strip()))


def _row_cells(line: str) -> list[str] | None:
    """The cells of one markdown table row, or ``None`` if it is not one."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|") or len(stripped) < 2:
        return None
    return [_clean(cell) for cell in stripped[1:-1].split("|")]


def _is_separator(cells: Sequence[str]) -> bool:
    filled = [cell for cell in cells if cell]
    return bool(filled) and all(_SEPARATOR_CELL.match(cell) for cell in filled)


def _dedupe_spans(cells: Sequence[str]) -> list[str]:
    """Collapse a merged cell back to one occurrence.

    A cell spanning several columns is emitted once per column it covers, so
    a repeated neighbour is a span rather than a repeated value. Only
    *consecutive* repeats are collapsed, and the emptied columns are kept so
    the row still lines up with the header.
    """
    out: list[str] = []
    previous = None
    for cell in cells:
        if cell and cell == previous:
            out.append("")
        else:
            out.append(cell)
            previous = cell or previous
    return out


def _grid(table_text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in table_text.splitlines():
        cells = _row_cells(line)
        if cells is None or _is_separator(cells):
            continue
        cells = _dedupe_spans(cells)
        if any(cells):
            rows.append(cells)
    return rows


def _filled(cells: Sequence[str]) -> list[tuple[int, str]]:
    return [(index, cell) for index, cell in enumerate(cells) if cell]


def _headers(
    rows: Sequence[Sequence[str]], start: int
) -> tuple[dict[int, str], list[str], int]:
    """Column names, read down as many rows as the header is split over.

    A header row is one with no value in it. The run stops at the first row
    that carries a number, because that row is data -- which is also what
    makes this work on a header the layout model broke across four lines.

    A name too long to be a column name is not a name, but it is still text
    the document printed in its header -- most often a label column whose row
    labels the layout model merged into one cell. It is returned separately,
    to be kept on a line of its own: repeated onto every row it would swamp
    the index, dropped it would take with it the words the table names its
    own rows with.
    """
    merged: dict[int, list[str]] = {}
    index = start
    while index < len(rows) and index - start < MAX_HEADER_ROWS:
        cells = rows[index]
        if any(_is_numeric(cell) for cell in cells if cell):
            break
        for column, cell in _filled(cells):
            merged.setdefault(column, []).append(cell)
        index += 1
    headers: dict[int, str] = {}
    oversized: list[str] = []
    for column, parts in sorted(merged.items()):
        name = " ".join(parts)
        if not name:
            continue
        if len(name) <= MAX_HEADER_CHARS:
            headers[column] = name
        else:
            oversized.append(name)
    return headers, oversized, index


def _table_lines(table_text: str) -> list[str]:
    rows = _grid(table_text)
    if not rows:
        return []

    lines: list[str] = []
    # A row with a single filled cell is a caption or a band label -- the
    # shape a table's own title takes when the layout model keeps it inside
    # the table. The first is the title; the rest name the bands below them.
    body_start = 0
    captions: list[str] = []
    for index, cells in enumerate(rows):
        filled = _filled(cells)
        if len(filled) != 1:
            body_start = index
            break
        captions.append(filled[0][1])
        body_start = index + 1
    if captions:
        lines.append("Tablo: " + captions[0])
        if len(captions) > 1:
            lines.append("Bant: " + ", ".join(captions[1:]))

    headers, oversized, data_start = _headers(rows, body_start)
    if headers:
        lines.append("Sutunlar: " + ", ".join(
            headers[column] for column in sorted(headers) if headers[column]))
    for name in oversized:
        # Header text too long to name a column: kept whole, and kept once.
        lines.append("Basliklar: " + name)

    for cells in rows[data_start:]:
        filled = _filled(cells)
        if not filled:
            continue
        if len(filled) == 1:
            column, value = filled[0]
            if _is_numeric(value):
                # A row the layout model left no label in: the value belongs to
                # its own column, not to a band it does not name.
                header = headers.get(column)
                lines.append(f"{header}: {value}" if header else value)
                continue
            # A band label between data rows: it names what follows, so it is
            # kept on its own line rather than becoming a label with no value.
            lines.append(value + ":")
            continue
        label = filled[0][1]
        pairs = []
        for column, value in filled[1:]:
            header = headers.get(column)
            pairs.append(f"{header} = {value}" if header else value)
        lines.append(f"{label}: " + "; ".join(pairs))
    return lines


def _reliable_context(row: Mapping[str, Any]) -> list[str]:
    """The chunk's own heading and section path, when they can be trusted.

    A caption printed above a table is set apart typographically, so a layout
    model can report it as a section header and the section state machine then
    names a section after a value -- a path like ``['%100']``. A name that is
    only a number names nothing, so it is dropped rather than searched on.
    """
    def usable(text: Any) -> str | None:
        cleaned = _clean(str(text or ""))
        if len(cleaned) < 3 or _is_numeric(cleaned):
            return None
        return cleaned

    lines: list[str] = []
    paths = row.get("section_paths") or []
    path = [name for name in (usable(part) for part in (paths[0] if paths else [])) if name]
    if path:
        lines.append("Bolum: " + " > ".join(path))
    heading = usable(row.get("heading"))
    if heading and heading not in path:
        lines.append("Baslik: " + heading)
    return lines


def search_text_for(row: Mapping[str, Any], tables: Sequence[RawDocumentUnit]) -> str | None:
    """The searchable form of one chunk's tables, or ``None`` if there is none."""
    lines = _reliable_context(row)
    for table in tables:
        lines.extend(_table_lines(table.text))
    if not lines:
        return None
    text = "\n".join(lines)
    if len(text) > MAX_SEARCH_TEXT_CHARS:
        # Cut at a line, never mid-value: half a label/value pair would put a
        # number in the index under no category at all.
        kept: list[str] = []
        budget = MAX_SEARCH_TEXT_CHARS
        for line in lines:
            if len(line) + 1 > budget:
                break
            kept.append(line)
            budget -= len(line) + 1
        text = "\n".join(kept)
    return text or None


def enrich_rows(
    rows: Iterable[dict[str, Any]], units: Sequence[RawDocumentUnit]
) -> int:
    """Give every chunk that carries a table a ``search_text``, in place.

    Returns how many rows were enriched. A chunk with no table is left exactly
    as it was, and ``text`` is never touched: this only ever adds a key.
    """
    by_id = {unit.unit_id: unit for unit in units}
    enriched = 0
    for row in rows:
        tables: dict[str, RawDocumentUnit] = {}
        for unit_id in row.get("unit_ids") or []:
            unit = by_id.get(base_unit_id(str(unit_id)))
            # A table split across fragments reaches the chunk as several
            # ids of one unit; it is still one table and is rendered once.
            if unit is not None and unit.type == UnitType.TABLE:
                tables.setdefault(unit.unit_id, unit)
        if not tables:
            continue
        text = search_text_for(row, list(tables.values()))
        if text:
            row["search_text"] = text
            enriched += 1
    return enriched
