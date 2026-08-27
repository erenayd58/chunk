"""Structural QA: flag suspicious parser and section attribution on a corpus.

Reading a few hundred chunks by hand is how the reading-order, running-header
and lead-in defects were each found, one at a time. This module does that sweep
mechanically so only flagged cases need a human.

It is **diagnostic only**. Nothing here changes the parser, the chunker or the
retrieval path; it reads a canonical ``.units.jsonl`` and the ``chunks`` a
chunker produced from it and reports what looks wrong.

Rules, all text-agnostic -- no document, heading or page is matched by name:

===========================  =============================================
``body_heading``             a numbered or all-caps title sitting inside a
                             paragraph or table, with no section to match
``chunk_heading_mismatch``   a chunk whose body carries a title that is
                             neither its own heading nor any of its sections
``sentence_like_heading``    a heading that reads as a sentence or clause
``section_inconsistency``    the section state machine and the heading
                             stream disagree -- a heading that opens a section
                             is not the tail of its own path, or the path moved
                             where nothing opened a section
``running_header``           the same heading leads a logical page on
                             several distinct physical pages
``unresolved_visual``        a picture unit with an unpaired label/value
                             grid, or one attributed across a spread
===========================  =============================================

Confidence is HIGH when the finding is almost certainly a defect, MEDIUM when
it needs a look, LOW when it is a known-benign pattern worth keeping visible.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Iterable, Sequence

HIGH, MEDIUM, LOW = "HIGH", "MEDIUM", "LOW"
_CONFIDENCE_ORDER = {HIGH: 0, MEDIUM: 1, LOW: 2}

#: A heading whose text is longer than this is prose, not a title.
MAX_HEADING_WORDS = 12
MAX_HEADING_CHARS = 90
#: A title repeated at the top of this many distinct physical pages is
#: page furniture rather than a section start.
RUNNING_HEADER_MIN_PAGES = 3

_EMPHASIS = re.compile(r"^[*_]+|[*_]+$")
_NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)[.)]\s+(\S.*)$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_DIVIDER = re.compile(r"^\s*\|(?:\s*:?-{2,}:?\s*\|)+\s*$")
_MARKUP = re.compile(r"<br\s*/?>|\|", flags=re.IGNORECASE)
_NUMERIC = re.compile(r"^[\d.,]+%?$|^%[\d.,]+$")
_CLAUSE_END = (";",)
_LABEL_END = (":",)
_SENTENCE_END = (".", "!", "?")


@dataclass(frozen=True)
class Finding:
    rule: str
    confidence: str
    target_id: str
    page: int | None
    reason: str
    evidence: str = ""

    def sort_key(self) -> tuple:
        return (
            _CONFIDENCE_ORDER.get(self.confidence, 9),
            self.rule,
            self.target_id,
            self.evidence,
        )


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    unit_count: int = 0
    chunk_count: int = 0

    def by_confidence(self) -> dict[str, list[Finding]]:
        grouped: dict[str, list[Finding]] = {HIGH: [], MEDIUM: [], LOW: []}
        for finding in self.findings:
            grouped.setdefault(finding.confidence, []).append(finding)
        return grouped

    def rule_counts(self) -> dict[str, Counter]:
        counts: dict[str, Counter] = defaultdict(Counter)
        for finding in self.findings:
            counts[finding.rule][finding.confidence] += 1
        return dict(counts)


# --------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------


def strip_emphasis(text: str) -> str:
    return _EMPHASIS.sub("", text.strip()).strip()


def upper_ratio(text: str) -> float:
    letters = [character for character in text if character.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for character in letters if character.isupper()) / len(letters)


def looks_like_title(line: str) -> tuple[str, str] | None:
    """Classify a line as a title, or return ``None``.

    Returns ``(kind, bare_text)`` where kind is ``numbered`` or ``caps``.
    """
    stripped = line.strip()
    if not stripped or _TABLE_DIVIDER.match(stripped):
        return None
    if _MARKUP.search(stripped):
        # An HTML break or a pipe means table serialization, not a title.
        return None
    bare = strip_emphasis(stripped)
    if not bare or len(bare) > MAX_HEADING_CHARS:
        return None
    words = bare.split()
    if len(words) > MAX_HEADING_WORDS:
        return None

    numbered = _NUMBERED.match(bare)
    if numbered:
        remainder = numbered.group(2)
        if remainder.rstrip().endswith(_SENTENCE_END):
            return None
        if upper_ratio(remainder) >= 0.6 or stripped != bare:
            return "numbered", bare
        return None

    if bare.rstrip().endswith(_SENTENCE_END):
        return None
    if len(words) >= 2 and upper_ratio(bare) >= 0.85:
        return "caps", bare
    return None


def candidate_lines(unit: dict) -> list[str]:
    """Lines of a unit, with table rows flattened to their cell content."""
    lines: list[str] = []
    for raw in (unit.get("text") or "").splitlines():
        if _TABLE_ROW.match(raw) and not _TABLE_DIVIDER.match(raw):
            cells = [cell.strip() for cell in raw.strip().strip("|").split("|")]
            filled = [cell for cell in cells if cell]
            # Only a row carrying a single value can be a swallowed title; a
            # real data row has several populated cells.
            if len(filled) == 1:
                lines.append(filled[0])
            continue
        lines.append(raw)
    return lines


def _page(unit: dict) -> int | None:
    source = unit.get("source") or {}
    value = source.get("page")
    return int(value) if isinstance(value, int) else None


def _normalized(text: str) -> str:
    return " ".join(strip_emphasis(text).split()).casefold()


def ends_in_abbreviation(text: str) -> bool:
    """``T. Garanti Bankasi A.S.`` ends in a full stop but is not a sentence."""
    tokens = text.split()
    if not tokens:
        return False
    return "." in tokens[-1][:-1]


# --------------------------------------------------------------------------
# rules
# --------------------------------------------------------------------------


def check_body_headings(units: Sequence[dict]) -> list[Finding]:
    """A title the layout model left inside a paragraph or table."""
    findings: list[Finding] = []
    for index, unit in enumerate(units):
        if unit.get("type") not in {"paragraph", "table"}:
            continue
        known = {_normalized(part) for part in (unit.get("section_path") or [])}
        following = units[index + 1] if index + 1 < len(units) else None
        if following is not None:
            known |= {
                _normalized(part) for part in (following.get("section_path") or [])
            }
        for position, line in enumerate(candidate_lines(unit)):
            title = looks_like_title(line)
            if title is None:
                continue
            kind, bare = title
            if _normalized(bare) in known:
                continue
            leading = position == 0
            if kind == "numbered" and leading:
                confidence = HIGH
            elif kind == "numbered" or leading:
                confidence = MEDIUM
            else:
                confidence = LOW
            findings.append(
                Finding(
                    rule="body_heading",
                    confidence=confidence,
                    target_id=str(unit.get("unit_id")),
                    page=_page(unit),
                    reason=(
                        f"{kind} title inside a {unit.get('type')} "
                        f"({'first line' if leading else f'line {position + 1}'}); "
                        "the section never changes here"
                    ),
                    evidence=bare,
                )
            )
    return findings


def check_chunk_headings(chunks: Sequence[dict]) -> list[Finding]:
    """A chunk whose body carries a title it does not claim."""
    findings: list[Finding] = []
    for chunk in chunks:
        heading = chunk.get("heading") or ""
        known = {_normalized(part) for part in str(heading).splitlines() if part.strip()}
        for path in chunk.get("section_paths") or []:
            known |= {_normalized(part) for part in path}
        known.discard("")

        body = str(chunk.get("text") or "")
        if heading and body.startswith(str(heading)):
            body = body[len(str(heading)) :]

        seen: set[str] = set()
        for line in body.splitlines():
            if _TABLE_ROW.match(line):
                # A title swallowed by a table is reported against the unit by
                # ``body_heading``, which can read the row's cells; here the
                # rows are only data.
                continue
            title = looks_like_title(line)
            if title is None:
                continue
            kind, bare = title
            key = _normalized(bare)
            if key in known or key in seen:
                continue
            seen.add(key)
            pages = chunk.get("pages") or []
            findings.append(
                Finding(
                    rule="chunk_heading_mismatch",
                    confidence=HIGH if kind == "numbered" else MEDIUM,
                    target_id=str(chunk.get("chunk_id")),
                    page=pages[0] if pages else None,
                    reason=(
                        f"body carries a {kind} title that is neither the chunk "
                        f"heading ({heading!r}) nor any of its section paths"
                    ),
                    evidence=bare,
                )
            )
    return findings


def check_sentence_like_headings(units: Sequence[dict]) -> list[Finding]:
    """A heading that reads as a sentence or an unfinished clause."""
    findings: list[Finding] = []
    for unit in units:
        if unit.get("type") != "heading":
            continue
        text = str(unit.get("text") or "")
        bare = strip_emphasis(text)
        if not bare:
            continue
        reasons: list[tuple[str, str]] = []
        if not any(character.isalpha() for character in bare):
            # ``24.`` is a section number that lost its title; a bare ``2024``
            # is a plausible label on a milestone timeline.
            numbering = bare.rstrip().endswith((".", ")"))
            reasons.append(
                (HIGH, "section numbering with no title text")
                if numbering
                else (LOW, "figures only: check this is a real label")
            )
        elif bare.endswith(_CLAUSE_END):
            reasons.append((HIGH, "ends in a semicolon: the clause is left open"))
        elif bare.endswith(".") and not ends_in_abbreviation(bare):
            reasons.append((HIGH, "ends in a full stop: this is a sentence"))
        elif bare.endswith(("?", "!")):
            reasons.append(
                (MEDIUM, "ends in sentence punctuation: may be a rhetorical title")
            )
        elif bare.endswith(_LABEL_END):
            reasons.append((LOW, "ends in a colon: usually a labelled sub-heading"))
        words = bare.split()
        if len(words) > MAX_HEADING_WORDS:
            reasons.append((MEDIUM, f"{len(words)} words: too long for a title"))
        if bare[:1].islower():
            reasons.append((MEDIUM, "starts lowercase"))
        for confidence, reason in reasons:
            findings.append(
                Finding(
                    rule="sentence_like_heading",
                    confidence=confidence,
                    target_id=str(unit.get("unit_id")),
                    page=_page(unit),
                    reason=reason,
                    evidence=bare[:MAX_HEADING_CHARS],
                )
            )
    return findings


def _opens_section(unit: dict) -> bool:
    """Whether this unit is a heading that starts a section.

    Looking like a heading and bearing hierarchy are two different claims (see
    :mod:`amsc.semantic_roles`). A canonical extracted before the role pass
    existed carries no decision, and every heading opens a section exactly as
    it always did -- which is what keeps this linter's verdict unchanged on
    those corpora.
    """
    if unit.get("type") != "heading":
        return False
    return unit.get("opens_section") is not False


def check_section_consistency(
    units: Sequence[dict], chunks: Sequence[dict]
) -> list[Finding]:
    """Disagreements between the heading stream and the section state.

    Two claims, and which one applies depends on one thing: does this unit open
    a section?

    A unit that does -- a heading bearing hierarchy -- must be the tail of its
    own path. A unit that does not must carry exactly the path of the unit
    before it. The second claim used to be made only of a body unit following
    another body unit, because every heading was assumed to open a section.
    Once ``item`` labels and ``display`` banners deliberately open nothing,
    that assumption both flags the model working correctly *and* excuses the
    unit after a label from any check at all. Reading the same predicate on
    both sides fixes both halves.
    """
    findings: list[Finding] = []
    previous: dict | None = None
    for unit in units:
        path = list(unit.get("section_path") or [])
        if _opens_section(unit):
            if not path or _normalized(path[-1]) != _normalized(
                str(unit.get("text") or "")
            ):
                findings.append(
                    Finding(
                        rule="section_inconsistency",
                        confidence=HIGH,
                        target_id=str(unit.get("unit_id")),
                        page=_page(unit),
                        reason=(
                            "a heading whose own text is not the tail of its "
                            "section path"
                        ),
                        evidence=f"{str(unit.get('text'))[:60]} -> {path}",
                    )
                )
        elif previous is not None or unit.get("type") == "heading":
            # Nothing has opened a section yet at the first unit, so the path it
            # may carry is the empty one. A body unit in that position was never
            # checked and still is not; a heading there was, and still is.
            expected = (
                list(previous.get("section_path") or []) if previous is not None else []
            )
            if path != expected:
                findings.append(
                    Finding(
                        rule="section_inconsistency",
                        confidence=HIGH,
                        target_id=str(unit.get("unit_id")),
                        page=_page(unit),
                        reason=(
                            "the section changed at a unit that opens none "
                            + (
                                f"(previous unit {previous.get('unit_id')})"
                                if previous is not None
                                else "(first unit, nothing is open yet)"
                            )
                        ),
                        evidence=f"{expected} -> {path}",
                    )
                )
        previous = unit

    for chunk in chunks:
        paths = chunk.get("section_paths") or []
        if len(paths) > 1:
            pages = chunk.get("pages") or []
            findings.append(
                Finding(
                    rule="section_inconsistency",
                    confidence=MEDIUM,
                    target_id=str(chunk.get("chunk_id")),
                    page=pages[0] if pages else None,
                    reason=f"one chunk spans {len(paths)} section paths",
                    evidence=" | ".join(" > ".join(path) for path in paths)[:120],
                )
            )
    return findings


def check_running_headers(units: Sequence[dict]) -> list[Finding]:
    """The same title leading a logical page on several physical pages."""
    seen_logical: set[tuple[Any, Any]] = set()
    leading_pages: defaultdict[str, set[int]] = defaultdict(set)
    all_pages: defaultdict[str, set[int]] = defaultdict(set)
    first_unit: dict[str, dict] = {}

    for unit in units:
        source = unit.get("source") or {}
        key = (source.get("page"), source.get("logical_page_side"))
        leads = key not in seen_logical
        seen_logical.add(key)
        if unit.get("type") != "heading":
            continue
        text = _normalized(str(unit.get("text") or ""))
        if not text:
            continue
        first_unit.setdefault(text, unit)
        page = _page(unit)
        if page is None:
            continue
        all_pages[text].add(page)
        if leads:
            leading_pages[text].add(page)

    findings: list[Finding] = []
    for text, pages in sorted(leading_pages.items()):
        if len(pages) >= RUNNING_HEADER_MIN_PAGES:
            unit = first_unit[text]
            findings.append(
                Finding(
                    rule="running_header",
                    confidence=HIGH,
                    target_id=str(unit.get("unit_id")),
                    page=_page(unit),
                    reason=(
                        f"leads a logical page on {len(pages)} distinct physical "
                        f"pages {sorted(pages)[:8]}: page furniture, not a section"
                    ),
                    evidence=str(unit.get("text"))[:MAX_HEADING_CHARS],
                )
            )
    for text, pages in sorted(all_pages.items()):
        if len(pages) >= RUNNING_HEADER_MIN_PAGES and len(leading_pages[text]) < (
            RUNNING_HEADER_MIN_PAGES
        ):
            unit = first_unit[text]
            findings.append(
                Finding(
                    rule="running_header",
                    confidence=MEDIUM,
                    target_id=str(unit.get("unit_id")),
                    page=_page(unit),
                    reason=(
                        f"the same heading text appears on {len(pages)} distinct "
                        f"pages {sorted(pages)[:8]} without leading them"
                    ),
                    evidence=str(unit.get("text"))[:MAX_HEADING_CHARS],
                )
            )
    return findings


def check_visual_units(units: Sequence[dict]) -> list[Finding]:
    """Picture units whose label/value grid was never paired up."""
    findings: list[Finding] = []
    last_heading: dict | None = None
    for unit in units:
        if unit.get("type") == "heading":
            last_heading = unit
        source = unit.get("source") or {}
        if source.get("content_origin") != "visual":
            continue

        lines = [line.strip() for line in (unit.get("text") or "").splitlines()]
        lines = [line for line in lines if line]
        numeric = [
            line
            for line in lines
            if line.split() and all(_NUMERIC.fullmatch(t) for t in line.split())
        ]
        labels = [line for line in lines if line not in numeric]
        resolved = source.get("extraction_method") == "layout_text_card_grid"

        if not resolved and len(numeric) >= 2 and len(labels) >= 2:
            balanced = abs(len(numeric) - len(labels)) <= 1
            findings.append(
                Finding(
                    rule="unresolved_visual",
                    confidence=HIGH if balanced else MEDIUM,
                    target_id=str(unit.get("unit_id")),
                    page=_page(unit),
                    reason=(
                        f"{len(labels)} label lines and {len(numeric)} value lines "
                        "with no label-to-value pairing"
                    ),
                    evidence=" / ".join(lines[:4])[:120],
                )
            )

        if last_heading is not None:
            heading_source = last_heading.get("source") or {}
            if heading_source.get("page") != source.get("page") or heading_source.get(
                "logical_page_side"
            ) != source.get("logical_page_side"):
                findings.append(
                    Finding(
                        rule="unresolved_visual",
                        confidence=MEDIUM,
                        target_id=str(unit.get("unit_id")),
                        page=_page(unit),
                        reason=(
                            "inherits a heading from another logical page "
                            f"({last_heading.get('unit_id')} on page "
                            f"{heading_source.get('page')} "
                            f"{heading_source.get('logical_page_side')})"
                        ),
                        evidence=" > ".join(unit.get("section_path") or [])[:120],
                    )
                )
    return findings


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

RULES = (
    "body_heading",
    "chunk_heading_mismatch",
    "sentence_like_heading",
    "section_inconsistency",
    "running_header",
    "unresolved_visual",
)


def lint(units: Sequence[dict], chunks: Sequence[dict]) -> Report:
    findings: list[Finding] = []
    findings += check_body_headings(units)
    findings += check_chunk_headings(chunks)
    findings += check_sentence_like_headings(units)
    findings += check_section_consistency(units, chunks)
    findings += check_running_headers(units)
    findings += check_visual_units(units)
    findings.sort(key=Finding.sort_key)
    return Report(findings=findings, unit_count=len(units), chunk_count=len(chunks))


def load_jsonl(path: str | Path) -> list[dict]:
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"File does not exist: {source}")
    rows: list[dict] = []
    with source.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def render(report: Report, *, limit: int | None = None) -> str:
    lines: list[str] = []
    lines.append(
        f"Structural QA: {report.unit_count} canonical units, "
        f"{report.chunk_count} chunks, {len(report.findings)} findings"
    )
    lines.append("")
    counts = report.rule_counts()
    lines.append(f"{'rule':26} {'HIGH':>6} {'MEDIUM':>7} {'LOW':>5}")
    lines.append("-" * 48)
    for rule in RULES:
        rule_counts = counts.get(rule, Counter())
        lines.append(
            f"{rule:26} {rule_counts[HIGH]:>6} {rule_counts[MEDIUM]:>7} "
            f"{rule_counts[LOW]:>5}"
        )
    lines.append("")

    grouped = report.by_confidence()
    for confidence in (HIGH, MEDIUM, LOW):
        bucket = grouped.get(confidence) or []
        lines.append(f"=== {confidence} ({len(bucket)}) " + "=" * 40)
        shown = bucket if limit is None else bucket[:limit]
        for finding in shown:
            page = f"p{finding.page}" if finding.page is not None else "p?"
            lines.append(f"  [{finding.rule}] {finding.target_id} {page}")
            lines.append(f"      {finding.reason}")
            if finding.evidence:
                lines.append(f"      evidence: {finding.evidence}")
        if limit is not None and len(bucket) > limit:
            lines.append(f"  ... {len(bucket) - limit} more not shown")
        lines.append("")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m amsc.structural_qa",
        description=(
            "Flag suspicious parser and section attribution across a canonical "
            "corpus and the chunks built from it. Diagnostic only."
        ),
    )
    parser.add_argument("--units", required=True, type=Path)
    parser.add_argument("--chunks", required=True, type=Path)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = lint(load_jsonl(args.units), load_jsonl(args.chunks))
    print(render(report, limit=args.limit))
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "unit_count": report.unit_count,
                    "chunk_count": report.chunk_count,
                    "findings": [asdict(finding) for finding in report.findings],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
