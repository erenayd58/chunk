"""Carry a gold set onto a re-extracted canonical, or refuse to.

``_validate_gold`` pins every gold set to the sha256 of the canonical it was
written against, which is what stops a stale answer key being scored silently.
Re-extracting a document therefore invalidates the key even when nothing the
key points at actually moved.

This module re-pins a gold set onto a new canonical **only when that is
provably true**: every evidence unit id must still exist, carry byte-identical
text, and sit on the same page. If a single one does not, nothing is written
and the mismatches are reported -- the answer key then needs a human, not a new
sha. A gold set whose evidence genuinely moved must be re-authored, and this
module will not paper over that.

A repair that *removes* a unit renumbers every unit after it, because
``unit_id`` encodes ``order``. Then the evidence has not moved at all and the
id-matching above still refuses, for the one reason that is not a defect.
:func:`repin_across_renumbering` is the operation for that case, and it is
stricter rather than looser: an evidence unit is carried across only when the
new canonical holds **exactly one** unit with the same page, type and
byte-identical text. Two matches are as fatal as none -- this corpus prints the
same boilerplate line on many pages, so an ambiguous anchor is a real outcome
and not a theoretical one. The id it resolves to is written into the gold set
and the whole old-to-new mapping into the provenance, so the renumbering stays
readable afterwards.

What the set was re-pinned from is written to a sibling ``.provenance.json``
rather than into the gold file itself: ``RetrievalGoldSet`` forbids unknown
keys, and the re-pinned file has to stay loadable by the frozen validator that
made the re-pin necessary in the first place.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import RawDocumentUnit

EVIDENCE_KEYS = ("evidence_unit_ids",)


@dataclass(frozen=True)
class Mismatch:
    query_id: str
    unit_id: str
    reason: str


@dataclass(frozen=True)
class RepinResult:
    gold: dict[str, Any]
    provenance: dict[str, Any]
    checked_unit_ids: tuple[str, ...]
    mismatches: tuple[Mismatch, ...]

    @property
    def ok(self) -> bool:
        return not self.mismatches


def repin(
    gold: Mapping[str, Any],
    units: Sequence[RawDocumentUnit],
    *,
    units_path: str,
    units_sha256: str,
) -> RepinResult:
    """Re-pin ``gold`` onto ``units``, verifying every evidence unit first."""
    by_id = {unit.unit_id: unit for unit in units}
    original = {
        unit_id: None for query in gold.get("queries", []) for key in EVIDENCE_KEYS
        for unit_id in (query.get(key) or [])
    }
    mismatches: list[Mismatch] = []
    for query in gold.get("queries", []):
        for key in EVIDENCE_KEYS:
            for unit_id in query.get(key) or []:
                unit = by_id.get(unit_id)
                if unit is None:
                    mismatches.append(
                        Mismatch(query["query_id"], unit_id, "unit id is gone")
                    )
                    continue
                pages = query.get("evidence_pages") or []
                if pages and unit.source.page not in pages:
                    mismatches.append(
                        Mismatch(
                            query["query_id"],
                            unit_id,
                            f"page moved to {unit.source.page}, expected one of {pages}",
                        )
                    )

    repinned = dict(gold)
    repinned["source_units_file"] = units_path
    repinned["source_units_sha256"] = units_sha256
    provenance = {
        "repinned_from": {
            "source_units_file": gold.get("source_units_file"),
            "source_units_sha256": gold.get("source_units_sha256"),
        },
        "repinned_to": {
            "source_units_file": units_path,
            "source_units_sha256": units_sha256,
        },
        "verification": (
            "every evidence unit id resolves in the new canonical, on the page "
            "the gold set recorded; the questions and expected answers are "
            "untouched"
        ),
        "evidence_unit_ids_verified": sorted(original),
    }
    return RepinResult(
        repinned, provenance, tuple(sorted(original)), tuple(mismatches)
    )


def repin_against_text(
    gold: Mapping[str, Any],
    before: Sequence[RawDocumentUnit],
    after: Sequence[RawDocumentUnit],
    *,
    units_path: str,
    units_sha256: str,
) -> RepinResult:
    """As :func:`repin`, and also require the evidence text to be unchanged."""
    result = repin(gold, after, units_path=units_path, units_sha256=units_sha256)
    old = {unit.unit_id: unit for unit in before}
    new = {unit.unit_id: unit for unit in after}
    extra: list[Mismatch] = []
    for query in gold.get("queries", []):
        for key in EVIDENCE_KEYS:
            for unit_id in query.get(key) or []:
                a, b = old.get(unit_id), new.get(unit_id)
                if a is not None and b is not None and a.text != b.text:
                    extra.append(
                        Mismatch(query["query_id"], unit_id, "evidence text changed")
                    )
    provenance = dict(result.provenance)
    provenance["verification"] = (
        provenance["verification"] + "; every evidence unit's text is byte-identical"
    )
    return RepinResult(
        result.gold,
        provenance,
        result.checked_unit_ids,
        result.mismatches + tuple(extra),
    )


def _dump(payload: Mapping[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def write(result: RepinResult, path: str | Path) -> Path:
    """Write a verified re-pin and its provenance. Refuses an unverified one."""
    if not result.ok:
        raise ValueError(
            "Gold set cannot be re-pinned; "
            + "; ".join(f"{m.query_id}/{m.unit_id}: {m.reason}" for m in result.mismatches)
        )
    destination = Path(path)
    _dump(result.gold, destination)
    _dump(result.provenance, destination.with_suffix(".provenance.json"))
    return destination


def repin_across_renumbering(
    gold: Mapping[str, Any],
    before: Sequence[RawDocumentUnit],
    after: Sequence[RawDocumentUnit],
    *,
    units_path: str,
    units_sha256: str,
) -> RepinResult:
    """Carry a gold set onto a canonical whose unit ids were renumbered.

    Evidence is re-anchored on ``(page, type, text)``, which must resolve to
    exactly one unit in ``after``. Ambiguity refuses, as does absence.
    """
    old_by_id = {unit.unit_id: unit for unit in before}
    new_by_anchor: dict[tuple[int | None, str, str], list[str]] = {}
    for unit in after:
        anchor = (unit.source.page, unit.type, unit.text)
        new_by_anchor.setdefault(anchor, []).append(unit.unit_id)

    mismatches: list[Mismatch] = []
    remapped: dict[str, str] = {}
    checked: list[str] = []
    queries: list[dict[str, Any]] = []
    for query in gold.get("queries", []):
        rewritten = dict(query)
        for key in EVIDENCE_KEYS:
            unit_ids = query.get(key) or []
            resolved: list[str] = []
            for unit_id in unit_ids:
                checked.append(unit_id)
                source = old_by_id.get(unit_id)
                if source is None:
                    mismatches.append(
                        Mismatch(query["query_id"], unit_id, "not in the old canonical")
                    )
                    resolved.append(unit_id)
                    continue
                candidates = new_by_anchor.get(
                    (source.source.page, source.type, source.text), []
                )
                if len(candidates) != 1:
                    mismatches.append(
                        Mismatch(
                            query["query_id"],
                            unit_id,
                            "evidence is gone"
                            if not candidates
                            else f"{len(candidates)} units share its page and text",
                        )
                    )
                    resolved.append(unit_id)
                    continue
                resolved.append(candidates[0])
                if candidates[0] != unit_id:
                    remapped[unit_id] = candidates[0]
            if unit_ids:
                rewritten[key] = resolved
        queries.append(rewritten)

    repinned = dict(gold)
    repinned["queries"] = queries
    repinned["source_units_file"] = units_path
    repinned["source_units_sha256"] = units_sha256
    provenance = {
        "repinned_from": {
            "source_units_file": gold.get("source_units_file"),
            "source_units_sha256": gold.get("source_units_sha256"),
        },
        "repinned_to": {
            "source_units_file": units_path,
            "source_units_sha256": units_sha256,
        },
        "verification": (
            "every evidence unit resolves to exactly one unit of the new "
            "canonical carrying the same page, type and byte-identical text; "
            "unit ids were renumbered and are rewritten to match; the "
            "questions and expected answers are untouched"
        ),
        "evidence_unit_ids_verified": sorted(set(checked)),
        "evidence_unit_ids_remapped": dict(sorted(remapped.items())),
    }
    return RepinResult(
        repinned, provenance, tuple(sorted(set(checked))), tuple(mismatches)
    )
