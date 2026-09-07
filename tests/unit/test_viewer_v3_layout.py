"""The Viewer v3 top bar, measured in a browser.

The bar carries one chip per *registered* chunking method, and the registry is
open: a method is added by writing a module and naming it in ``_BUILTIN``.
Every other group on the bar is fixed -- the brand, the knowledge-base and
document pickers, the five screen tabs, the difference walker and the page
picker -- so the only group that can grow without bound is the method lane.
The bar used to be one non-wrapping row, which meant a fifth method was enough
to push the screen tabs and the page controls off the right-hand edge at
1366px, where they cannot be clicked at all.

These tests build the real page, put an artificial method set into it (4, 6
and 12 -- no product method is named anywhere here) and measure the layout at
the desktop widths the product is used at, plus one narrower one that only has
to degrade gracefully. What they assert is the requirement rather than the
mechanism: nothing widens the document, every control is inside the viewport,
no two controls overlap, the bar clips nothing of its own, the tabs still
switch screens, the comparison controls still work, and every chip is
reachable.

They need a browser. ``pip install -e ".[smoke]" && python -m playwright
install chromium`` provides one; without it these skip, exactly like the
``tools/viewer_smoke.py`` whose machinery they share.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import pytest

sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright

from amsc import methods
from amsc.viewer_v3 import build_viewer

#: The desktop widths the product is used at, and one narrower layout.
WIDTHS = (1920, 1440, 1366, 1024)
#: Method counts, not method names. The point is that no count is special.
COUNTS = (4, 6, 12)

#: Every control on the bar a user has to be able to reach.
CONTROLS = (
    "#kbBtn", "#docBtn",
    '#tabs button[data-t="home"]', '#tabs button[data-t="incele"]',
    '#tabs button[data-t="sorgu"]', '#tabs button[data-t="debug"]',
    '#tabs button[data-t="bench"]',
    "#dPrev", "#dNext", "#pPrev", "#pSel", "#pNext",
)

#: Drive the page the way the page drives itself: an artificial registry of
#: ``n`` methods, a document carrying one arm per method (the fixture's own
#: arms, cycled, so the compared pair really does differ and the difference
#: walker is offered), and the Incele screen open with two methods compared.
STAGE = """
(n) => {
  const order = [], labels = {}, summaries = {}, meta = {};
  for (let i = 0; i < n; i++) {
    const key = "probe-" + i;
    order.push(key);
    labels[key] = "Yontem " + (i + 1);
    summaries[key] = "olcum icin";
    meta[key] = { kind: "probe_" + i, deep: false, baseline: null };
  }
  DATA.methodOrder = order;
  DATA.methodLabels = labels;
  DATA.methodSummaries = summaries;
  DATA.methodMeta = meta;
  deriveMethods();

  const source = DATA.docs[DATA.docOrder[0]];
  const armKeys = Object.keys(source.arms);
  const arms = {}, live = {};
  order.forEach((key, i) => {
    arms[key] = source.arms[armKeys[i % armKeys.length]];
    live[key] = { status: "ready" };
  });
  const doc = Object.assign({}, source, {
    arms: arms,
    live: { kbName: "Olcum tabani", methods: live },
  });

  S.kb = { name: "Olcum tabani", kind: "live" };
  S.doc = doc;
  S.mode = "incele";
  S.sel = order.slice(0, 2);
  S.page = doc.pages[0];
  buildRows();
  renderBar();
  return {
    chips: document.querySelectorAll("#chips .chip").length,
    diffs: S.diffs.length,
  };
}
"""

#: One measurement pass over the finished bar. Everything it returns is a fact
#: about boxes on the screen, so a failure names a control and a number.
MEASURE = """
(selectors) => {
  const bar = document.getElementById("bar");
  const lane = document.getElementById("chips");
  const box = (el) => {
    const r = el.getBoundingClientRect();
    return { x: r.left, y: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height };
  };
  const controls = {};
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    controls[sel] = el ? box(el) : null;
  }
  // Where each chip sits inside the lane's *scrollable content*: the lane is
  // not a positioned ancestor, so offsetLeft would be a page coordinate.
  const laneBox = lane.getBoundingClientRect();
  const chips = [...lane.querySelectorAll(".chip")].map((c) => {
    const r = c.getBoundingClientRect();
    const left = r.left - laneBox.left + lane.scrollLeft;
    return { left: left, right: left + r.width, width: r.width };
  });
  return {
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    bar: Object.assign(box(bar), {
      scrollH: bar.scrollHeight, clientH: bar.clientHeight,
      scrollW: bar.scrollWidth, clientW: bar.clientWidth,
    }),
    lane: Object.assign(box(lane), { scrollW: lane.scrollWidth, clientW: lane.clientWidth }),
    controls: controls,
    chips: chips,
  };
}
"""


@pytest.fixture(scope="module")
def page_file(tmp_path_factory):
    """The real page, built from the same synthetic tree the v3 tests use."""
    from _viewer_fixtures import make_tree

    root = tmp_path_factory.mktemp("layout")
    tree = make_tree(root)
    output = root / "v3" / "index.html"
    build_viewer({"doc": tree}, output, root=root)
    return output.resolve()


@pytest.fixture(scope="module")
def page_url(page_file):
    return page_file.as_uri()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as play:
        launched = play.chromium.launch()
        yield launched
        launched.close()


def _overlaps(a, b) -> bool:
    """Do two boxes share area? Rounded, because adjacent borders touch."""
    return (round(a["x"]) < round(b["r"]) - 1 and round(b["x"]) < round(a["r"]) - 1
            and round(a["y"]) < round(b["b"]) - 1 and round(b["y"]) < round(a["b"]) - 1)


def _measure(browser, url, width, count):
    page = browser.new_page(viewport={"width": width, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(url, wait_until="load", timeout=60000)
        staged = page.evaluate(STAGE, count)
        assert staged["chips"] == count, f"{count} methods rendered {staged['chips']} chips"
        assert staged["diffs"] > 0, "the staged pair must differ, or the walker is not on the bar"
        measured = page.evaluate(MEASURE, list(CONTROLS))
        assert not errors, errors
        return measured
    finally:
        page.close()


@pytest.fixture(scope="module")
def measurements(browser, page_url):
    return {
        (width, count): _measure(browser, page_url, width, count)
        for width in WIDTHS
        for count in COUNTS
    }


@pytest.mark.parametrize("count", COUNTS)
@pytest.mark.parametrize("width", WIDTHS)
def test_no_method_count_makes_the_page_scroll_sideways(measurements, width, count):
    """A bar that does not fit wraps; it never widens the document."""
    m = measurements[(width, count)]
    assert m["scrollWidth"] <= m["innerWidth"] + 1, (
        f"{count} methods at {width}px push the page "
        f"{m['scrollWidth'] - m['innerWidth']}px wide"
    )
    assert m["bar"]["scrollW"] <= m["bar"]["clientW"] + 1, "the bar itself overflows sideways"


@pytest.mark.parametrize("count", COUNTS)
@pytest.mark.parametrize("width", WIDTHS)
def test_every_top_bar_control_stays_inside_the_viewport(measurements, width, count):
    """Document navigation, the five screen tabs, the difference walker and the
    page picker: each one drawn, and each one inside the window."""
    m = measurements[(width, count)]
    for selector, rect in m["controls"].items():
        assert rect is not None, f"{selector} is not on the page at all"
        assert rect["w"] > 0 and rect["h"] > 0, f"{selector} collapsed at {width}px/{count}"
        assert rect["x"] >= -1, f"{selector} starts {-rect['x']:.0f}px off the left edge"
        assert rect["r"] <= m["innerWidth"] + 1, (
            f"{selector} runs {rect['r'] - m['innerWidth']:.0f}px past the right edge "
            f"at {width}px with {count} methods"
        )


@pytest.mark.parametrize("count", COUNTS)
@pytest.mark.parametrize("width", WIDTHS)
def test_no_two_top_bar_controls_overlap(measurements, width, count):
    """Overlap is what "cramped" actually was: two controls in one place, and
    whichever is underneath cannot be clicked."""
    m = measurements[(width, count)]
    items = [(name, rect) for name, rect in m["controls"].items() if rect]
    for index, (name, rect) in enumerate(items):
        for other_name, other in items[index + 1:]:
            assert not _overlaps(rect, other), (
                f"{name} and {other_name} overlap at {width}px with {count} methods"
            )


@pytest.mark.parametrize("count", COUNTS)
@pytest.mark.parametrize("width", WIDTHS)
def test_the_bar_grows_instead_of_clipping_its_contents(measurements, width, count):
    """Whatever ends up on the bar is inside the bar: the design height is a
    minimum, not a lid."""
    m = measurements[(width, count)]
    assert m["bar"]["scrollH"] <= m["bar"]["clientH"] + 1, (
        f"the bar clips {m['bar']['scrollH'] - m['bar']['clientH']}px of its own content"
    )
    assert m["bar"]["h"] >= 58, "the bar is shorter than the design height"


@pytest.mark.parametrize("count", COUNTS)
@pytest.mark.parametrize("width", WIDTHS)
def test_every_method_chip_is_reachable(measurements, width, count):
    """The lane may scroll. What it may not do is put a chip where no amount of
    scrolling reaches it, or collapse to nothing."""
    m = measurements[(width, count)]
    assert len(m["chips"]) == count
    lane = m["lane"]
    assert lane["clientW"] > 60, f"the method lane collapsed to {lane['clientW']}px"
    for index, chip in enumerate(m["chips"]):
        assert chip["width"] > 0, f"chip {index} has no width"
        assert chip["right"] <= lane["scrollW"] + 1, (
            f"chip {index} sits past the scrollable extent of the lane"
        )
    assert lane["r"] <= m["innerWidth"] + 1, "the method lane runs past the right edge"


def test_the_screen_tabs_still_switch_screens_with_a_large_method_set(browser, page_url):
    """Reaching a control is not the same as it working: the narrowest layout
    with the largest method set clicks all five."""
    page = browser.new_page(viewport={"width": 1024, "height": 900})
    try:
        page.goto(page_url, wait_until="load", timeout=60000)
        page.evaluate(STAGE, 12)
        for mode in ("home", "sorgu", "debug", "bench", "incele"):
            page.click(f'#tabs button[data-t="{mode}"]')
            page.wait_for_timeout(60)
            assert page.evaluate("() => S.mode") == mode, f"the {mode} tab did not switch"
    finally:
        page.close()


def test_the_comparison_controls_still_work_with_a_large_method_set(browser, page_url):
    """Page selection and Fark navigation, at the tightest desktop width with
    twelve methods on the bar."""
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    try:
        page.goto(page_url, wait_until="load", timeout=60000)
        page.evaluate(STAGE, 12)
        pages = page.evaluate("() => S.doc.pages")
        assert len(pages) > 1, "the fixture document needs more than one page"
        page.click("#pNext")
        assert page.evaluate("() => S.page") == pages[1], "the page picker did not advance"
        page.click("#pPrev")
        assert page.evaluate("() => S.page") == pages[0]
        assert page.evaluate("() => !document.getElementById('dGrp').hidden")
        page.click("#dNext")
        assert page.evaluate("() => S.diffIdx") >= 0, "the difference walker did not move"
    finally:
        page.close()


def test_a_chip_stays_clickable_when_the_lane_has_to_scroll(browser, page_url):
    """The last chip of a twelve-method set, at 1366px: scrolled into view and
    clicked, and the page takes it as a method selection."""
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    try:
        page.goto(page_url, wait_until="load", timeout=60000)
        page.evaluate(STAGE, 12)
        last = page.locator("#chips .chip").last
        last.scroll_into_view_if_needed()
        last.click()
        assert "probe-11" in page.evaluate("() => S.sel"), "the last chip did not select"
    finally:
        page.close()


def test_the_top_bar_layout_names_no_method_and_counts_none(page_file):
    """The layout must not learn a method's name, or how many there are."""
    html = page_file.read_text(encoding="utf-8")
    style = html.split("</style>")[0]
    for key in methods.order():
        assert f'[data-m="{key}"]' not in style, f"the stylesheet singles out {key!r}"
    # Nothing in the bar's own rules selects an nth chip, which is the other
    # way a method count gets baked into a layout.
    bar_rules = [line for line in style.splitlines()
                 if line.startswith(("#chips", ".chip", "#bar", "#tabs"))]
    assert bar_rules, "the top bar rules moved; this test no longer reads them"
    assert not [line for line in bar_rules if "nth-child" in line or "nth-of-type" in line], (
        "the bar counts its own children: " + json.dumps(bar_rules)
    )
