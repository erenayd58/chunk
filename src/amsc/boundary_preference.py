"""Human boundary-preference labelling: items, a blind A/B form, and scoring.

The Kademe 0 measurement instrument of the Deep Analysis v2 plan. The only
numbers that can carry a "premium" claim are human judgements of the places
where Deep Analysis and Standard actually differ, so this module builds
exactly those items and nothing that could be gamed:

* ``change_group`` -- a span between cuts common to both partitions where
  they differ (from :func:`amsc.boundary_quality.compare`). The annotator
  sees the full text of both partitions of the span, blind and A/B
  randomised; the mapping lives in the manifest, never in the form.
* ``unchanged_window`` -- a multi-candidate budget window where both arms
  kept Standard's cut: was that cut acceptable, and would another candidate
  have been better (a missed opportunity)?
* ``forced_cut`` -- a single-admissible budget cut whose boundary carries a
  deterministic smell: is Standard's cut acceptable, which neighbour is
  better?

Sampling is deterministic (sha256 order of item ids), no RNG; the form is a
single self-contained HTML file with no external resources; labels are
exported as JSON and scored by :func:`score`, which unblinds against the
manifest. The window enumeration is a read-only mirror of the structural
walk, pinned against :func:`amsc.structural_chunker.chunk_units` by test.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .boundary_quality import (
    QualityConfig,
    boundary_smells,
    compare,
    load_rows,
    partition_from_rows,
    refuse_frozen_output,
    write_json,
)
from .chunk_mapping import base_unit_id
from .models import RawDocumentUnit
from .structural_chunker import _sections
from .tokenization import TokenCounter

SCHEMA_VERSION = "1.0"
KIND_CHANGE_GROUP = "change_group"
KIND_UNCHANGED_WINDOW = "unchanged_window"
KIND_FORCED_CUT = "forced_cut"
KINDS = (KIND_CHANGE_GROUP, KIND_UNCHANGED_WINDOW, KIND_FORCED_CUT)
REASONS = ("orphan_label", "lead_in", "back_reference", "run_split", "size", "topic", "other")
WINDOW_MULTI = "multi"
WINDOW_FORCED = "forced"
WINDOW_LABEL_SEAM = "label_seam"
CONTEXT_PIECES_AFTER = 2


# --------------------------------------------------------------------------
# the window mirror
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Window:
    """One budget decision of the structural walk, as the walk saw it."""

    section_index: int
    heading: str | None
    section_path: tuple[str, ...]
    start: int
    greedy: int
    admissible: tuple[int, ...]
    kind: str
    piece_ids: tuple[str, ...]
    piece_texts: tuple[str, ...]

    @property
    def cut_after_unit_id(self) -> str:
        return self.piece_ids[self.greedy - 1]

    @property
    def candidate_cut_after(self) -> tuple[str, ...]:
        return tuple(self.piece_ids[stop - 1] for stop in self.admissible)


def enumerate_windows(
    units: Sequence[RawDocumentUnit],
    *,
    counter: TokenCounter,
    config: QualityConfig = QualityConfig(),
    respect_semantic_roles: bool = True,
) -> list[Window]:
    """Every budget cut of the structural walk with its admissible set.

    A step-for-step mirror of ``structural_chunker.chunk_units`` up to the
    rejoin (which never fires on the KKB corpora and is pinned by test on a
    synthetic one): the seamed ceiling, the label seam, the greedy budget
    cut and the re-test after an early cut.
    """
    sections = _sections(units, counter, config.hard_max_tokens, respect_semantic_roles)
    windows: list[Window] = []
    for section_index, section in enumerate(sections):
        seamed = respect_semantic_roles and any(piece.label for piece in section.pieces)
        ceiling = config.target_tokens if seamed else config.soft_max_tokens
        if section.tokens <= ceiling:
            continue
        pieces = section.pieces
        piece_ids = tuple(piece.unit_id for piece in pieces)
        piece_texts = tuple(piece.text for piece in pieces)
        head_cost = counter.count(section.heading) + 2 if section.heading else 0
        totals = [0]
        for piece in pieces:
            totals.append(totals[-1] + piece.tokens)

        def size(start: int, stop: int) -> int:
            return head_cost + totals[stop] - totals[start]

        start = index = current = 0
        while index < len(pieces):
            piece = pieces[index]
            projected = head_cost + current + piece.tokens
            at_label = piece.label and current >= config.min_tokens
            if index > start and (projected > config.target_tokens or at_label):
                greedy = index
                if at_label:
                    kind, admissible = WINDOW_LABEL_SEAM, (greedy,)
                else:
                    admissible = tuple(
                        stop
                        for stop in range(start + 1, index + 1)
                        if config.min_tokens <= size(start, stop) <= config.target_tokens
                    )
                    kind = WINDOW_MULTI if len(admissible) >= 2 else WINDOW_FORCED
                windows.append(
                    Window(
                        section_index=section_index,
                        heading=section.heading,
                        section_path=tuple(section.section_path),
                        start=start,
                        greedy=greedy,
                        admissible=admissible,
                        kind=kind,
                        piece_ids=piece_ids,
                        piece_texts=piece_texts,
                    )
                )
                start = greedy
                current = totals[index] - totals[greedy]
                continue
            current += piece.tokens
            index += 1
    return windows


# --------------------------------------------------------------------------
# items
# --------------------------------------------------------------------------


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cut_ids(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    """Raw ids after which a partition cuts inside a section."""
    cuts: set[str] = set()
    for section in partition_from_rows(rows):
        for block in section.blocks[:-1]:
            cuts.add(block.unit_ids[-1])
    return cuts


def build_items(
    units: Sequence[RawDocumentUnit],
    standard_rows: Sequence[Mapping[str, Any]],
    deep_rows: Sequence[Mapping[str, Any]],
    *,
    counter: TokenCounter,
    config: QualityConfig = QualityConfig(),
    unchanged_sample: int = 30,
    respect_semantic_roles: bool = True,
) -> dict[str, Any]:
    """The labelling manifest: items plus the blinding the form must not show."""
    units_by_id = {unit.unit_id: unit for unit in units}
    report = compare(units, standard_rows, deep_rows, counter=counter, config=config)
    items: list[dict[str, Any]] = []

    for section in report["sections_with_differences"]:
        for group in section["change_groups"]:
            item_id = f"cg-{group['unit_ids'][0]}-{group['unit_ids'][-1]}"
            standard_side = "A" if int(_digest(item_id)[0], 16) % 2 == 0 else "B"
            items.append(
                {
                    "item_id": item_id,
                    "kind": KIND_CHANGE_GROUP,
                    "heading": section["heading"],
                    "section_paths": section["section_paths"],
                    "unit_ids": list(group["unit_ids"]),
                    "cuts_after": {
                        "standard": list(group["standard_cuts_after"]),
                        "deep": list(group["deep_cuts_after"]),
                    },
                    "deterministic_verdict": section["verdict"],
                    "blinding": {
                        "A": "standard" if standard_side == "A" else "deep",
                        "B": "deep" if standard_side == "A" else "standard",
                    },
                }
            )

    windows = enumerate_windows(
        units, counter=counter, config=config, respect_semantic_roles=respect_semantic_roles
    )
    standard_cuts, deep_cuts = _cut_ids(standard_rows), _cut_ids(deep_rows)

    def context(window: Window) -> list[str]:
        end = min(len(window.piece_ids), window.greedy + CONTEXT_PIECES_AFTER)
        return list(window.piece_ids[window.start : end])

    def smells_at(window: Window) -> list[str]:
        left_raw = window.piece_ids[window.greedy - 1]
        right_raw = window.piece_ids[window.greedy]
        left = units_by_id[base_unit_id(left_raw)]
        right = units_by_id[base_unit_id(right_raw)]
        return boundary_smells(
            left, right, left_raw_id=left_raw, right_raw_id=right_raw, config=config
        )

    unchanged = [
        window
        for window in windows
        if window.kind == WINDOW_MULTI
        and window.cut_after_unit_id in standard_cuts
        and window.cut_after_unit_id in deep_cuts
    ]
    unchanged.sort(key=lambda window: _digest(f"uw-{window.cut_after_unit_id}"))
    for window in unchanged[:unchanged_sample]:
        items.append(
            {
                "item_id": f"uw-{window.cut_after_unit_id}",
                "kind": KIND_UNCHANGED_WINDOW,
                "heading": window.heading,
                "section_paths": [list(window.section_path)] if window.section_path else [],
                "unit_ids": context(window),
                "standard_cut_after": window.cut_after_unit_id,
                "candidates": list(window.candidate_cut_after),
                "smells": smells_at(window),
            }
        )

    for window in windows:
        if window.kind != WINDOW_FORCED or window.greedy >= len(window.piece_ids):
            continue
        smells = smells_at(window)
        if not smells:
            continue
        low = max(window.start + 1, window.greedy - 2)
        high = min(len(window.piece_ids) - 1, window.greedy + 2)
        items.append(
            {
                "item_id": f"fc-{window.cut_after_unit_id}",
                "kind": KIND_FORCED_CUT,
                "heading": window.heading,
                "section_paths": [list(window.section_path)] if window.section_path else [],
                "unit_ids": context(window),
                "standard_cut_after": window.cut_after_unit_id,
                "candidates": [window.piece_ids[stop - 1] for stop in range(low, high + 1)],
                "smells": smells,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "document_id": units[0].document_id,
        "config": {**config.__dict__},
        "reasons": list(REASONS),
        "unchanged_sample": unchanged_sample,
        "window_counts": dict(Counter(window.kind for window in windows)),
        "kind_counts": dict(Counter(item["kind"] for item in items)),
        "items": items,
    }


# --------------------------------------------------------------------------
# the form
# --------------------------------------------------------------------------

_CSS = """
body{font:15px/1.5 Georgia,serif;margin:0;background:#fbfaf7;color:#1e1c18}
header{position:sticky;top:0;background:#fff8e6;border-bottom:1px solid #d9cfae;padding:10px 18px;z-index:2}
main{max-width:1240px;margin:0 auto;padding:18px}
.item{border:1px solid #d9d4c4;border-radius:8px;background:#fff;margin:0 0 22px;padding:14px 16px}
.item h2{font-size:16px;margin:0 0 6px}
.meta{font:12.5px Consolas,monospace;color:#5a5648;margin-bottom:10px}
.sides{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.side{border:1px solid #e3ded0;border-radius:6px;padding:10px;background:#fdfcf9}
.side h3{margin:0 0 8px;font-size:14px;letter-spacing:.06em;text-transform:uppercase}
.block{border-left:4px solid #b8a97a;padding:6px 10px;margin:0 0 10px;background:#fff}
.cut{color:#9a2f1f;font:bold 12px Consolas,monospace;margin:6px 0}
.cand{display:inline-block;background:#fff3b0;border:1px solid #d9c25a;border-radius:4px;padding:0 6px;font:bold 12px Consolas,monospace;margin:4px 0}
pre{white-space:pre-wrap;font:13.5px/1.45 "Segoe UI",system-ui,sans-serif;margin:0}
.q{margin-top:12px;padding-top:10px;border-top:1px dashed #d9d4c4}
.q label{margin-right:14px}
textarea{width:100%;min-height:48px;font:13px Consolas,monospace}
button{font:14px Georgia,serif;padding:6px 14px}
.smell{color:#7a4f00;font:12px Consolas,monospace}
"""

_JS = """
const KEY = 'bp-labels-' + document.body.dataset.manifest;
function load(){ try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { return {}; } }
function save(labels){ try { localStorage.setItem(KEY, JSON.stringify(labels)); } catch (e) {} }
function collect(){
  const labels = {};
  document.querySelectorAll('.item').forEach(item => {
    const id = item.dataset.item; const entry = {kind: item.dataset.kind};
    item.querySelectorAll('input[type=radio]:checked').forEach(r => { entry[r.dataset.field] = r.value; });
    entry.reasons = Array.from(item.querySelectorAll('input[type=checkbox]:checked')).map(c => c.value);
    const note = item.querySelector('textarea'); if (note && note.value.trim()) entry.note = note.value.trim();
    if (Object.keys(entry).length > 2 || entry.reasons.length) labels[id] = entry;
  });
  return labels;
}
function restore(){
  const labels = load();
  document.querySelectorAll('.item').forEach(item => {
    const entry = labels[item.dataset.item]; if (!entry) return;
    item.querySelectorAll('input[type=radio]').forEach(r => { if (entry[r.dataset.field] === r.value) r.checked = true; });
    item.querySelectorAll('input[type=checkbox]').forEach(c => { c.checked = (entry.reasons || []).includes(c.value); });
    const note = item.querySelector('textarea'); if (note && entry.note) note.value = entry.note;
  });
  progress();
}
function progress(){
  const labels = collect(); save(labels);
  const total = document.querySelectorAll('.item').length;
  document.getElementById('progress').textContent = Object.keys(labels).length + ' / ' + total + ' etiketlendi';
}
function exportLabels(){
  const payload = {schema_version: '1.0', manifest_sha256: document.body.dataset.manifest, labels: collect()};
  const text = JSON.stringify(payload, null, 2);
  document.getElementById('export').value = text;
  const link = document.getElementById('download');
  link.href = 'data:application/json;charset=utf-8,' + encodeURIComponent(text);
  link.style.display = 'inline';
}
document.addEventListener('change', progress);
document.addEventListener('input', progress);
document.addEventListener('DOMContentLoaded', restore);
"""


def _render_blocks(unit_ids: Sequence[str], cuts_after: Sequence[str], texts: Mapping[str, str]) -> str:
    cut_set = set(cuts_after)
    blocks: list[list[str]] = [[]]
    for unit_id in unit_ids:
        blocks[-1].append(unit_id)
        if unit_id in cut_set:
            blocks.append([])
    parts: list[str] = []
    for index, block in enumerate(block for block in blocks if block):
        if index:
            parts.append('<div class="cut">— — — chunk sınırı — — —</div>')
        seen: list[str] = []
        for unit_id in block:
            base = base_unit_id(unit_id)
            if base in seen:
                continue
            seen.append(base)
            parts.append(f'<div class="block"><pre>{html.escape(texts[base])}</pre></div>')
    return "".join(parts)


def _render_candidates(item: Mapping[str, Any], texts: Mapping[str, str]) -> str:
    candidates = list(item["candidates"])
    parts: list[str] = []
    for unit_id in item["unit_ids"]:
        base = base_unit_id(unit_id)
        parts.append(f'<div class="block"><pre>{html.escape(texts[base])}</pre></div>')
        marks = []
        if unit_id in candidates:
            marks.append(f'<span class="cand">C{candidates.index(unit_id) + 1}</span>')
        if unit_id == item["standard_cut_after"]:
            marks.append('<div class="cut">— — — Standard kesimi — — —</div>')
        parts.extend(marks)
    return "".join(parts)


def _reason_boxes(item_id: str) -> str:
    return " ".join(
        f'<label><input type="checkbox" value="{reason}"> {reason}</label>' for reason in REASONS
    )


def _radio(item_id: str, field: str, options: Sequence[tuple[str, str]]) -> str:
    return " ".join(
        f'<label><input type="radio" name="{field}-{html.escape(item_id)}" data-field="{field}" '
        f'value="{value}"> {html.escape(label)}</label>'
        for value, label in options
    )


def render_form(manifest: Mapping[str, Any], units: Sequence[RawDocumentUnit], *, title: str) -> str:
    """A self-contained blind labelling form. Carries no blinding, no verdicts."""
    texts = {unit.unit_id: unit.text for unit in units}
    public = {
        key: value for key, value in manifest.items() if key != "items"
    }
    manifest_sha = _digest(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    sections: list[str] = []
    for item in manifest["items"]:
        item_id = item["item_id"]
        heading = html.escape((item.get("heading") or "(başlıksız bölüm)").replace("\n", " / "))
        path = " › ".join(html.escape(" / ".join(p)) for p in item.get("section_paths") or [])
        meta = f'<div class="meta">{html.escape(item_id)} · {item["kind"]} · yol: {path}</div>'
        if item["kind"] == KIND_CHANGE_GROUP:
            side_for = item["blinding"]
            body = (
                '<div class="sides">'
                + "".join(
                    f'<div class="side"><h3>{side}</h3>'
                    + _render_blocks(item["unit_ids"], item["cuts_after"][side_for[side]], texts)
                    + "</div>"
                    for side in ("A", "B")
                )
                + "</div>"
            )
            questions = (
                '<div class="q"><b>Hangi bölümleme daha iyi?</b> '
                + _radio(item_id, "preferred", [("A", "A"), ("B", "B"), ("equal", "eşit")])
                + '</div><div class="q"><b>A kabul edilebilir mi?</b> '
                + _radio(item_id, "acceptable_A", [("yes", "evet"), ("no", "hayır")])
                + ' &nbsp; <b>B kabul edilebilir mi?</b> '
                + _radio(item_id, "acceptable_B", [("yes", "evet"), ("no", "hayır")])
                + "</div>"
            )
        else:
            body = _render_candidates(item, texts)
            options = [(f"C{i + 1}", f"C{i + 1}") for i in range(len(item["candidates"]))]
            questions = (
                '<div class="q"><b>Standard kesimi kabul edilebilir mi?</b> '
                + _radio(item_id, "acceptable_standard", [("yes", "evet"), ("no", "hayır")])
                + '</div><div class="q"><b>Daha iyi bir aday var mı?</b> '
                + _radio(item_id, "better_candidate", [("none", "yok")] + options)
                + "</div>"
            )
        sections.append(
            f'<section class="item" data-item="{html.escape(item_id)}" data-kind="{item["kind"]}">'
            f"<h2>{heading}</h2>{meta}{body}{questions}"
            f'<div class="q"><b>Neden:</b> {_reason_boxes(item_id)}</div>'
            f'<div class="q"><textarea placeholder="Not (isteğe bağlı)"></textarea></div>'
            "</section>"
        )
    return (
        "<!doctype html><html lang=\"tr\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head>"
        f'<body data-manifest="{manifest_sha}">'
        f"<header><b>{html.escape(title)}</b> · {len(manifest['items'])} öğe · "
        f'<span id="progress">0 etiketlendi</span> · '
        '<button type="button" onclick="exportLabels()">Etiketleri dışa aktar</button> '
        '<a id="download" download="boundary-preference-labels.json" style="display:none">indir</a>'
        f'<div class="meta">{html.escape(json.dumps(public, ensure_ascii=False, sort_keys=True))}</div>'
        "</header><main>"
        + "".join(sections)
        + '<section class="item"><h2>Dışa aktarılan etiketler</h2>'
        '<textarea id="export" placeholder="Etiketleri dışa aktar düğmesine basın"></textarea></section>'
        f"</main><script>{_JS}</script></body></html>"
    )


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def score(labels: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Unblind the labels against the manifest and compute the plan's rates."""
    by_id = {item["item_id"]: item for item in manifest["items"]}
    groups = Counter()
    windows = Counter()
    forced = Counter()
    reasons: Counter[str] = Counter()
    unknown: list[str] = []
    for item_id, label in (labels.get("labels") or {}).items():
        item = by_id.get(item_id)
        if item is None:
            unknown.append(item_id)
            continue
        for reason in label.get("reasons") or []:
            reasons[reason] += 1
        if item["kind"] == KIND_CHANGE_GROUP:
            preferred = label.get("preferred")
            if preferred not in ("A", "B", "equal"):
                continue
            groups["labeled"] += 1
            side = item["blinding"]
            if preferred == "equal":
                groups["equal"] += 1
            else:
                groups[f"{side[preferred]}_preferred"] += 1
            for letter in ("A", "B"):
                if label.get(f"acceptable_{letter}") == "yes":
                    groups[f"{side[letter]}_acceptable"] += 1
        else:
            bucket = windows if item["kind"] == KIND_UNCHANGED_WINDOW else forced
            if label.get("acceptable_standard") not in ("yes", "no"):
                continue
            bucket["labeled"] += 1
            bucket["standard_acceptable"] += label.get("acceptable_standard") == "yes"
            better = label.get("better_candidate")
            bucket["better_candidate_named"] += bool(better and better != "none")
    labeled = groups["labeled"]
    return {
        "schema_version": SCHEMA_VERSION,
        "change_groups": {
            **{key: groups[key] for key in (
                "labeled", "deep_preferred", "standard_preferred", "equal",
                "deep_acceptable", "standard_acceptable",
            )},
            "preferred_or_equal_rate": _rate(groups["deep_preferred"] + groups["equal"], labeled),
            "worse_than_standard_rate": _rate(groups["standard_preferred"], labeled),
            "zero_worse_and_n_at_least_60": labeled >= 60 and groups["standard_preferred"] == 0,
        },
        "unchanged_windows": {
            **{key: windows[key] for key in ("labeled", "standard_acceptable", "better_candidate_named")},
            "standard_acceptable_rate": _rate(windows["standard_acceptable"], windows["labeled"]),
        },
        "forced_cuts": {
            **{key: forced[key] for key in ("labeled", "standard_acceptable", "better_candidate_named")},
            "standard_acceptable_rate": _rate(forced["standard_acceptable"], forced["labeled"]),
        },
        "reasons": dict(sorted(reasons.items())),
        "unknown_item_ids": sorted(unknown),
        "note": (
            "Rates over labelled items only; the premium claim of the plan needs "
            "n >= 60 labelled change groups with zero standard_preferred, pooled "
            "across corpora, plus retrieval non-inferiority and a third document."
        ),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> None:
    from .io import load_jsonl_units
    from .tokenization import TiktokenTokenCounter

    parser = argparse.ArgumentParser(
        description="Boundary-preference labelling: build a blind form, or score labels"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--units", required=True, type=Path)
    build.add_argument("--standard", required=True, type=Path)
    build.add_argument("--deep", required=True, type=Path)
    build.add_argument("--output-dir", required=True, type=Path)
    build.add_argument("--title", default="Boundary preference")
    build.add_argument("--unchanged-sample", type=int, default=30)
    build.add_argument("--encoding", default="cl100k_base")
    build.add_argument("--min-tokens", type=int, default=QualityConfig.min_tokens)
    build.add_argument("--target-tokens", type=int, default=QualityConfig.target_tokens)
    build.add_argument("--soft-max-tokens", type=int, default=QualityConfig.soft_max_tokens)
    build.add_argument("--hard-max-tokens", type=int, default=QualityConfig.hard_max_tokens)
    scoring = commands.add_parser("score")
    scoring.add_argument("--labels", required=True, type=Path)
    scoring.add_argument("--manifest", required=True, type=Path)
    scoring.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    if args.command == "build":
        refuse_frozen_output(args.output_dir)
        config = QualityConfig(
            min_tokens=args.min_tokens,
            target_tokens=args.target_tokens,
            soft_max_tokens=args.soft_max_tokens,
            hard_max_tokens=args.hard_max_tokens,
        )
        units = load_jsonl_units(args.units)
        counter = TiktokenTokenCounter(args.encoding)
        manifest = build_items(
            units,
            load_rows(args.standard),
            load_rows(args.deep),
            counter=counter,
            config=config,
            unchanged_sample=args.unchanged_sample,
        )
        write_json(args.output_dir / "items.json", manifest)
        form = render_form(manifest, units, title=args.title)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "form.html").write_text(form, encoding="utf-8", newline="\n")
        print(json.dumps({"kind_counts": manifest["kind_counts"], "window_counts": manifest["window_counts"]}, ensure_ascii=False, sort_keys=True))
        return

    refuse_frozen_output(args.output)
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = score(labels, manifest)
    write_json(args.output, result)
    print(json.dumps(result["change_groups"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
