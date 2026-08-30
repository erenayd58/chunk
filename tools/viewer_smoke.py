"""Browser smoke for Viewer v2: open the page, drive the four tabs, screenshot.

Not a pytest test -- it needs a built viewer and a real browser:

    py -3.11 -m pip install -e ".[smoke]" && py -3.11 -m playwright install chromium
    py -3.11 tools/viewer_smoke.py artifacts/viewer-v2/index.html artifacts/local/smoke-offline
    py -3.11 tools/viewer_smoke.py http://127.0.0.1:8765/ artifacts/local/smoke-live --live

The offline run drives Sunum (the comparison board: aligned method columns,
chunk cards, divergence stepping, adding a third column, picking a chunk),
the gold-query view, Debug (filters, inspector, section decision trail),
Benchmark (frozen section, Deep panel, cross-document table), the deep-only
holdout document and an 820px viewport.
``--live`` additionally sends a question through the chat, opens a source
card, and runs the four-arm comparison against ``amsc.viewer_server``.
Reports console errors and failed checks; exit code 1 on any failure.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

target = sys.argv[1]
outdir = Path(sys.argv[2])
live = "--live" in sys.argv
outdir.mkdir(parents=True, exist_ok=True)
if not target.startswith("http"):
    target = Path(target).resolve().as_uri()

problems: list[str] = []
console: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        problems.append(message)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 950})
    page.on("console", lambda m: console.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
    started = time.perf_counter()
    page.goto(target, wait_until="load", timeout=120000)
    page.wait_for_selector("#methods .method", timeout=60000)
    load_s = time.perf_counter() - started

    # --- Sunum ---
    methods = page.locator("#methods .method")
    check(methods.count() == 4, f"expected 4 method cards, got {methods.count()}")
    check(page.locator("#results .results").count() == 1, "results strip missing on the default doc")
    # --- the comparison board: columns, chunk cards, divergence walking ---
    check(page.locator("#board .cell.ur").count() > 0, "the comparison rendered no rows")
    check(page.locator("#board .cell.bd .open:not(.cont)").count() > 0, "no chunk starts on the board")
    check(page.locator("#board .cell.bd.dv").count() > 0, "the board opened without a divergence")
    lanes = page.evaluate("() => laneList()")
    check(lanes == ["structure-only", "agentic"], f"expected Standard then Deep Analysis, got {lanes}")
    # The paragraph is the atom: every row carries one cell per column, and
    # the same paragraph starts at the same height in all of them.
    align = page.evaluate("""() => {
      const bd = document.getElementById('board');
      const n = Number(getComputedStyle(bd).getPropertyValue('--n'));
      const by = new Map();
      for (const c of bd.querySelectorAll('.cell.ur')) {
        if (!by.has(c.dataset.uid)) by.set(c.dataset.uid, []);
        by.get(c.dataset.uid).push(c);
      }
      let bad = 0, worst = 0;
      for (const [, g] of by) {
        if (g.length !== n) { bad++; continue; }
        const tops = g.map(c => {
          const b = c.querySelector('.body, .miss');
          return b ? Math.round(b.getBoundingClientRect().top) : null;
        }).filter(v => v !== null);
        if (tops.length > 1) worst = Math.max(worst, Math.max(...tops) - Math.min(...tops));
      }
      return {rows: by.size, n, bad, worst};
    }""")
    check(align["bad"] == 0, f"rows without one cell per column: {align}")
    check(align["worst"] <= 1, f"the columns are {align['worst']}px out of true")
    page.screenshot(path=str(outdir / "01-sunum.png"), full_page=False)

    # a chunk card opens the detail panel for the column it belongs to
    page.locator('#board .cell.bd .open[data-arm="agentic"]').first.click()
    page.wait_for_timeout(300)
    detail = page.locator("#presdetail").inner_text()
    check("Parça" in detail and "Deep Analysis kararı" in detail, "detail panel lacks the Deep decision sentence")

    # a third method joins as a third column, at the right-hand end
    page.locator('#cmpbar button[data-lane="markdown"]').click()
    page.wait_for_timeout(500)
    check(page.evaluate("() => laneList()") == ["structure-only", "agentic", "markdown"],
          "a third column did not join at the end")
    check(page.evaluate("() => Number(getComputedStyle(document.getElementById('board')).getPropertyValue('--n'))") == 3,
          "the board did not grow a third column")
    page.screenshot(path=str(outdir / "02-sunum-compare.png"), full_page=False)
    page.locator('#board .colhead .drop[data-drop="markdown"]').click()
    page.wait_for_timeout(400)
    check(len(page.evaluate("() => laneList()")) == 2, "the column head did not drop its method")

    # walking to a divergence moves the page and marks the spot
    diffs = page.evaluate("() => stepDiffs().length")
    check(diffs > 0, "Standard and Deep are identical everywhere, which they are not")
    # The screen opens on the first divergence; one step moves to the next.
    at = page.evaluate("() => state.diffIdx")
    check(at == 0, f"Sunum did not open on the first divergence (diffIdx={at})")
    page.locator("#nextdiff").click()
    page.wait_for_timeout(500)
    check(page.locator("#board .gut.bd.dv.here").count() == 1, "no current divergence after stepping to one")
    check(page.evaluate("() => state.diffIdx") == at + 1, "the divergence walker did not advance")
    check("yeni parça açtı" in page.locator("#dvsum").inner_text(), "the readout does not say what happened")
    page.screenshot(path=str(outdir / "03-sunum-deepdiff.png"), full_page=False)

    # --- Sorgu ---
    page.locator("#modetabs button[data-mode='query']").click()
    page.wait_for_timeout(800)
    offline_hidden = "hidden" in (page.locator("#offline").get_attribute("class") or "")
    check(offline_hidden == live, f"offline notice hidden={offline_hidden} but live={live}")
    check(page.locator("#chatarms button").count() >= 2, "chat arm pills missing")
    check(page.locator("#suggest button").count() > 0, "no suggested questions on a gold-backed doc")
    if live:
        page.locator("#suggest button").first.click()
        page.locator("#chatsend").click()
        page.wait_for_selector("#turns .answer .txt:not(.muted)", timeout=180000)
        page.wait_for_timeout(300)
        answer = page.locator("#turns .answer .txt").first.inner_text()
        check(len(answer) > 20, "empty chat answer")
        check(page.locator("#turns .src").count() > 0, "no source cards after chat")
        check(page.locator("#turns .cite").count() > 0, "answer carries no citation chips")
        page.screenshot(path=str(outdir / "04-sorgu-chat.png"), full_page=False)
        page.locator("#turns .src").first.click()
        page.wait_for_timeout(300)
        check(page.locator("#modal .box").count() == 1, "source modal did not open")
        page.screenshot(path=str(outdir / "05-sorgu-source-modal.png"), full_page=False)
        page.locator("#mclose").click()
        # compare mode
        page.locator("#chatcmp").check()
        page.locator("#chatq").fill("Şirketin 2024 yılı toplam üye sayısı kaçtır?")
        page.locator("#chatsend").click()
        page.wait_for_selector("#turns .cmpcols", timeout=300000)
        page.wait_for_timeout(300)
        check(page.locator("#turns .cmpcol").count() >= 2, "compare columns missing")
        page.screenshot(path=str(outdir / "06-sorgu-compare.png"), full_page=False)
        page.locator("#chatcmp").uncheck()
    else:
        page.screenshot(path=str(outdir / "04-sorgu-offline.png"), full_page=False)
    # gold sub-tab
    page.locator("#qsubtabs button[data-sub='gold']").click()
    page.wait_for_timeout(400)
    check(page.locator("#querycols .qcol").count() >= 3, "gold columns missing")
    page.screenshot(path=str(outdir / "07-sorgu-gold.png"), full_page=False)

    # --- Debug ---
    page.locator("#modetabs button[data-mode='debug']").click()
    page.wait_for_timeout(500)
    check(page.locator("#dbglist .dbgunit").count() > 0, "debug unit list empty")
    page.locator("#dbglist .dbgunit").first.click()
    page.wait_for_timeout(200)
    check("Birim incelemesi" in page.locator("#inspector").inner_text(), "inspector not populated")
    page.locator("#secpanel details > summary").click()
    page.wait_for_timeout(200)
    check(page.locator("#secpanel .sectable tr").count() > 1, "section decision table empty")
    page.screenshot(path=str(outdir / "08-debug.png"), full_page=False)
    page.locator("#secpanel tr.clk").first.click()
    page.wait_for_timeout(300)
    check("Deep Analysis karar izi" in page.locator("#inspector").inner_text(), "decision trail not shown after section click")
    page.screenshot(path=str(outdir / "09-debug-trail.png"), full_page=False)

    # --- Benchmark ---
    page.locator("#modetabs button[data-mode='benchmark']").click()
    page.wait_for_timeout(500)
    text = page.locator("#view-benchmark").inner_text()
    check("Kalite özeti" in text, "benchmark summary section missing")
    check("Sınır kalitesi" in text, "the per-defect contract table is missing")
    check("frozen benchmark v5" in text, "frozen benchmark section missing")
    check("Deep Analysis ölçüm paneli" in text, "deep panel missing")
    check("Dokümanlar arası" in text, "cross-document table missing")
    check("Sözlük" in text, "glossary missing")
    page.screenshot(path=str(outdir / "10-benchmark.png"), full_page=True)

    # --- doc switch: holdout (deep-only) ---
    page.select_option("#docsel", "arcelik-2024")
    page.wait_for_timeout(800)
    page.locator("#modetabs button[data-mode='presentation']").click()
    page.wait_for_timeout(500)
    # A method this document has no run for is one line under the row, not two
    # greyed cards: the absence is stated once, where it costs no attention.
    check(page.locator("#methods .method").count() == 2, "deep-only doc should show only the 2 methods it has")
    note = page.locator("#methodnote").inner_text()
    check("Markdown" in note and "Hybrid" in note, f"the two absent methods are not named: {note!r}")
    check(page.locator("#results .results").count() == 1, "results strip missing on the holdout doc")
    page.screenshot(path=str(outdir / "11-arcelik-sunum.png"), full_page=False)
    page.locator("#modetabs button[data-mode='benchmark']").click()
    page.wait_for_timeout(500)
    check("gold sorgu seti yok" in page.locator("#view-benchmark").inner_text(), "deep-only benchmark notice missing")
    check("Kalite özeti" in page.locator("#view-benchmark").inner_text(), "summary missing on the holdout doc")
    page.locator("#modetabs button[data-mode='query']").click()
    page.wait_for_timeout(500)
    check(page.locator("#qsubtabs button[data-sub='gold']").is_hidden(), "gold sub-tab should be hidden without gold")

    # --- the RAG console bridge: one button, and a dialog on demand ---
    page.locator("#modetabs button[data-mode='presentation']").click()
    page.wait_for_timeout(400)
    check(page.locator("#wsopen").is_visible(), "the console button is missing from the top bar")
    check(page.locator("#wspanel").count() == 0,
          "the workspace must not occupy the content area")
    page.locator("#wsopen").click()
    page.wait_for_selector("#modal .box", timeout=15000)
    dialog = page.locator("#modal .box").inner_text()
    check("RAG Console" in dialog, "the console dialog does not name the console")
    if live:
        check("bilgi taban" in dialog or "ba\u011flan\u0131lam" in dialog,
              f"the dialog reports neither counts nor a failure: {dialog[:120]!r}")
        page.screenshot(path=str(outdir / "13-workspace.png"), full_page=False)
    else:
        check("ba\u011flan\u0131lam" in dialog,
              "a standalone file cannot reach a console and must say so")
    page.locator("#mclose").click()
    page.wait_for_timeout(200)

    # --- responsive ---
    page.set_viewport_size({"width": 820, "height": 900})
    page.locator("#modetabs button[data-mode='presentation']").click()
    page.wait_for_timeout(400)
    width = page.evaluate("document.documentElement.scrollWidth")
    check(width <= 840, f"horizontal overflow at 820px: scrollWidth={width}")
    page.screenshot(path=str(outdir / "12-responsive-820.png"), full_page=False)
    browser.close()

report = {
    "target": target,
    "load_seconds": round(load_s, 2),
    "problems": problems,
    "console": console[:20],
    "screenshots": sorted(p.name for p in outdir.glob("*.png")),
}
print(json.dumps(report, ensure_ascii=False, indent=1))
sys.exit(1 if problems or any(c.startswith(("error", "pageerror")) for c in console) else 0)
