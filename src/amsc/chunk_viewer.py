"""One self-contained HTML page showing where each arm put its boundaries.

The benchmark's tables say *how much* the arms differ. This says *where*: the
parsed document, page by page, with every block tinted by the chunk that carries
it, and a tab per arm so the same page can be seen segmented three ways.

It is a debugging and explainability aid, never a quality metric. A page chosen
because it looks bad is an anecdote; the numbers in ``benchmark-summary.json``
are the measurement.

Two deliberate refusals:

* No PDF and no bounding boxes. The parsed canonical stream is what the chunkers
  actually see, so it is what gets drawn -- a picture of the PDF would show
  boundaries the chunker never had.
* A unit the mapping could not place is drawn in grey and labelled ``UNMAPPED``.
  Colouring it by guesswork would put a chunk's colour on text that chunk may
  not contain, which is the one error a viewer must not make.

The output has no external asset of any kind: styles, script and data are inline,
so the file works from disk with no server.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .chunk_mapping import DocumentMapping
from .models import RawDocumentUnit, UnitType

#: Cycled by chunk ordinal, so neighbouring chunks never share a tint.
PALETTE = (
    "#4c78a8", "#f58518", "#54a24b", "#e45756", "#72b7b2",
    "#eeca3b", "#b279a2", "#ff9da6", "#9d755d", "#bab0ac",
)


def build_payload(
    units: Sequence[RawDocumentUnit],
    arms: Mapping[str, tuple[Sequence[Mapping[str, Any]], DocumentMapping]],
    *,
    document_id: str,
) -> dict[str, Any]:
    """Everything the page needs, and nothing it does not."""
    pages: list[dict[str, Any]] = []
    for unit in units:
        page = unit.source.page
        if not pages or pages[-1]["page"] != page:
            pages.append({"page": page, "units": []})
        entry = {
            "id": unit.unit_id,
            "type": unit.type.value,
            "section": list(unit.section_path or ()),
            "text": unit.text,
        }
        # Why a heading did or did not move section_path is the thing this
        # viewer exists to make auditable, so it is carried when the canonical
        # has it and simply absent when it does not.
        if unit.type is UnitType.HEADING:
            entry["level"] = unit.heading_level
            if unit.semantic_role is not None:
                entry["role"] = unit.semantic_role.value
                entry["opens"] = bool(unit.opens_section)
        pages[-1]["units"].append(entry)

    chunks: dict[str, dict[str, Any]] = {}
    segments: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for arm, (rows, mapping) in arms.items():
        chunks[arm] = {
            str(row["chunk_id"]): {
                "i": index,
                "tokens": row.get("token_count"),
                "pages": list(row.get("pages") or []),
                "heading": row.get("heading"),
                "sections": row.get("section_paths") or [],
                "strategies": row.get("split_strategies") or [],
            }
            for index, row in enumerate(rows)
        }
        by_unit: dict[str, list[dict[str, Any]]] = {}
        for chunk in mapping.chunks:
            for segment in chunk.segments:
                by_unit.setdefault(segment.unit_id, []).append(
                    {
                        "c": chunk.chunk_id,
                        "s": segment.unit_start,
                        "e": segment.unit_end,
                        "m": segment.method,
                    }
                )
        for entries in by_unit.values():
            entries.sort(key=lambda entry: (entry["s"], entry["c"]))
        segments[arm] = by_unit

    return {
        "document_id": document_id,
        "arms": list(arms),
        "pages": pages,
        "chunks": chunks,
        "segments": segments,
        "palette": list(PALETTE),
    }


_TEMPLATE = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #ffffff; --fg: #1b1b1b; --muted: #6b7280; --line: #e5e7eb;
    --panel: #f9fafb; --accent: #111827;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#111418; --fg:#e6e6e6; --muted:#9aa4b2; --line:#2a2f36;
            --panel:#171b21; --accent:#e6e6e6; }
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  header { padding:14px 18px; border-bottom:1px solid var(--line);
           display:flex; gap:18px; align-items:baseline; flex-wrap:wrap; }
  header h1 { font-size:15px; margin:0; font-weight:650; }
  .note { color:var(--muted); font-size:12px; }
  .tabs { display:flex; gap:6px; margin-left:auto; }
  .tabs button { border:1px solid var(--line); background:var(--panel); color:var(--fg);
                 padding:6px 12px; border-radius:6px; cursor:pointer; font:inherit; }
  .tabs button[aria-selected="true"] { background:var(--accent); color:var(--bg);
                                       border-color:var(--accent); font-weight:600; }
  main { display:grid; grid-template-columns:190px minmax(0,1fr) 320px; height:calc(100vh - 56px); }
  nav, aside { overflow:auto; border-right:1px solid var(--line); background:var(--panel); }
  aside { border-right:0; border-left:1px solid var(--line); }
  nav ol { list-style:none; margin:0; padding:6px; }
  nav button { width:100%; text-align:left; border:0; background:none; color:var(--fg);
               padding:6px 8px; border-radius:6px; cursor:pointer; font:inherit;
               display:flex; justify-content:space-between; gap:8px; }
  nav button[aria-current="true"] { background:var(--accent); color:var(--bg); font-weight:600; }
  nav .counts { color:var(--muted); font-variant-numeric:tabular-nums; font-size:12px; }
  nav button[aria-current="true"] .counts { color:var(--bg); }
  #page { overflow:auto; padding:18px 22px; }
  .unit { margin:0 0 12px; white-space:pre-wrap; word-wrap:break-word;
          border-left:3px solid transparent; padding-left:9px; }
  .unit.heading { font-weight:650; }
  .unit .tag { display:inline-block; font-size:11px; color:var(--muted);
               margin-right:8px; letter-spacing:.03em; cursor:pointer;
               border:0; background:none; padding:0; font-family:inherit;
               text-align:left; }
  .unit .tag:hover, .unit .tag[aria-pressed="true"] { color:var(--fg); text-decoration:underline; }
  .unit .tag .kind { text-transform:uppercase; }
  .unit .tag .crumb { text-transform:none; }
  .role { display:inline-block; font-size:10px; letter-spacing:.04em; padding:0 5px;
          border-radius:3px; border:1px solid var(--line); text-transform:uppercase; }
  .role-section { border-color:var(--accent); color:var(--accent); font-weight:600; }
  .role-group   { border-color:var(--accent); color:var(--accent); }
  .role-item    { color:var(--muted); }
  .role-display { color:var(--muted); font-style:italic; }
  .inspector .muted { color:var(--muted); }
  .unit[data-inspected="true"] { border-left-color:var(--accent); }
  .inspector { margin:0 10px 8px; padding:8px 10px; border:1px solid var(--accent);
               border-radius:7px; background:var(--bg); }
  .inspector dl { margin:0; display:grid; grid-template-columns:auto minmax(0,1fr);
                  gap:2px 8px; font-size:12px; }
  .inspector dt { color:var(--muted); }
  .inspector dd { margin:0; word-break:break-word; }
  .inspector .mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
  .seg { border-radius:3px; padding:1px 0; cursor:pointer; }
  .unmapped { background:repeating-linear-gradient(45deg,var(--line),var(--line) 4px,transparent 4px,transparent 8px);
              color:var(--muted); }
  .faded { opacity:.22; }
  aside h2 { font-size:12px; text-transform:uppercase; letter-spacing:.04em;
             color:var(--muted); margin:14px 14px 8px; }
  .chunk { margin:0 10px 8px; padding:8px 10px; border:1px solid var(--line);
           border-radius:7px; cursor:pointer; background:var(--bg); }
  .chunk[aria-selected="true"] { border-color:var(--accent); box-shadow:0 0 0 1px var(--accent); }
  .chunk .id { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }
  .chunk .meta { color:var(--muted); font-size:12px; margin-top:3px; }
  .swatch { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; }
  .empty { color:var(--muted); margin:0 14px; font-size:13px; }
</style>
</head>
<body>
<header>
  <h1>Parsed Chunk Viewer — __TITLE__</h1>
  <span class="note">Açıklanabilirlik/debug aracı; ana kalite metriğinin yerine geçmez.</span>
  <div class="tabs" id="tabs" role="tablist"></div>
</header>
<main>
  <nav><ol id="pages"></ol></nav>
  <section id="page"></section>
  <aside>
    <h2>Seçili birim</h2>
    <div id="inspector"></div>
    <h2>Bu sayfadaki chunk'lar</h2>
    <div id="legend"></div>
  </aside>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
(function () {
  var DATA = JSON.parse(document.getElementById("data").textContent);
  var arm = DATA.arms[0];
  var pageIndex = 0;
  var selected = null;
  var inspected = null;

  function escape(value) {
    var node = document.createElement("span");
    node.textContent = value == null ? "" : String(value);
    return node.innerHTML;
  }

  function breadcrumb(path) {
    return (path && path.length) ? path.join(" › ") : "—";
  }

  function colour(chunkId) {
    var meta = DATA.chunks[arm][chunkId];
    return meta ? DATA.palette[meta.i % DATA.palette.length] : null;
  }

  function chunksOnPage(index) {
    var seen = [];
    DATA.pages[index].units.forEach(function (unit) {
      (DATA.segments[arm][unit.id] || []).forEach(function (seg) {
        if (seen.indexOf(seg.c) === -1) seen.push(seg.c);
      });
    });
    return seen;
  }

  function pieces(unit) {
    // Cover the unit's text with its segments; whatever no segment claims is
    // reported as unmapped rather than tinted by the nearest neighbour.
    var out = [], cursor = 0;
    (DATA.segments[arm][unit.id] || []).forEach(function (seg) {
      if (seg.s > cursor) out.push({ text: unit.text.slice(cursor, seg.s), chunk: null });
      if (seg.e > cursor) {
        out.push({ text: unit.text.slice(Math.max(seg.s, cursor), seg.e), chunk: seg.c, method: seg.m });
        cursor = seg.e;
      }
    });
    if (cursor < unit.text.length) out.push({ text: unit.text.slice(cursor), chunk: null });
    return out;
  }

  function renderTabs() {
    var host = document.getElementById("tabs");
    host.innerHTML = "";
    DATA.arms.forEach(function (name) {
      var button = document.createElement("button");
      button.type = "button";
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", String(name === arm));
      button.textContent = name;
      button.onclick = function () { arm = name; selected = null; renderAll(); };
      host.appendChild(button);
    });
  }

  function renderPages() {
    var host = document.getElementById("pages");
    host.innerHTML = "";
    DATA.pages.forEach(function (page, index) {
      var counts = DATA.arms.map(function (name) {
        var previous = arm; arm = name;
        var total = chunksOnPage(index).length; arm = previous;
        return total;
      }).join(" / ");
      var item = document.createElement("li");
      var button = document.createElement("button");
      button.type = "button";
      button.setAttribute("aria-current", String(index === pageIndex));
      button.innerHTML = "<span>s. " + page.page + "</span>" +
                         "<span class='counts'>" + counts + "</span>";
      button.onclick = function () {
        pageIndex = index; selected = null; inspected = null; renderAll();
      };
      item.appendChild(button);
      host.appendChild(item);
    });
  }

  function renderPage() {
    var host = document.getElementById("page");
    host.innerHTML = "";
    DATA.pages[pageIndex].units.forEach(function (unit) {
      var block = document.createElement("p");
      block.className = "unit" + (unit.type === "heading" ? " heading" : "");
      block.setAttribute("data-inspected", String(inspected === unit.id));
      var tag = document.createElement("button");
      tag.type = "button";
      tag.className = "tag";
      tag.setAttribute("aria-pressed", String(inspected === unit.id));
      var badge = unit.role
        ? " <span class='role role-" + escape(unit.role) + "'>" + escape(unit.role) +
          (unit.opens ? " ▸" : " ·") + "</span>"
        : "";
      tag.innerHTML = "<span class='kind'>" + escape(unit.type + " · " + unit.id) +
                      "</span>" + badge +
                      " <span class='crumb'>" + escape(breadcrumb(unit.section)) + "</span>";
      tag.onclick = function () {
        inspected = inspected === unit.id ? null : unit.id;
        renderPage(); renderInspector();
      };
      block.appendChild(tag);
      pieces(unit).forEach(function (piece) {
        if (!piece.text) return;
        var span = document.createElement("span");
        span.textContent = piece.text;
        if (piece.chunk) {
          span.className = "seg" + (selected && selected !== piece.chunk ? " faded" : "");
          span.style.background = colour(piece.chunk) + "38";
          span.style.borderBottom = "2px solid " + colour(piece.chunk);
          span.title = piece.chunk + " · " + piece.method;
          span.onclick = function () {
            selected = selected === piece.chunk ? null : piece.chunk;
            renderPage(); renderLegend();
          };
        } else {
          span.className = "seg unmapped";
          span.title = "UNMAPPED — hiçbir chunk'a güvenle eşlenemedi";
        }
        block.appendChild(span);
      });
      host.appendChild(block);
    });
  }

  function renderInspector() {
    var host = document.getElementById("inspector");
    host.innerHTML = "";
    if (!inspected) {
      host.innerHTML = "<p class='empty'>Bir birimin etiketine tıklayın.</p>";
      return;
    }
    var page = DATA.pages[pageIndex];
    var unit = null;
    page.units.forEach(function (candidate) { if (candidate.id === inspected) unit = candidate; });
    if (!unit) {
      host.innerHTML = "<p class='empty'>Seçili birim bu sayfada değil.</p>";
      return;
    }
    var segs = DATA.segments[arm][unit.id] || [];
    var rows = [
      ["unit_id", "<span class='mono'>" + escape(unit.id) + "</span>"],
      ["type", escape(unit.type)],
      ["page", escape(page.page)],
    ];
    if (unit.type === "heading") {
      rows.push(["heading_level", escape(unit.level)]);
      rows.push([
        "semantic_role",
        unit.role
          ? "<span class='role role-" + escape(unit.role) + "'>" + escape(unit.role) + "</span>"
          : "<span class='muted'>bu canonical rol taşımıyor</span>",
      ]);
      rows.push([
        "opens_section",
        unit.role
          ? (unit.opens ? "<b>evet</b> — section_path'i değiştirir"
                        : "hayır — section_path'e dokunmaz")
          : "<span class='muted'>—</span>",
      ]);
    }
    rows.push(["section", escape(breadcrumb(unit.section))]);
    rows.push(["depth", escape((unit.section || []).length)]);
    if (!segs.length) {
      rows.push(["chunk", "UNMAPPED"]);
    } else {
      segs.forEach(function (seg) {
        var meta = DATA.chunks[arm][seg.c] || {};
        rows.push([
          "chunk",
          "<span class='mono'>" + escape(seg.c) + "</span> · " + escape(seg.m) +
          " · " + escape(seg.s) + "–" + escape(seg.e) +
          (meta.strategies && meta.strategies.length
            ? " · " + escape(meta.strategies.join(", ")) : ""),
        ]);
      });
    }
    var card = document.createElement("div");
    card.className = "inspector";
    card.innerHTML = "<dl>" + rows.map(function (row) {
      return "<dt>" + row[0] + "</dt><dd>" + row[1] + "</dd>";
    }).join("") + "</dl>";
    host.appendChild(card);
  }

  function renderLegend() {
    var host = document.getElementById("legend");
    host.innerHTML = "";
    var ids = chunksOnPage(pageIndex);
    if (!ids.length) {
      host.innerHTML = "<p class='empty'>Bu sayfada eşlenmiş chunk yok.</p>";
      return;
    }
    ids.forEach(function (chunkId) {
      var meta = DATA.chunks[arm][chunkId] || {};
      var card = document.createElement("div");
      card.className = "chunk";
      card.setAttribute("aria-selected", String(selected === chunkId));
      var sections = (meta.sections || []).map(function (path) { return path.join(" > "); });
      card.innerHTML =
        "<div class='id'><span class='swatch' style='background:" + colour(chunkId) + "'></span>" +
        chunkId + "</div>" +
        "<div class='meta'>" + (meta.tokens != null ? meta.tokens + " token" : "") +
        (meta.pages && meta.pages.length ? " · s. " + meta.pages.join(", ") : "") + "</div>" +
        (meta.heading ? "<div class='meta'>heading: " + meta.heading.split("\\n")[0] + "</div>" : "") +
        (sections.length ? "<div class='meta'>section: " + sections.join(" | ") + "</div>" : "") +
        (meta.strategies && meta.strategies.length
          ? "<div class='meta'>split: " + meta.strategies.join(", ") + "</div>" : "");
      card.onclick = function () {
        selected = selected === chunkId ? null : chunkId;
        renderPage(); renderLegend();
      };
      host.appendChild(card);
    });
  }

  function renderAll() {
    renderTabs(); renderPages(); renderPage(); renderInspector(); renderLegend();
  }
  renderAll();
})();
</script>
</body>
</html>
"""


def render_html(payload: Mapping[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    # The payload is embedded in a script element, so any "<" has to stop being
    # one; escaping it keeps a "</script>" inside document text from ending the
    # element early.
    data = data.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    title = html.escape(str(payload.get("document_id") or "document"))
    return _TEMPLATE.replace("__TITLE__", title).replace("__DATA__", data)


def write_viewer(
    path: str | Path,
    units: Sequence[RawDocumentUnit],
    arms: Mapping[str, tuple[Sequence[Mapping[str, Any]], DocumentMapping]],
    *,
    document_id: str,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render_html(build_payload(units, arms, document_id=document_id)),
        encoding="utf-8",
        newline="\n",
    )
    return destination
