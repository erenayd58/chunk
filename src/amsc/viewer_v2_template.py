"""The Viewer v2 page: markup, styles and behaviour, as one template string.

Kept apart from :mod:`amsc.viewer_v2` so the loader reads like Python and
the page reads like a page. ``__VIEWER_DATA__`` is replaced with the JSON
payload at build time; nothing else is templated -- every number the page
shows is read from that payload at runtime, never written into the markup.
"""

TEMPLATE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AMSC Chunking Viewer v2</title>
<style>
:root{
  --bg:#f3f5f8; --surface:#ffffff; --well:#f8fafc; --well-2:#eef2f6;
  --ink:#0f172a; --ink-2:#334155; --muted:#64748b; --faint:#94a3b8;
  --line:#e2e8f0; --line-2:#cbd5e1;
  --accent:#1d4ed8; --accent-ink:#1e40af; --accent-soft:#e8effc; --accent-line:#bfd0f5;
  --deep:#6d28d9; --deep-ink:#5b21b6; --deep-soft:#f1ebfd; --deep-line:#d8c8f7;
  --good:#047857; --good-soft:#e2f4ec; --warn:#b45309; --warn-soft:#fdf1dc; --bad:#b91c1c; --bad-soft:#fdeceb;
  --amber:#b45309; --teal:#0f766e;
  --tintA:#eef4ff; --tintB:#fdf7e9; --mark:#fde68a;
  --font:"Segoe UI Variable Text","Segoe UI",Inter,system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;
  --serif:Georgia,"Times New Roman",serif;
  --mono:"Cascadia Code","Cascadia Mono",Consolas,Menlo,monospace;
  --r:10px; --r-sm:7px;
  --shadow:0 1px 2px rgba(15,23,42,.04),0 1px 3px rgba(15,23,42,.06);
  --shadow-lg:0 14px 36px rgba(15,23,42,.16);
  --barh:60px;
  --paper:var(--bg); --panel:var(--surface); --line-strong:var(--line-2);
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-padding-top:calc(var(--barh) + 16px)}
html,body{background:var(--bg);color:var(--ink);font:15px/1.55 var(--font);-webkit-font-smoothing:antialiased}
button{font:inherit;color:inherit;background:none;border:none;cursor:pointer}
button:focus-visible,select:focus-visible,textarea:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
select,textarea,input[type=text]{font:inherit;color:inherit;padding:7px 11px;border:1px solid var(--line-2);border-radius:var(--r-sm);background:#fff}
select{appearance:none;-webkit-appearance:none;padding-right:30px;cursor:pointer;
  background:#fff url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M3 4.5l3 3 3-3' fill='none' stroke='%2364748b' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") no-repeat right 10px center}
a{color:var(--accent)}
b,strong{font-weight:650}
.hidden{display:none!important}
.muted{color:var(--muted)}
.mono{font-family:var(--mono);font-size:13px}
.nowrap{white-space:nowrap}

/* ---- app header: brand, the four screens, the document, the console ---- */
.topbar{position:sticky;top:0;z-index:40;background:rgba(255,255,255,.96);backdrop-filter:blur(8px);
  border-bottom:1px solid var(--line);padding:0 28px;display:flex;gap:26px;align-items:center;flex-wrap:wrap;min-height:var(--barh)}
.brand{display:flex;align-items:center;gap:10px;font-weight:650;font-size:15.5px;letter-spacing:-.1px;white-space:nowrap}
.brand .mark{width:28px;height:28px;border-radius:8px;background:linear-gradient(135deg,#1e3a8a,#2563eb);color:#fff;
  display:inline-flex;align-items:center;justify-content:center;font-size:14px;font-weight:700}
.brand small{color:var(--muted);font-weight:500;font-size:13.5px}
.brand .tag{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);
  border:1px solid var(--line-2);border-radius:5px;padding:1px 6px}
.tabs{display:flex;gap:2px;align-self:stretch}
.tabs button{padding:0 14px;color:var(--muted);font-weight:600;font-size:15px;border-bottom:2px solid transparent;
  margin-bottom:-1px;transition:color .12s}
.tabs button:hover{color:var(--ink)}
.tabs button.on{color:var(--accent-ink);border-bottom-color:var(--accent)}
.bar-right{margin-left:auto;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.docpick{display:inline-flex;align-items:stretch;border:1px solid var(--line-2);border-radius:8px;background:#fff;overflow:hidden}
.docpick .lab{padding:0 10px 0 12px;font-size:11.5px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;
  border-right:1px solid var(--line);display:flex;align-items:center;background:var(--well)}
.docpick select{border:none;border-radius:0;font-weight:600;min-width:210px;max-width:380px;padding:7px 30px 7px 10px}
.docpick select:focus-visible{outline-offset:-2px}
main{max-width:1720px;margin:0 auto;padding:22px 28px 48px}

/* ---- page head: the same three answers on every screen ---- */
.pagehead{display:flex;align-items:flex-end;justify-content:space-between;gap:16px 28px;flex-wrap:wrap;
  margin-bottom:24px;padding-bottom:18px;border-bottom:1px solid var(--line)}
.pagehead .ph-main{min-width:0;max-width:860px}
.pagehead .eyebrow{font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:6px}
.pagehead h1{font-size:26px;font-weight:650;letter-spacing:-.4px;line-height:1.2}
.pagehead .lead{font-size:14.5px;line-height:1.5;color:var(--muted);margin-top:6px}
.pagehead .facts{display:flex;gap:8px 12px;align-items:center;flex-wrap:wrap;font-size:13.5px;color:var(--ink-2);padding-bottom:3px}
.pagehead .facts>span:not(.pill){display:inline-flex;align-items:center;gap:7px}
.pagehead .facts>span:not(.pill)::before{content:"";width:4px;height:4px;border-radius:50%;background:var(--faint)}

/* ---- shared surfaces ---- */
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px;box-shadow:var(--shadow)}
.cards{display:flex;gap:12px;flex-wrap:wrap}
.stat{min-width:150px}
.stat .v{font-size:26px;font-weight:650;font-variant-numeric:tabular-nums;line-height:1.15;letter-spacing:-.3px}
.stat .v small{font-size:14px;font-weight:500;color:var(--muted);margin-left:4px}
.stat .k{color:var(--muted);font-size:13.5px;margin-top:5px;line-height:1.35}
.stat.deep .v{color:var(--deep)}
.stat.good .v{color:var(--good)}
.pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:2px 10px;font-size:12.5px;font-weight:600;
  white-space:nowrap;line-height:1.5}
.pill.ok{background:var(--good-soft);color:var(--good)}
.pill.mid{background:var(--warn-soft);color:var(--warn)}
.pill.miss{background:var(--bad-soft);color:var(--bad)}
.pill.deep{background:var(--deep-soft);color:var(--deep-ink)}
.pill.std{background:var(--accent-soft);color:var(--accent-ink)}
.pill.grey{background:var(--well-2);color:var(--ink-2)}
.chip{font:12.5px/1.5 var(--mono);background:var(--well-2);border-radius:5px;padding:1px 7px;color:var(--ink-2)}
.chip.role{background:var(--deep-soft);color:var(--deep-ink)}
.chip.opens{background:var(--good-soft);color:var(--good)}
.chip.noopen{background:var(--bad-soft);color:var(--bad)}
.chip.big{background:var(--bad-soft);color:var(--bad)}
.chip.pf{background:var(--warn-soft);color:var(--warn)}
.note{color:var(--muted);font-size:14px;line-height:1.55;max-width:1040px}
.guard{border-left:3px solid var(--accent);background:var(--accent-soft);padding:11px 16px;
  border-radius:0 var(--r-sm) var(--r-sm) 0;font-size:14.5px;line-height:1.55;margin:12px 0 4px;max-width:1040px}
.guard.deep{border-left-color:var(--deep);background:var(--deep-soft)}
.guard.warn{border-left-color:var(--warn);background:var(--warn-soft)}
h2.sec{margin:30px 0 10px;font-size:19px;font-weight:650;letter-spacing:-.2px}
h3.sub{margin:18px 0 8px;font-size:16px;font-weight:650}
details.adv{margin-top:10px}
details.adv summary{cursor:pointer;color:var(--accent);font-size:14px;font-weight:500}
details.adv pre{white-space:pre-wrap;font:12.5px/1.5 var(--mono);background:var(--well);border:1px solid var(--line);
  border-radius:var(--r-sm);padding:10px 12px;margin-top:8px;max-height:320px;overflow:auto}
table.t{border-collapse:separate;border-spacing:0;background:var(--surface);font-variant-numeric:tabular-nums;font-size:14px;
  border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
table.t th,table.t td{padding:9px 14px;text-align:right;border-bottom:1px solid var(--line)}
table.t tr:last-child td{border-bottom:none}
table.t th:first-child,table.t td:first-child{text-align:left}
table.t th{background:var(--well);font-weight:600;font-size:12.5px;letter-spacing:.03em;color:var(--ink-2);white-space:nowrap}
table.t td.best{font-weight:700;color:var(--accent-ink)}
table.t td.best::after{content:" \25CF";font-size:8px;vertical-align:2px}
table.t td.deepcol{background:#faf8ff}
.scrollx{overflow-x:auto;max-width:100%}
.btn{border:1px solid var(--line-2);border-radius:8px;padding:7px 14px;background:#fff;font-weight:600;font-size:14px;color:var(--ink);
  display:inline-flex;align-items:center;gap:7px;text-decoration:none;transition:background .12s,border-color .12s}
.btn:hover{background:var(--well);border-color:var(--faint)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{background:var(--accent-ink)}
.btn.deep{background:var(--deep);border-color:var(--deep);color:#fff}
.btn:disabled{opacity:.5;cursor:default}
.btn.small{padding:5px 11px;font-size:13px}
.linkbtn{color:var(--accent);font-weight:600;padding:0}
.linkbtn:hover{text-decoration:underline}

/* ---- section heads: numbered, so the story reads in order ---- */
.sechead{margin:30px 0 12px;max-width:1040px}
.sechead:first-child,.results:empty + .sechead{margin-top:0}
.sechead h2{font-size:19px;font-weight:650;letter-spacing:-.2px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.sechead .lead{color:var(--muted);font-size:14.5px;line-height:1.5;margin-top:4px}
.sechead .step{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:7px;
  background:var(--ink);color:#fff;font-size:12.5px;font-weight:700;flex:0 0 auto}
.help{color:var(--muted);font-size:13.5px;line-height:1.5;margin-top:6px}
.info{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:999px;
  border:1px solid var(--line-2);color:var(--muted);font-size:10.5px;font-weight:700;cursor:pointer;line-height:1;
  vertical-align:1px;margin-left:5px;font-family:var(--font);user-select:none;padding:0;flex:0 0 auto}
.info:hover,.info.on{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}
.tip{position:fixed;z-index:90;background:#0f172a;color:#f1f5f9;border-radius:9px;padding:10px 13px;
  font:13.5px/1.5 var(--font);box-shadow:var(--shadow-lg);pointer-events:none;max-width:340px}
.techname{font-family:var(--mono);font-size:12px;color:var(--muted);font-weight:400;text-transform:none;letter-spacing:0}

/* ---- Sunum: the result band ---- */
.results{margin:0}
.results.legacy{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:14px 18px;box-shadow:var(--shadow)}
.results .title{font-weight:650;display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.results .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.results .item .v{font-size:23px;font-weight:650;font-variant-numeric:tabular-nums}
.results .item .k{font-size:13px;color:var(--muted);line-height:1.35}
.hero{position:relative;overflow:hidden;color:#eef0fb;border-radius:14px;padding:22px 28px 22px;max-width:1480px;
  background:linear-gradient(120deg,#171c46 0%,#232a6b 55%,#3b2a8f 100%);box-shadow:0 10px 30px rgba(23,28,70,.22)}
.hero::after{content:"";position:absolute;right:-140px;top:-160px;width:460px;height:460px;border-radius:50%;
  background:radial-gradient(closest-side,rgba(255,255,255,.10),transparent)}
.hero.flat{background:linear-gradient(120deg,#1f2937 0%,#334155 60%,#475569 100%);box-shadow:0 10px 30px rgba(31,41,55,.18)}
.hero>*{position:relative}
.hero-head{display:flex;align-items:flex-start;gap:14px;flex-wrap:wrap;margin-bottom:18px}
.hero-doc{font-size:13px;font-weight:700;letter-spacing:.02em;color:#b9c0ee}
.hero.flat .hero-doc{color:#b8c1d1}
.hero-facts{font-size:13px;color:#9ea6dd;display:flex;gap:9px;flex-wrap:wrap;margin-top:5px;font-family:var(--mono)}
.hero.flat .hero-facts{color:#9aa5b8}
.hero-badge{margin-left:auto;display:flex;gap:7px;flex-wrap:wrap}
.hero-badge .pill{background:rgba(255,255,255,.14);color:#fff;border:1px solid rgba(255,255,255,.18)}
.hero-nums{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px 28px}
.hero-nums .n{min-width:0;padding-left:16px;border-left:2px solid rgba(255,255,255,.14)}
.hero-nums .n:first-child{padding-left:0;border-left:none}
.hero-nums .v{font-size:38px;font-weight:650;line-height:1.05;letter-spacing:-.6px;font-variant-numeric:tabular-nums;
  display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
.hero-nums .v .from{color:#9ea6dd;font-size:26px;font-weight:600}
.hero-nums .v .arrow{color:#9ea6dd;font-size:22px;font-weight:400}
.hero-nums .v .to{color:#fff}
.hero.flat .v .from,.hero.flat .v .arrow{color:#94a3b8}
.hero-nums .k{font-size:13.5px;color:#c9cef2;margin-top:6px;display:flex;align-items:center;gap:2px;flex-wrap:wrap}
.hero.flat .hero-nums .k{color:#cbd5e1}
.hero-nums .k .info{border-color:rgba(255,255,255,.4);color:#e7e9fb}
.hero-nums .k .info:hover,.hero-nums .k .info.on{background:rgba(255,255,255,.16);border-color:#fff;color:#fff}
.hero-nums .sub{font-size:13px;color:#a9b0e3;margin-top:3px}
.hero.flat .hero-nums .sub{color:#aab4c4}
.hero-nums .gain{display:inline-block;margin-top:7px;border-radius:999px;padding:2px 10px;font-size:12.5px;
  font-weight:650;background:rgba(74,222,128,.18);color:#86efac}
.hero-line{margin-top:18px;padding-top:14px;border-top:1px solid rgba(255,255,255,.14);font-size:15px;line-height:1.5;color:#dfe2f7}
.hero.flat .hero-line{color:#d7dde8}
.hero-line b{color:#fff;font-weight:650}
.guards{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-top:12px}
.guards .g{border-left:3px solid var(--line-2);padding:2px 0 2px 14px;font-size:14px;line-height:1.5;color:var(--ink-2)}
.guards .g b{color:var(--ink);font-weight:650;display:block;margin-bottom:2px}
.guards .g.llm{border-left-color:var(--deep)}
.guards .g.rule{border-left-color:var(--good)}
.when{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px 26px;margin-top:14px;
  border-left:3px solid var(--line-2);padding:2px 0 2px 16px;max-width:1480px}
.when .w{font-size:13.5px;line-height:1.5;color:var(--muted)}
.when .w b{display:block;color:var(--ink-2);font-weight:650;font-size:13.5px;margin-bottom:2px}

/* ---- what improved: one row per defect, Standard above Deep on one scale ---- */
.fixlist{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:4px 20px 10px;margin-top:8px;
  box-shadow:var(--shadow);max-width:1480px}
.fixrow{display:grid;grid-template-columns:minmax(190px,300px) minmax(140px,1fr) 118px;gap:20px;align-items:center;
  padding:8px 0;border-bottom:1px solid var(--well-2)}
.fixrow:last-child{border-bottom:none}
.fixrow.flat{opacity:.7}
.fixrow .name{font-size:14px;font-weight:600;min-width:0}
.fixrow .bars{display:flex;flex-direction:column;gap:3px;min-width:0}
.fixrow .b{height:8px;border-radius:4px;background:var(--well-2);position:relative}
.fixrow .b i{position:absolute;left:0;top:0;bottom:0;border-radius:4px}
.fixrow .b.std i{background:#9db4e8}
.fixrow .b.deep i{background:var(--deep)}
.fixrow.gone .b.deep i{background:var(--good)}
.fixrow .n{text-align:right;font-variant-numeric:tabular-nums;font-size:14.5px;white-space:nowrap;font-weight:600}
.fixrow .n .to{color:var(--deep)}
.fixrow.gone .n .to{color:var(--good)}
.fixrow .n .kept{color:var(--muted);font-weight:500}
.fixrow .n small{display:block;font-size:12px;font-weight:500;color:var(--muted);margin-top:2px}
.fixhead{display:grid;grid-template-columns:minmax(190px,300px) minmax(140px,1fr) 118px;gap:20px;
  padding:10px 0 8px;font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:700;
  border-bottom:1px solid var(--line)}
.fixhead .legend2{display:flex;gap:16px;text-transform:none;letter-spacing:0;font-size:12.5px;font-weight:500}
.fixhead .legend2 span{display:flex;align-items:center;gap:6px}
.fixhead .swatch{width:16px;height:8px;border-radius:4px;display:inline-block}

/* ---- Sunum: the methods this document actually has ---- */
.methods{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;max-width:1480px}
.method{--c:var(--line-2);--c-soft:var(--well-2);background:var(--surface);border:1px solid var(--line);border-radius:var(--r);
  padding:15px 16px 13px;cursor:pointer;position:relative;box-shadow:var(--shadow);transition:box-shadow .12s,border-color .12s}
.method::before{content:"";position:absolute;left:14px;right:14px;top:-1px;height:3px;border-radius:0 0 3px 3px;background:var(--c)}
.method:hover{box-shadow:0 4px 14px rgba(15,23,42,.08);border-color:var(--line-2)}
.method.on{border-color:var(--c);box-shadow:0 0 0 2px var(--c-soft)}
.method .name{font-weight:650;font-size:15.5px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.method .desc{color:var(--ink-2);font-size:14px;margin-top:6px;line-height:1.5;min-height:42px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.method .facts{color:var(--muted);font-size:13px;margin-top:10px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.method .inlane{flex-basis:100%;text-align:right;font-size:12.5px;font-weight:600;color:var(--c);white-space:nowrap;margin-top:2px}
.method .inlane.add{color:var(--faint)}
.method:hover .inlane.add{color:var(--c)}
.method.aside{background:var(--well)}
.method.aside .name{font-weight:600}
.method.aside .desc{color:var(--muted)}
#results,#methodhead,#methodnote{max-width:1480px}
#methodnote .help{margin-top:8px}

/* ---- the comparison workspace: the first screen of Sunum ----
   One column per selected method, in the order the reader picked them. The
   paragraph is the atom: every column prints the same paragraphs into the
   same grid rows, so a line of text sits at the same height in all of them
   and only the boundaries move. A chunk is a card: it opens on a boundary
   row carrying its number and its reason, runs through the paragraph rows
   it owns, and closes on the next boundary row. Where one column opens a
   card and another runs straight through, that place is a divergence.

   Two rules keep the alignment exact:
     - the board is one grid, so a "row" is a run of sibling cells, not an
       element: the row's state travels on every cell of the row;
     - a row is drawn the same way in every column. If one method cuts
       inside a paragraph, that paragraph is drawn as plain text in ALL
       columns, so no column can be taller than its neighbours.
   Method colour is never used for the divergence chrome -- the methods own
   blue, violet, amber and teal, so "you are here" is drawn in ink. */
.pagehead.compact{margin-bottom:14px;padding-bottom:12px;align-items:center}
.pagehead.compact .ph-main{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.pagehead.compact .eyebrow{margin:0}
.pagehead.compact h1{font-size:22px}

/* the toolbar: which methods are columns, which divergence, which page */
.cmpbar{background:var(--surface);border:1px solid var(--line);border-bottom:none;border-radius:var(--r) var(--r) 0 0;
  padding:10px 16px 9px;display:flex;flex-direction:column;gap:8px}
.cmpbar .row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:13.5px;color:var(--muted)}
.cmpbar .title{display:flex;align-items:center;gap:10px;font-weight:650;font-size:16px;color:var(--ink);margin-right:8px}
.cmpbar .title .step{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:7px;
  background:var(--ink);color:#fff;font-size:12.5px;font-weight:700}
.cmpbar .lab{font-size:11.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.cmpbar select{padding:5px 30px 5px 10px;font-size:13.5px;max-width:420px}
.cmpbar .sep{width:1px;height:22px;background:var(--line)}
.cmpbar .grow{margin-left:auto;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.lanechip{--c:var(--faint);--c-soft:var(--well-2);border:1px solid var(--line-2);border-radius:999px;padding:4px 13px 4px 5px;background:#fff;
  font-size:14px;font-weight:600;color:var(--ink-2);display:inline-flex;align-items:center;gap:7px;transition:border-color .12s,background .12s}
.lanechip:hover{border-color:var(--c)}
.lanechip .dot{width:10px;height:10px;border-radius:3px;background:var(--c);flex:0 0 auto;margin-left:5px}
/* the chip carries its column position, so "the first method I picked" and
   "the left column" are visibly the same thing */
.lanechip .ord{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:6px;
  background:var(--c);color:#fff;font-size:11.5px;font-weight:700;flex:0 0 auto}
.lanechip.on{border-color:var(--c);background:var(--c-soft);color:var(--c)}
.lanechip.off{opacity:.5;cursor:not-allowed;border-style:dashed;padding-left:13px}
.lanechip .n{font-weight:400;font-size:12.5px;opacity:.8}
.stepnav{display:inline-flex;gap:4px;align-items:center}
.stepnav button{border:1px solid var(--line-2);border-radius:7px;padding:4px 11px;background:#fff;color:var(--ink-2);line-height:1.3}
.stepnav button:hover{background:var(--well)}
.stepnav button:disabled{opacity:.4;cursor:default;background:#fff}
.diffstep{display:inline-flex;align-items:center;gap:8px}
.diffstep .count{font-weight:650;color:var(--ink);font-variant-numeric:tabular-nums;white-space:nowrap}
.diffstep .count.none{font-weight:500;color:var(--muted)}
.conttoggle{display:flex;align-items:center;gap:6px;font-size:13.5px;color:var(--muted);cursor:pointer;white-space:nowrap}
/* the text-density switch: full paragraphs, or the first lines of each */
.seg2{display:inline-flex;border:1px solid var(--line-2);border-radius:7px;overflow:hidden}
.seg2 button{padding:3px 11px;font-size:13px;color:var(--muted);background:#fff;line-height:1.4}
.seg2 button+button{border-left:1px solid var(--line-2)}
.seg2 button.on{background:var(--ink);color:#fff;font-weight:600}
.sonuc{border:1px solid var(--deep-line);background:var(--deep-soft);color:var(--deep-ink);border-radius:999px;padding:4px 12px;
  font-size:13px;font-weight:600;white-space:nowrap}
.sonuc:hover{background:#e6dcfb}

/* the readout: the divergence the reader is standing on, said in words */
.dvsum{background:var(--surface);border:1px solid var(--line);border-bottom:none;padding:9px 16px;
  display:flex;gap:8px 16px;align-items:baseline;flex-wrap:wrap;font-size:13.5px;color:var(--ink-2)}
.dvsum .ix{background:var(--ink);color:#fff;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:700;
  font-variant-numeric:tabular-nums;white-space:nowrap}
.dvsum .pg{color:var(--muted);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:360px}
.dvsum .ent{display:inline-flex;align-items:baseline;gap:7px;min-width:0}
.dvsum .ent .dot{width:9px;height:9px;border-radius:3px;background:var(--c);flex:0 0 auto;align-self:center}
.dvsum .ent b{color:var(--ink);font-weight:650;white-space:nowrap}
.dvsum .verb{font-weight:650;white-space:nowrap}
.dvsum .verb.cut{color:var(--c)}
.dvsum .verb.kept{color:var(--muted)}
.dvsum .m{color:var(--muted);font-size:12.5px;white-space:nowrap}
.dvsum .dec{flex-basis:100%;color:var(--muted);font-size:13px;line-height:1.45}
.dvsum .dec b{color:var(--deep-ink);font-weight:650}
.dvsum .dec i{font-style:normal;color:var(--ink-2)}
.dvsum.quiet{color:var(--muted)}

.stage{display:grid;grid-template-columns:26px minmax(0,1fr) 320px;grid-template-rows:minmax(0,1fr);height:640px;background:var(--surface);
  border:1px solid var(--line);border-radius:0 0 var(--r) var(--r);box-shadow:var(--shadow);overflow:hidden;margin-bottom:26px}
.docmap{border-right:1px solid var(--line);background:var(--well);position:relative;cursor:pointer}
.docmap svg{display:block;width:100%;height:100%}

/* the board itself. No smooth scrolling: it is positioned in one step when a
   divergence is chosen, and an animation only fights the next click. */
.board{--colmin:260px;overflow:auto;min-width:0;min-height:0;position:relative;display:grid;
  grid-template-columns:34px repeat(var(--n,2),minmax(var(--colmin),1fr));
  align-content:start;background:var(--well);scroll-padding-top:44px}
.board .empty{grid-column:1/-1;padding:40px 24px;color:var(--muted);font-size:14.5px;line-height:1.6;max-width:620px}

/* the index column: page marks, divergence numbers, row controls. Sticky on
   the inline axis so four columns can scroll sideways without losing it. */
.gut{background:var(--well);border-right:1px solid var(--line);display:flex;flex-direction:column;
  align-items:center;gap:3px;padding:2px 2px 0;min-width:0;position:sticky;left:0;z-index:2}
.gut .pg{font-size:10px;font-weight:700;color:var(--faint);letter-spacing:.02em;white-space:nowrap}
.gut .dvchip{width:24px;border-radius:6px;background:#fff;border:1px solid var(--line-2);color:var(--muted);
  font:700 11px/17px var(--font);font-variant-numeric:tabular-nums;text-align:center;margin-top:8px;padding:0}
.gut .dvchip:hover{border-color:var(--ink);color:var(--ink)}
.gut.here .dvchip{background:var(--ink);border-color:var(--ink);color:#fff}
.gut .tall{width:22px;height:20px;border-radius:6px;border:1px solid var(--line-2);background:#fff;color:var(--faint);
  font-size:11px;line-height:18px;text-align:center;padding:0}
.gut .tall:hover{color:var(--accent);border-color:var(--accent)}

/* the sticky column heads */
.colhead{position:sticky;top:0;z-index:3;background:rgba(255,255,255,.97);backdrop-filter:blur(6px);
  border-bottom:1px solid var(--line);border-top:2px solid var(--c);padding:7px 12px;
  display:flex;align-items:center;gap:8px;min-width:0}
.colhead.gut{padding:7px 2px;background:rgba(248,250,252,.97);flex-direction:row;justify-content:center;
  border-top:2px solid var(--line);z-index:5}
.colhead .dot{width:10px;height:10px;border-radius:3px;background:var(--c);flex:0 0 auto}
.colhead .nm{font-weight:650;font-size:14px;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.colhead .n{font-size:12.5px;color:var(--muted);white-space:nowrap}
.colhead .drop{margin-left:auto;color:var(--faint);font-size:16px;line-height:1;padding:0 4px;border-radius:5px;flex:0 0 auto}
.colhead .drop:hover{color:var(--bad);background:var(--bad-soft)}

/* every cell of a column. The card's ground is the cell's own padding, so
   the break between two chunks is a real gap, not a drawn line. */
.cell{min-width:0;padding:0 9px;background:var(--well);--cl:var(--line-2);--cle:var(--line)}
/* The two chunks that meet at the current divergence carry their method's
   colour on the spine. They can run for ten paragraphs, so the ground stays
   white: a tint that large stops meaning "look here". */
.cell.foc{--cl:var(--c);--cle:color-mix(in srgb,var(--c) 34%,#fff)}
/* a paragraph row */
.cell.ur > .ck{background:#fff;border-left:3px solid var(--cl);border-right:1px solid var(--cle);
  position:relative;padding:3px 12px 3px 11px}
.cell.ur.alt > .ck{background:#fbfcfe}
.cell.ur.sel > .ck{background:var(--c-soft)}
.cell.ur.none > .ck{border-left-style:dashed;background:var(--well-2)}
.cell.ur.evflash > .ck{outline:3px solid var(--warn);outline-offset:-3px}
.cell.ur.clip > .ck{max-height:var(--cliph,150px);overflow:hidden}
.cell.ur.clip > .ck::after{content:"";position:absolute;left:0;right:0;bottom:0;height:40px;
  background:linear-gradient(to bottom,rgba(255,255,255,0),#fff)}
.cell.ur.alt.clip > .ck::after{background:linear-gradient(to bottom,rgba(251,252,254,0),#fbfcfe)}
.cell .miss{font-size:11.5px;color:var(--faint);padding:3px 0}
.board .body{font-family:var(--serif);font-size:14.5px;line-height:1.55;color:var(--ink);
  overflow-wrap:anywhere;max-width:680px}
.board .body.pre{white-space:pre-wrap}
/* No leading or trailing margin inside a cell: a heading's own margin would
   collapse through the body and drop that column 12px below a neighbour
   that has no chunk for the same paragraph. */
.board .body > :first-child{margin-top:0}
.board .body > :last-child{margin-bottom:0}
.board .cell.ctx .body{color:var(--faint)}
/* a boundary row: the card that ends closes, the card that starts opens */
.cell.bd > .close{height:9px;background:#fff;border-left:3px solid var(--cl);border-right:1px solid var(--cle);
  border-bottom:1px solid var(--cle);border-radius:0 0 9px 9px}
.cell.bd > .close.dash{border-bottom-style:dashed}
.cell.bd > .gap{height:10px}
.cell.bd > .open{width:100%;text-align:left;background:#fff;border-left:3px solid var(--cl);border-right:1px solid var(--cle);
  border-top:1px solid var(--cle);border-radius:9px 9px 0 0;padding:6px 10px 6px 9px;
  display:flex;gap:8px;align-items:baseline;flex-wrap:nowrap;min-width:0}
.cell.bd > .open:hover{background:var(--well)}
.cell.bd.sel > .open{background:var(--c-soft)}
.cell.bd > .open.cont{border-top-style:dashed;background:var(--well-2);cursor:default}
.cell.bd .num{font-weight:700;font-size:13.5px;color:var(--c);white-space:nowrap}
.cell.bd .why{font-size:12px;color:var(--muted);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cell.bd .tk{margin-left:auto;font-size:11.5px;color:var(--faint);font-variant-numeric:tabular-nums;white-space:nowrap}
.cell.bd .tail{font-size:11px;color:var(--faint);padding:3px 10px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
/* the method that did NOT open a chunk here: its card runs straight through */
.cell.bd > .thru{height:100%;min-height:22px;background:#fff;border-left:3px solid var(--cl);border-right:1px solid var(--cle);
  display:flex;align-items:center;padding-left:10px;min-width:0}
.cell.bd > .thru .lbl{font-size:11.5px;color:var(--faint);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cell.bd.dv > .thru{background:repeating-linear-gradient(135deg,#fff 0 7px,#eef2f6 7px 14px)}
.cell.bd.dv > .thru .lbl{color:var(--ink-2);font-weight:600}
/* the divergence itself: the row the columns disagree on */
.cell.bd.dv,.gut.bd.dv{background:#e8ecf2}
.cell.bd.dv.here,.gut.bd.dv.here{background:#dde3ec}
.cell.bd.dv.here > .open,.cell.bd.dv.here > .thru{box-shadow:0 0 0 2px var(--ink-2)}
/* A boundary that falls inside a paragraph. The note lives on its own line,
   and that line is drawn in EVERY column of the row -- blank where a method
   has nothing to say -- so one column can never sit a line lower. */
.board .seamrow{height:21px;line-height:21px;margin:2px 0;overflow:hidden;white-space:nowrap}
.board .seam{display:inline-block;padding:0 8px 0 6px;border-left:3px solid var(--c);border-radius:2px;
  background:color-mix(in srgb,var(--c) 12%,#fff);font-family:var(--font);font-size:10.5px;font-weight:700;
  color:var(--c);line-height:19px;vertical-align:middle;letter-spacing:.01em;
  max-width:100%;overflow:hidden;text-overflow:ellipsis}
/* The overlap mark is inset: a padding or a border here would narrow the
   text in one column only, and one wrapped line is a broken row. */
.board .body.ov{box-shadow:inset 3px 0 0 var(--c);
  background-image:repeating-linear-gradient(135deg,color-mix(in srgb,var(--c) 13%,#fff) 0 5px,transparent 5px 10px)}
.board .body.pre+.body.pre{margin-top:0}

/* rows that span the whole board */
.wide{grid-column:1/-1;min-width:0;position:sticky;left:0}
.fold{padding:4px 14px;font-size:13px;color:var(--muted);background:var(--well-2);
  border-top:1px dashed var(--line-2);border-bottom:1px dashed var(--line-2);cursor:pointer;text-align:left;width:100%}
.fold .op{color:var(--accent);font-weight:600}
.fold:hover{background:#e6ebf2}
.fold:hover .op{text-decoration:underline}
.edge{padding:5px 14px;font-size:12px;color:var(--faint);font-family:var(--font);background:var(--well)}
.edge button{color:var(--accent);font-weight:600;font-size:12px}
.edge button:hover{text-decoration:underline}

/* the panel beside the board */
.panel{border-left:1px solid var(--line);overflow:auto;min-height:0;padding:14px 16px;font-size:14px;background:var(--surface)}
.panel h3{font-size:15px;margin-bottom:10px;font-weight:650}
.panel .kv{display:grid;grid-template-columns:108px 1fr;gap:6px 10px;font-size:13.5px}
.panel .kv dt{color:var(--muted)}
.panel .empty{color:var(--muted);font-size:13.5px;line-height:1.5}

.evflash{outline:3px solid var(--warn);outline-offset:-3px}

/* Rendered document text, wherever a unit is shown. */
:is(.body,.rchunk,.mbody,.evbox) :is(h1,h2,h3,h4,h5,h6){font-family:var(--font);line-height:1.3;margin:12px 0 6px;font-weight:650}
:is(.body,.rchunk,.mbody,.evbox) h1{font-size:22px}
:is(.body,.rchunk,.mbody,.evbox) h2{font-size:19px}
:is(.body,.rchunk,.mbody,.evbox) h3{font-size:17px}
:is(.body,.rchunk,.mbody,.evbox) h4{font-size:16px}
:is(.body,.rchunk,.mbody,.evbox) h5{font-size:15px}
:is(.body,.rchunk,.mbody,.evbox) h6{font-size:14.5px;color:var(--ink-2)}
:is(.body,.rchunk,.mbody,.evbox) p{margin:6px 0}
:is(.body,.rchunk,.mbody,.evbox) ul{margin:6px 0 6px 22px}
:is(.body,.rchunk,.mbody,.evbox) li{margin:3px 0}
.tblwrap{overflow-x:auto;margin:10px 0}
.tblwrap table{border-collapse:collapse;font-size:14px;font-family:var(--font)}
.tblwrap th,.tblwrap td{border:1px solid var(--line);padding:4px 9px;text-align:left}
.tblwrap th{background:var(--well)}

/* the chunk detail beside the lanes */
.sidecard{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px;box-shadow:var(--shadow);
  position:sticky;top:calc(var(--barh) + 12px);max-height:calc(100vh - var(--barh) - 36px);overflow:auto}
.sidecard h3{font-size:15.5px;margin-bottom:10px;font-weight:650}
.sidecard .kv{display:grid;grid-template-columns:108px 1fr;gap:6px 10px;font-size:14px}
.sidecard .kv dt{color:var(--muted)}
.sidecard .empty{color:var(--muted);font-size:14px}
.reason-sent{margin-top:12px;padding:10px 12px;background:var(--well);border:1px solid var(--line);border-radius:var(--r-sm);font-size:13.5px;line-height:1.5}
.reason-sent.deep{background:var(--deep-soft);border-color:var(--deep-line)}
.arminfo{margin-top:14px;border-top:1px solid var(--line);padding-top:12px;font-size:13px;color:var(--muted)}
.detail-links button{color:var(--accent);font-weight:600;padding:0;font-size:13.5px}
.detail-links button:hover{text-decoration:underline}

/* ---- Sorgu ---- */
.subtabs{display:inline-flex;gap:2px;margin-bottom:16px;background:var(--well-2);border-radius:9px;padding:3px}
.subtabs button{padding:6px 14px;border-radius:7px;color:var(--muted);font-weight:600;font-size:14px}
.subtabs button.on{background:#fff;color:var(--ink);box-shadow:var(--shadow)}
.chatwrap{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:20px}
.chatbox{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:18px 20px;box-shadow:var(--shadow)}
.chatbox textarea{width:100%;min-height:84px;resize:vertical;font-size:15.5px;line-height:1.5}
.chatctl{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:12px}
.chatctl label{font-size:13.5px;color:var(--muted);display:flex;align-items:center;gap:6px}
.seg{display:inline-flex;gap:2px;background:var(--well-2);border-radius:9px;padding:3px;flex-wrap:wrap}
.seg button{padding:5px 12px;border-radius:7px;color:var(--muted);font-weight:600;font-size:13.5px}
.seg button.on{background:var(--accent);color:#fff}
.seg button.on.deep{background:var(--deep)}
.offline{border:1px dashed var(--line-2);border-radius:var(--r);padding:14px 18px;color:var(--ink-2);font-size:14px;background:var(--well);margin-bottom:14px;line-height:1.6}
.offline code{font-family:var(--mono);font-size:12.5px;background:#fff;border:1px solid var(--line);padding:1px 6px;border-radius:4px}
.suggest{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}
.suggest button{border:1px solid var(--line);border-radius:999px;padding:4px 12px;font-size:13.5px;background:#fff;color:var(--ink-2);text-align:left}
.suggest button:hover{border-color:var(--accent);color:var(--accent-ink)}
.turn{margin-top:20px}
.turn .q{font-weight:650;font-size:16.5px;margin-bottom:8px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.turn .q .who{font-size:11.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.answer{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px;box-shadow:var(--shadow)}
.answer .txt{font-size:15.5px;line-height:1.65;white-space:pre-wrap}
.answer .meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px;font-size:13px;color:var(--muted)}
.cite{display:inline-block;background:var(--accent-soft);color:var(--accent-ink);border-radius:6px;padding:0 6px;font-size:12px;font-weight:700;margin:0 1px;vertical-align:baseline;font-family:var(--font)}
.cite:hover{background:var(--accent);color:#fff}
.sources{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px;margin-top:12px}
.src{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-sm);padding:11px 13px;cursor:pointer;font-size:13.5px;position:relative}
.src:hover{box-shadow:0 2px 8px rgba(15,23,42,.08);border-color:var(--line-2)}
.src.used{border-color:var(--accent-line);background:#fbfcff}
.src.hl{outline:2px solid var(--warn)}
.src .lab{font-weight:700;color:var(--accent-ink);font-size:12px;margin-right:6px}
.src .hd{font-weight:600;margin:3px 0}
.src .path{color:var(--muted);font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.src .facts{color:var(--muted);font-size:12.5px;margin-top:5px;display:flex;gap:8px;flex-wrap:wrap}
.src .usedmark{position:absolute;right:10px;top:8px;color:var(--good);font-weight:700;font-size:12px}
.cmpcols{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-top:14px}
.cmpcol{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:14px;min-width:0;box-shadow:var(--shadow)}
.cmpcol .armname{font-weight:650;display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap}
.cmpcol .txt{font-size:14.5px;line-height:1.6;white-space:pre-wrap;max-height:260px;overflow:auto;border-left:3px solid var(--line);padding-left:10px}
.cmpcol .srcs{margin-top:10px;font-size:13px}
.cmpcol .srcs div{padding:4px 0;border-bottom:1px solid var(--line);display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;cursor:pointer}
.chatside h3{font-size:15px;margin-bottom:8px;font-weight:650}
.chatside .kv{display:grid;grid-template-columns:112px 1fr;gap:5px 8px;font-size:13.5px}
.chatside .kv dt{color:var(--muted)}
.goldpick{display:flex;align-items:center;gap:10px;margin-bottom:16px;flex-wrap:wrap}
.goldpick .lab{font-size:11.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.goldpick select{max-width:900px;min-width:0;flex:1 1 420px}
.qhead{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:18px 22px;margin-bottom:16px;box-shadow:var(--shadow)}
.qhead .qq{font-size:18px;font-weight:650;margin-bottom:6px}
.qhead .qa{color:var(--ink-2);margin-bottom:10px}
.qhead .qmeta{color:var(--muted);font-size:13.5px;margin-bottom:10px}
.evbox{border-left:3px solid var(--warn);background:#fefaf0;padding:10px 14px;border-radius:0 var(--r-sm) var(--r-sm) 0;font-family:var(--serif);font-size:15px;max-height:230px;overflow:auto}
.evbox .evlabel{font-family:var(--font);font-size:11.5px;color:var(--warn);font-weight:700;letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px}
.qcols{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.qcol{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:14px;min-width:0;box-shadow:var(--shadow)}
.qcol .armname{font-weight:600;margin-bottom:8px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.qcol .covline{color:var(--muted);font-size:13px;margin-bottom:10px}
.rchunk{border:1px solid var(--line);border-radius:var(--r-sm);padding:13px;font-family:var(--serif);font-size:14.5px;max-height:330px;overflow:auto;background:var(--well)}
.rchunk mark{background:var(--mark);padding:0 2px;border-radius:2px}
.rchunk .rhead{font-family:var(--font);font-size:13px;color:var(--muted);margin-bottom:8px}
.rchunk .piece{margin:6px 0}
.top5{margin-top:12px}
.top5 summary{cursor:pointer;color:var(--accent);font-size:14px;font-weight:500}
.top5 .row{display:flex;gap:8px;align-items:baseline;padding:6px 4px;border-bottom:1px solid var(--line);font-size:13.5px;flex-wrap:wrap}
.top5 .row .rk{font-weight:600;min-width:44px}
.top5 .row .mt{color:var(--good)}
.qlink{margin-top:10px;font-size:13.5px}
.qlink button{color:var(--accent);font-weight:600;padding:0}
.qlink button:hover{text-decoration:underline}

/* ---- Debug ---- */
.dbgtools{display:flex;gap:16px;align-items:center;flex-wrap:wrap;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r);padding:10px 14px;margin-bottom:12px;font-size:14px;box-shadow:var(--shadow)}
.dbgtools .lab{font-size:11.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.pagectl{display:inline-flex;align-items:center;gap:8px;padding-right:16px;border-right:1px solid var(--line)}
.pagectl select{padding:4px 30px 4px 10px;min-width:82px}
.dbgbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:13.5px}
.dbgbar select{padding:4px 30px 4px 10px}
.dbgbar input[type=text]{min-width:240px;padding:4px 10px}
.dbgbar label{display:inline-flex;align-items:center;gap:5px;color:var(--ink-2)}
.dbg{display:grid;grid-template-columns:minmax(0,1fr) 420px;gap:20px}
.dbgunit{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:12px 16px;margin-bottom:10px;cursor:pointer;
  scroll-margin-top:calc(var(--barh) + 14px);box-shadow:var(--shadow)}
.dbgunit:hover{border-color:var(--line-2)}
.dbgunit.sel{outline:2px solid var(--accent);outline-offset:-1px}
.dbgunit .head{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:6px}
.dbgunit .path{font-size:12.5px;color:var(--muted);margin-bottom:6px;font-family:var(--mono);word-break:break-all}
.dbgunit .txt{font-size:14px;color:var(--ink-2);white-space:pre-wrap;max-height:80px;overflow:hidden}
.dbgtable{width:100%;border-collapse:collapse;font:12.5px/1.5 var(--mono);margin-top:10px}
.dbgtable th,.dbgtable td{padding:3px 8px;text-align:left;border-bottom:1px solid var(--well-2)}
.dbgtable th{font-family:var(--font);font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:700;border-bottom:1px solid var(--line)}
.dbgtable tr:last-child td{border-bottom:none}
.inspector{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:16px;box-shadow:var(--shadow);
  position:sticky;top:calc(var(--barh) + 12px);max-height:calc(100vh - var(--barh) - 36px);overflow:auto;font-size:13.5px}
.inspector pre{white-space:pre-wrap;font:12.5px/1.5 var(--mono);background:var(--well);border:1px solid var(--line);border-radius:var(--r-sm);padding:10px;margin-top:8px;max-height:260px;overflow:auto}
.trail{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}
.trail .row{display:grid;grid-template-columns:112px 1fr;gap:5px 8px;font-size:13px;margin-bottom:5px}
.trail .row dt{color:var(--muted)}
.trail .grp{background:var(--well);border:1px solid var(--line);border-radius:var(--r-sm);padding:8px 10px;margin-top:8px;font-size:13px}
.trail .grp .ids{font-family:var(--mono);font-size:11.5px;color:var(--muted);word-break:break-all}
.secpanel{margin-top:22px}
.sectable{width:100%;border-collapse:collapse;font-size:13.5px;background:var(--surface)}
.sectable th,.sectable td{border-bottom:1px solid var(--line);padding:8px 11px;text-align:left;vertical-align:top}
.sectable th{background:var(--well);font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:700}
.sectable tr.clk{cursor:pointer;scroll-margin-top:calc(var(--barh) + 52px)}
.sectable tr.clk:hover{background:var(--well)}
.stpill{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12.5px;font-weight:600}
.stpill.standard_kept{background:var(--well-2);color:var(--ink-2)}
.stpill.deterministic_improved{background:var(--good-soft);color:var(--good)}
.stpill.llm_accepted{background:var(--deep-soft);color:var(--deep-ink)}
.stpill.llm_reverted{background:var(--warn-soft);color:var(--warn)}
.stpill.contract_reverted{background:var(--bad-soft);color:var(--bad)}

/* ---- Benchmark ---- */
.bench h2{margin:26px 0 10px;font-size:17px;font-weight:650}
.legend{color:var(--muted);font-size:13.5px;line-height:1.55;margin-top:8px;max-width:1040px}
.pairlists{display:flex;gap:16px;flex-wrap:wrap;margin-top:8px}
.pairlists .pl{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-sm);padding:13px 16px;font-size:13.5px;line-height:1.7}
.pairlists .pl b{font-weight:600}
.qidchip{font-family:var(--mono);background:var(--well-2);border-radius:4px;padding:1px 7px;font-size:12.5px;cursor:pointer}
.qidchip:hover{background:var(--accent-soft);color:var(--accent-ink)}
details.secgold{margin-top:14px}
details.secgold summary{cursor:pointer;color:var(--accent);font-weight:500}
.interp{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:16px 20px;font-size:15px;line-height:1.6;max-width:1040px;margin-top:12px}
.interp b{font-weight:650}
.mfacts{display:flex;gap:10px;flex-wrap:wrap;font-size:13px;color:var(--muted)}

/* KPI tiles: the top layer of every summary */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:15px 17px;min-width:0;box-shadow:var(--shadow)}
.kpi .lab{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:2px;flex-wrap:wrap}
.kpi .v{font-size:28px;font-weight:650;letter-spacing:-.4px;font-variant-numeric:tabular-nums;line-height:1.2;margin-top:8px;
  display:flex;align-items:baseline;gap:7px;flex-wrap:wrap}
.kpi .v .from{color:var(--muted);font-weight:600}
.kpi .v .arrow{color:var(--faint);font-size:18px;font-weight:400}
.kpi .v .to{color:var(--deep)}
.kpi .v .unit{font-size:14px;font-weight:500;color:var(--muted)}
.kpi .sub{font-size:13.5px;color:var(--muted);margin-top:6px;line-height:1.45}
.kpi .delta{display:inline-block;border-radius:999px;padding:1px 9px;font-size:12.5px;font-weight:650;margin-top:8px}
.kpi .delta.good{background:var(--good-soft);color:var(--good)}
.kpi .delta.flat{background:var(--well-2);color:var(--ink-2)}
.kpi .delta.warn{background:var(--warn-soft);color:var(--warn)}
.kpi.hero{border-color:var(--deep-line);background:linear-gradient(150deg,var(--deep-soft) 0%,var(--surface) 62%)}

/* disclosures: everything a reader asks second */
details.deep-detail{margin-top:14px;background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:0 18px;box-shadow:var(--shadow)}
details.deep-detail>summary{cursor:pointer;color:var(--ink);font-size:14.5px;font-weight:600;padding:13px 0;list-style:none;display:flex;align-items:center;gap:12px}
details.deep-detail>summary::-webkit-details-marker{display:none}
details.deep-detail>summary::before{content:"";width:7px;height:7px;border-right:2px solid var(--muted);border-bottom:2px solid var(--muted);
  transform:rotate(-45deg);transition:transform .15s;flex:0 0 auto;margin-left:3px}
details.deep-detail[open]>summary::before{transform:rotate(45deg)}
details.deep-detail[open]>summary{border-bottom:1px solid var(--line);margin-bottom:8px}
details.deep-detail .inner{padding-bottom:18px}
details.deep-detail .inner>h2:first-child,details.deep-detail .inner>.sechead:first-child{margin-top:14px}
.gloss{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:4px 18px 12px;margin-top:10px}
.gloss dl{display:grid;grid-template-columns:minmax(190px,270px) 1fr;gap:0 20px}
.gloss dt{font-size:14px;font-weight:600;padding:10px 0 0;border-top:1px solid var(--line)}
.gloss dt:first-of-type,.gloss dd:first-of-type{border-top:none}
.gloss dd{font-size:13.5px;color:var(--ink-2);line-height:1.5;padding:10px 0;border-top:1px solid var(--line)}
.gloss dt .techname{display:block;font-weight:400;margin-top:2px}

/* ---- the RAG console: one button, one dialog ---- */
#wsopen{display:inline-flex;align-items:center;gap:7px}
#wsopen .dot{width:8px;height:8px;border-radius:999px;background:var(--faint);flex:0 0 auto}
#wsopen.live .dot{background:var(--good)}
#wsopen.down .dot{background:var(--bad)}
.wsbody{font-family:var(--font);font-size:14.5px;line-height:1.55}
.wskb{border:1px solid var(--line);border-radius:var(--r);padding:12px 14px;background:var(--well);min-width:0;margin-top:10px}
.wskb .kbname{font-weight:650;font-size:15px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.wskb .kbmeta{color:var(--muted);font-size:13px;margin-top:4px;display:flex;gap:12px;flex-wrap:wrap}
.wskb .docs{margin-top:8px;display:flex;flex-direction:column}
.wskb details>summary{cursor:pointer;color:var(--accent);font-size:13.5px;margin-top:8px}
.wsdoc{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;font-size:13.5px;padding:8px 0;border-top:1px solid var(--line)}
.wsdoc .dname{font-weight:600;overflow-wrap:anywhere}
.wsdoc .dmeta{color:var(--muted);font-size:12.5px;margin-left:auto;white-space:nowrap}
.wskb .none{color:var(--muted);font-size:13.5px;margin-top:8px}

/* ---- modal ---- */
.modal{position:fixed;inset:0;background:rgba(15,23,42,.5);z-index:80;display:flex;align-items:center;justify-content:center;padding:20px}
.modal .box{background:var(--surface);border-radius:14px;max-width:980px;width:100%;max-height:88vh;overflow:auto;padding:22px 26px;box-shadow:var(--shadow-lg)}
.modal .box .mhead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}
.modal .box .mhead h3{font-size:17px;font-weight:650}
.modal .box .mbody{font-family:var(--serif);font-size:16px;line-height:1.6}
.modal .box .mbody p{margin:8px 0}
.modal .box .mbody ul{margin:8px 0 8px 22px}
.modal .box .mfacts{margin-bottom:12px}
footer{color:var(--faint);font-size:12.5px;padding:28px 22px;text-align:center}

@media (max-width:1500px){
  .sonuc .num{display:none}
  .stage{grid-template-columns:26px minmax(0,1fr) 288px}
  .board{--colmin:248px}
}
@media (min-width:2200px){
  .board .body{font-size:15.5px;max-width:760px}
}
@media (max-width:1100px){
  .dbg,.chatwrap{grid-template-columns:1fr}
  .stage{grid-template-columns:minmax(0,1fr);grid-template-rows:auto auto;height:auto!important;max-height:none}
  .docmap{display:none}
  .board{max-height:70vh;--colmin:236px}
  .panel{grid-column:1/-1;border-left:none;border-top:1px solid var(--line);max-height:320px}
  .sidecard,.inspector{position:static;max-height:none}
  .fixrow,.fixhead{grid-template-columns:1fr;gap:6px}
  .fixrow .n{text-align:left}
  .gloss dl{grid-template-columns:1fr}
  .gloss dd{border-top:none;padding-top:2px}
}
@media (max-width:760px){
  .topbar{padding:8px 14px;gap:10px 16px}
  .tabs{order:3;width:100%;border-top:1px solid var(--line)}
  .tabs button{padding:8px 12px}
  .docpick select{min-width:140px}
  main{padding:16px 14px 32px}
  .pagehead h1{font-size:22px}
}
</style>
</head>
<body>
<header class="topbar">
  <span class="brand"><span class="mark">A</span>AMSC Chunking<small>Viewer v2</small><span class="tag">PoC</span></span>
  <nav class="tabs" id="modetabs">
    <button data-mode="presentation">Sunum</button>
    <button data-mode="query">Sorgu</button>
    <button data-mode="debug">Debug</button>
    <button data-mode="benchmark">Benchmark</button>
  </nav>
  <div class="bar-right">
    <label class="docpick"><span class="lab">Doküman</span><select id="docsel" title="Doküman"></select></label>
    <button class="btn small" id="wsopen" title="RAG Console'daki bilgi tabanları ve dokümanlar"><span class="dot" id="wsdot"></span> <span id="wslabel">RAG Console</span></button>
  </div>
</header>
<main>
  <div class="pagehead" id="pagehead"></div>
  <div id="view-presentation" data-mode="presentation">
    <div class="cmpbar" id="cmpbar"></div>
    <div class="dvsum" id="dvsum"></div>
    <div class="stage" id="stage">
      <div class="docmap" id="docmap" title="Doküman haritası: işaretler ayrışma noktalarıdır, mavi pencere açık sayfadır. Tıklayınca oraya gider."></div>
      <div class="board" id="board"></div>
      <aside class="panel" id="presdetail"><div id="chunkdetail"></div></aside>
    </div>
    <div id="results"></div>
    <div class="sechead" id="methodhead"></div>
    <div id="methods" class="methods"></div>
    <div id="methodnote"></div>
  </div>
  <div id="view-query" class="hidden" data-mode="query">
    <div class="subtabs" id="qsubtabs">
      <button data-sub="chat">Dokümana sor</button>
      <button data-sub="gold">Ölçüm soruları</button>
    </div>
    <div id="chatview">
      <div id="offline" class="offline hidden"></div>
      <div class="chatwrap">
        <div>
          <div class="chatbox">
            <textarea id="chatq" placeholder="Örn. Şirketin 2024 yılı toplam üye sayısı kaçtır?"></textarea>
            <div class="chatctl">
              <span class="seg" id="chatarms"></span>
              <label><input type="checkbox" id="chatcmp"> Tüm yöntemlerle karşılaştır</label>
              <label>Top-k <select id="chatk"><option>3</option><option selected>5</option><option>8</option></select></label>
              <button class="btn primary" id="chatsend">Sor</button>
              <span class="muted" id="chatstatus" style="font-size:13px"></span>
            </div>
            <div class="suggest" id="suggest"></div>
          </div>
          <div id="turns"></div>
        </div>
        <aside class="card chatside" id="chatside"></aside>
      </div>
    </div>
    <div id="goldview" class="hidden">
      <div class="goldpick"><span class="lab">Ölçüm sorusu</span><select id="querysel"></select></div>
      <div id="queryhead"></div>
      <div class="qcols" id="querycols"></div>
    </div>
  </div>
  <div id="view-debug" class="hidden" data-mode="debug">
    <div class="dbgtools" id="dbgtools">
      <span class="pagectl" id="pagectl"><span class="lab">Sayfa</span>
        <span class="stepnav"><button id="dbgprev" title="Önceki sayfa">&#8592;</button></span>
        <select id="pagesel"></select>
        <span class="stepnav"><button id="dbgnext" title="Sonraki sayfa">&#8594;</button></span></span>
      <div class="dbgbar" id="dbgbar"></div>
    </div>
    <div class="dbg">
      <div id="dbglist"></div>
      <aside class="inspector" id="inspector"></aside>
    </div>
    <div class="secpanel" id="secpanel"></div>
  </div>
  <div id="view-benchmark" class="bench hidden" data-mode="benchmark"></div>
</main>
<footer id="foot"></footer>
<div id="tip" class="tip hidden" role="tooltip"></div>
<div id="modal" class="modal hidden"></div>
<script id="viewer-data" type="application/json">__VIEWER_DATA__</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("viewer-data").textContent);
const ARMS = DATA.armOrder;
const PRODUCT_ARMS = DATA.productArmOrder || ["markdown","hybrid","structure-only","agentic"];
const ARM_LABEL = DATA.armLabels;

const LANE_COLOR = {markdown: "#b45309", hybrid: "#0f766e", "structure-only": "#1d4ed8", agentic: "#6d28d9"};
const LANE_SOFT = {markdown: "#fdf1dc", hybrid: "#dcf3ef", "structure-only": "#e8effc", agentic: "#f1ebfd"};

const REASONS = {
  doc_start:   {label:"Doküman başlangıcı", short:"doküman başı", sent:"Bu, dokümanın ilk parçası."},
  new_section: {label:"Yeni bölüm başladı", short:"yeni bölüm", sent:"Bir önceki parçanın bölümü kapandı; bu parça yeni bir bölüm başlığıyla açılıyor."},
  label_split: {label:"Ara başlıkta bölündü", short:"ara başlık", sent:"Aynı bölümün içinde, okuyucunun zaten duraksadığı bir ara başlıkta kesildi."},
  budget_split:{label:"Boyut sınırına ulaşıldı", short:"boyut sınırı", sent:"Bölüm hedeflenen boyutu aştığı için bölündü; bölüm başlığı iki parçada da korunuyor."},
  md_size:     {label:"Boyut tabanlı kesim", short:"boyut sınırı", sent:"Markdown yöntemi bölüm yapısına bakmaz; hedef boyuta ulaşıldığında keser."},
  md_overlap:  {label:"Boyut tabanlı kesim (örtüşmeli)", short:"boyut sınırı · örtüşmeli", sent:"Hedef boyuta ulaşıldı; önceki parçanın kuyruğu örtüşme olarak bu parçaya taşındı."},
  md_heading:  {label:"Başlık sınırında kesim", short:"başlık sınırı", sent:"Kesim, markdown ayracının denk geldiği bir başlık sınırında gerçekleşti."}
};
// Continuation connector text, per boundary reason. Shown only when the
// boundary carries a TOKEN_BUDGET_CONTINUATION link (same section, adjacent).
const CONT_LABELS = {
  budget_split: "Önceki parçanın devamı — boyut sınırı nedeniyle ayrıldı",
  label_split:  "Önceki parçanın devamı — ara başlıkta bölündü",
  md_size:      "Önceki parçanın devamı — boyut sınırı nedeniyle ayrıldı",
  md_overlap:   "Önceki parçanın devamı — boyut sınırı (kuyruk örtüşme olarak taşındı)",
  md_heading:   "Önceki parçanın devamı — başlık sınırında kesildi"
};
// The same reason in the two or three words a band has room for.
const shortReason = chunk => (REASONS[chunk && chunk.rs] || {}).short || "";
// Every structural defect the contract counts, in the words a reader who has
// never seen the pipeline would use. The technical key stays visible next to
// the label wherever the number is audited, so nothing is renamed away.
const SMELL_INFO = {
  orphan_label:        {label:"Başlık içerikten koptu",           help:"Bir başlık, anlattığı metinden ayrı bir parçaya düştü. Arama başlığı bulur ama içeriği getirmez."},
  lead_in_cut:         {label:"Giriş cümlesi devamından ayrıldı", help:"“Aşağıdaki tabloda…” gibi bir giriş cümlesi, tarif ettiği içerikten koptu."},
  continuation_cut:    {label:"Devam cümlesi / dipnot koptu",     help:"Bir cümlenin devamı ya da dipnotu ayrı parçaya düştü; cevap yarım kalabilir."},
  run_split_when_fits: {label:"Liste gereksiz yere bölündü",      help:"Tek parçaya sığabilecek bir liste ikiye ayrıldı; maddelerin bir kısmı cevaba gelmez."},
  table_split:         {label:"Tablo ortadan bölündü",            help:"Bir tablo iki parçaya ayrıldı; satırlar kendi başlık satırından koptu."},
  fragment_cut:        {label:"Paragraf ortasından kesildi",      help:"Kesim bir paragrafın ya da bloğun ortasından geçti."},
  below_min:           {label:"Çok kısa parça",                   help:"Tek başına anlam taşımayacak kadar kısa chunk (160 token altı)."},
  above_soft_max:      {label:"Çok uzun parça",                   help:"Hedeflenen boyutun üstünde kalan chunk (900 token üstü); modele fazladan bağlam gider."}
};
const SMELL_TEXT = Object.fromEntries(Object.entries(SMELL_INFO).map(([k, v]) => [k, v.label]));
const SMELL_HELP = Object.fromEntries(Object.entries(SMELL_INFO).map(([k, v]) => [k, v.help]));
const SMELL_FIXED = {
  orphan_label: "başlık içeriğiyle birlikte kaldı",
  lead_in_cut: "giriş cümlesi devamıyla kaldı",
  continuation_cut: "devam cümlesi ayrılmadı",
  run_split_when_fits: "liste bütün kaldı",
  fragment_cut: "paragraf ortası kesim azaldı",
  table_split: "tablo ortası kesim azaldı"
};
// Metric names the page shows, each with the sentence that answers "bu sayı ne
// anlatıyor?". Rendered as a label + hover note, and collected into the
// glossary at the bottom of the Benchmark tab.
const TERMS = {
  smell:        {label:"Yapısal kalite problemi", tech:"boundary smell", help:"Parça sınırının yanlış yerden geçtiği durumların sayısı: kopmuş başlık, bölünmüş liste, ortadan ikiye ayrılmış tablo. Deterministik olarak sayılır, tahmin değildir. Ne kadar düşükse o kadar iyi."},
  regression:   {label:"Kötüleşen bölüm", tech:"tiered regression", help:"Deep Analysis'ten sonra herhangi bir problem türünde Standard'dan daha kötü hale gelen bölüm sayısı. Sözleşme gereği 0 olmak zorundadır."},
  sizetrade:    {label:"Boyut takası", tech:"strict regression", help:"Kalite problemi kesin azalırken parça boyutunun hedefin dışına taştığı bölüm sayısı. Bilinçli bir takastır, hata değildir."},
  ceiling:      {label:"Kaçınılmaz kesim", tech:"temsil tavanı / ceiling boundary", help:"Tek bir tablonun ya da paragrafın kendisi bütçeden büyük olduğu için hiçbir bölümleme yönteminin kaçınamayacağı kesim. Kalan problemlerin bu kısmı düzeltilebilir değildir."},
  hit:          {label:"Doğru parçayı bulma oranı", tech:"Hit@1 / Hit@3 / Hit@5", help:"Gold soruların yüzde kaçında doğru cevabı içeren parça ilk 1 / 3 / 5 sonuç arasında geldi. 1'e ne kadar yakınsa o kadar iyi."},
  mrr:          {label:"Sıralama kalitesi", tech:"MRR", help:"Doğru parçanın sonuç listesindeki sırasının tersinin ortalaması. Doğru sonuç ne kadar üste çıkarsa o kadar yüksektir."},
  coverage:     {label:"Kanıt kapsama", tech:"evidence coverage", help:"Cevabın dayandığı kanıt metninin, getirilen parçalar tarafından ne kadarının kapsandığı."},
  goldset:      {label:"Gold sorgu seti", tech:"gold set", help:"Cevabı ve kanıt metni elle doğrulanmış soru listesi. Ölçüm bunun üzerinden yapılır; sorusu olmayan doküman için arama sayısı uydurulmaz."},
  holdout:      {label:"Hiç ayar görmemiş doküman", tech:"holdout", help:"Eşiklerin ve kuralların ayarlanmasında kullanılmamış doküman. Sonuçların o dokümana özel ayarla şişirilmediğini gösterir."},
  llmrole:      {label:"LLM'in rolü", tech:"proposer + verifier", help:"LLM her sınıra karışmaz: yalnız kuralın kararsız kaldığı yerlerde öneri verir, her öneri iki farklı sırada ayrıca doğrulanır, doğrulanmayan öneri geri alınır."},
  chunk:        {label:"Parça (chunk)", tech:"chunk", help:"Dokümanın aramaya ve cevaba giren en küçük birimi. Sınırların doğru yerden geçmesi, cevabın bütün olup olmamasını belirler."},
  frozen:       {label:"Dondurulmuş karşılaştırma", tech:"frozen benchmark v5", help:"Bir kez koşulmuş ve bir daha değiştirilmemiş referans ölçüm. Metodolojik dayanak olarak durur; yeni koşularla güncellenmez."}
};
const SECTION_STATUS = {
  standard_kept: "Yapısal sınır korundu",
  deterministic_improved: "Kalite kuralı iyileştirdi",
  llm_accepted: "LLM önerisi doğrulandı",
  llm_reverted: "LLM önerisi reddedildi",
  contract_reverted: "Kalite kontrolü değişikliği reddetti"
};

// Presentation-mode naming. Standard is the product's fast mode; Agentic
// Chunker is the product's Deep Analysis; the embedding-assisted hybrid
// stays visible as a research arm, NOT a product mode.
const MODE_NAMES = {
  "structure-only": {top:"Standard", sub:"hızlı · deterministik"},
  "hybrid":         {top:"Hybrid", sub:"araştırma kolu"},
  "markdown":       {top:"Markdown", sub:"taban çizgisi"},
  "agentic":        {top:"Deep Analysis", sub:"yapı + kalite kuralları + model"}
};
const METHOD_DESC = {
  markdown: "Metni Markdown düzenine ve sabit token boyutuna göre böler (700 token hedef, 140 token örtüşme). Başlık/bölüm mantığına bakmaz; hızlı bir taban çizgisidir.",
  hybrid: "Bölüm yapısını takip eder; bütçeyi aşan bölümlerde kesim yerini embedding benzerliğiyle seçer (H1 arbitration). Araştırma koludur, ürün modu değildir; bir güven/belirsizlik dedektörü değildir.",
  "structure-only": "Başlık, bölüm ve etiket yapısını deterministic olarak takip eder: her bölüm kendi başlığı altında kalır, yalnız bütçeyi aşan bölümler bölünür. Hızlı, tekrarlanabilir, LLM'siz — ürünün Standard modu.",
  agentic: "Standard'ın üstüne bir kalite sözleşmesi koyar: yetim başlık, ayrılmış lead-in, bölünmüş liste gibi kötü sınırları deterministic kurallarla düzeltir; gerçekten belirsiz sınırlarda LLM'e danışır ve her öneriyi iki sırada doğrulatır. Hiçbir problem türünde Standard'dan kötü olamaz — ürünün Deep Analysis modu, ek gecikme ve maliyetle.",
  agentic_rules: "Bu dokümanda yalnız kalite sözleşmesinin deterministic katmanı çalıştı: yetim başlık, ayrılmış lead-in ve bölünmüş liste gibi kötü sınırlar kurallarla düzeltildi, hiçbir model çağrısı yapılmadı. Sonuç tekrarlanabilir ve ücretsizdir; model katmanı için dokümanı RAG Console'da Deep Analysis seçeneğiyle yükleyin."
};
// One sentence per method, answering "bu benim için ne demek?" -- the product
// layer over METHOD_DESC, which keeps the mechanism.
const METHOD_IMPACT = {
  markdown: "Hızlı, ama başlığı içeriğinden ayırabilir; cevap yarım gelebilir.",
  hybrid: "Araştırma için tutulur; üründe seçilecek bir mod değildir.",
  "structure-only": "Her bölüm kendi başlığı altında kalır. Ek maliyet yok, ek gecikme yok.",
  agentic: "Kopmuş başlık, bölünmüş liste ve ikiye ayrılmış tabloları toplar.",
  // The same mode on a document no model was consulted for. Promising a cost
  // that was never paid would be as wrong as hiding one that was.
  agentic_rules: "Standard'ın kaçırdığı kopmuş başlık, bölünmüş liste ve ikiye ayrılmış tabloları toplar. Bu dokümanda yalnız ücretsiz kalite kuralları çalıştı: model çağrısı yapılmadı."
};

// Two kinds of document share this page and must never be mixed. The frozen
// corpus is the published benchmark set: fixed, gold-backed, comparable. A
// live document comes from the RAG console's own ingest -- real analysis, but
// no gold queries and no place in the frozen tables.
const FROZEN_ORDER = (DATA.docOrder || Object.keys(DATA.docs)).filter(id => DATA.docs[id]);
const DOC_ORDER = FROZEN_ORDER.slice();
const LIVE_LOADED = new Set();
const state = {
  doc: DOC_ORDER[0],
  mode: "presentation",
  arm: null,
  armB: null,
  // The methods being compared, left to right. One lane is a reading view;
  // two or more is the comparison this product exists for.
  lanes: null,
  page: null,
  diffIdx: -1,
  // "Sadece ayrışmalar": runs every column agrees on fold away.
  foldAgree: false,
  unfolded: new Set(),
  // With three or four columns the disagreement list is dominated by the
  // research arms; this walks only the Standard / Deep Analysis story.
  pairOnly: false,
  // Text density: null follows the column count, true/false is the reader's
  // own choice. Paragraphs opened one at a time live in `tall`, keyed by
  // unit id so a row opens in EVERY column at once.
  short: null,
  tall: new Set(),
  query: null,
  selChunk: null,
  selArm: null,
  selUnit: null,
  qsub: "chat",
  dbg: {type:"all", role:"all", text:"", onlyBig:false, onlyPf:false, secStatus:"changed"},
  chat: {online:null, health:null, turns:[], busy:false, arm:null}
};

const D = () => DATA.docs[state.doc];
const A = () => D().arms[state.arm];
// The arm a chunk selection belongs to: the reader's own column in the
// side-by-side view, the single arm everywhere else.
const selArm = () => (state.selArm && D().arms[state.selArm]) ? state.selArm : state.arm;
const SA = () => D().arms[selArm()];
const $ = id => document.getElementById(id);
const esc = s => String(s === null || s === undefined ? "" : s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const fmt = (v, d) => v === null || v === undefined || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(d === undefined ? 4 : d);
const pct = v => v === null || v === undefined ? "—" : (Number(v) * 100).toFixed(1) + "%";
const hasArm = a => Boolean(D().arms[a]);
const docArms = () => PRODUCT_ARMS.filter(hasArm);
const isDeepArm = a => a === "agentic" && D().arms.agentic && D().arms.agentic.kind === "deep_analysis";
const isLegacyAgentic = () => D().arms.agentic && D().arms.agentic.kind === "agentic_structure_llm";
const deepMeta = () => D().meta.deep || null;
// What actually happened on this document, decided in one place so no two
// screens can tell different stories. The pipeline reports five states and
// `calls.total` counts *attempted* calls -- so a run whose every call failed
// would otherwise read exactly like a successful one.
const DEEP_STATES = {
  llm: {
    tag: "", pill: "deep", ranModel: true,
    short: "Deep Analysis çalıştı; model kararsız sınırlarda görüş verdi.",
    help: "Bu dokümanda kalite kuralları ve model katmanı birlikte çalıştı."
  },
  degraded: {
    tag: "kısmi model", pill: "mid", ranModel: true, warn: true,
    short: "Deep Analysis çalıştı, ancak model çağrılarının bir kısmı yanıtsız kaldı.",
    help: "Yanıtsız kalan bölümler kural katmanında bırakıldı; sonuç yine de Standard'ın gerisine düşemez."
  },
  rules: {
    tag: "kural tabanlı", pill: "grey", ranModel: false,
    short: "Bu dokümanda model kullanılmadı: yalnız deterministik kalite kuralları çalıştı.",
    help: "Doküman Standard modda yüklendi. Karşılaştırmanın Deep tarafını ücretsiz, modelsiz kalite sözleşmesi üretti.",
    desc: METHOD_DESC.agentic_rules, impact: METHOD_IMPACT.agentic_rules
  },
  no_calls: {
    tag: "modele gerek olmadı", pill: "grey", ranModel: false,
    short: "Deep Analysis çalıştı; bu dokümanda modele danışılacak kararsız bir sınır çıkmadı.",
    help: "Model yapılandırılmıştı ama hiç çağrılmadı: bütün düzeltmeleri ücretsiz kural katmanı yaptı. Sonuç tekrarlanabilir.",
    desc: "Deep Analysis bu dokümanda çalıştı, ancak kuralın kararsız kaldığı bir sınır çıkmadığı için modele hiç danışılmadı. Bütün düzeltmeler deterministik kalite katmanından geliyor; sonuç tekrarlanabilir ve ücretsizdir.",
    impact: "Standard'ın kaçırdığı kopmuş başlık ve bölünmüş listeleri toplar. Bu dokümanda modele gerek kalmadı: maliyet yok."
  },
  no_provider: {
    tag: "modelsiz tamamlandı", pill: "mid", ranModel: false, warn: true,
    short: "Deep Analysis istendi ama modele ulaşılamadı; sonuç yalnız kural katmanından geliyor.",
    help: "Model sağlayıcısı yapılandırılmamış ya da erişilemiyordu. Koşu kural katmanıyla tamamlandı.",
    desc: "Deep Analysis istendi; modele ulaşılamadığı için yalnız deterministik kalite katmanı çalıştı. Aşağıdaki kazanç o katmanın kazancıdır.",
    impact: "Standard'ın kaçırdığı kötü sınırları kurallarla topladı. Model katmanının ekleyeceği kazanç bu koşuda yok."
  },
  failed: {
    tag: "model yanıt vermedi", pill: "miss", ranModel: false, warn: true,
    short: "Model çağrıları yapıldı ama hiçbiri yanıtlanmadı; sonucun tamamı kural katmanından geliyor.",
    help: "Sağlayıcı hata döndürdü. Aşağıdaki sayılar yalnız deterministik katmanın kazancıdır.",
    desc: "Deep Analysis istendi; model çağrıları yanıtsız kaldığı için yalnız deterministik kalite katmanı çalıştı.",
    impact: "Standard'ın kaçırdığı kötü sınırları kurallarla topladı. Model katmanının ekleyeceği kazanç bu koşuda yok."
  }
};
function analysisState(){
  const dm = deepMeta();
  if (!dm) return null;
  const st = dm.status || null;
  const calls = (dm.calls && dm.calls.total) || 0;
  let key = "llm";
  if (st === "fallback_no_provider") key = "no_provider";
  else if (st === "fallback_provider_error") key = "failed";
  else if (st === "degraded") key = "degraded";
  else if (st === "deterministic" || dm.mode === "deterministic") key = "rules";
  // A model was configured and the run succeeded, but nothing was uncertain
  // enough to ask about. That is a different fact from "no model was offered".
  else if (calls === 0) key = dm.model ? "no_calls" : "rules";
  return Object.assign({key}, DEEP_STATES[key]);
}
// The product name is what a reader sees; the engine name is kept for the
// places where a measurement is being audited and the two must be tied.
const modeName = a => (MODE_NAMES[a] || {top: ARM_LABEL[a] || a, sub: ""});
const armLabel = a => modeName(a).top;
const armTech = a => ARM_LABEL[a] || a;
const armFull = a => armTech(a) === armLabel(a) ? esc(armLabel(a))
  : `${esc(armLabel(a))} <span class="techname">${esc(armTech(a))}</span>`;

/* -------- the explainer layer -------- */
// A "?" carrying one sentence of plain-language help. It is a real button, so
// it answers to hover, to focus and to a tap -- a native title answers to none
// of those three reliably, which is why some of them read as broken.
const info = help => help ? `<button type="button" class="info" data-help="${esc(help)}" aria-label="Aciklama">?</button>` : "";
let tipFor = null;
function showTip(btn){
  const tip = $("tip");
  tip.textContent = btn.dataset.help || "";
  tip.classList.remove("hidden");
  const r = btn.getBoundingClientRect();
  const w = Math.min(340, window.innerWidth - 24);
  tip.style.width = w + "px";
  tip.style.left = Math.max(12, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - w - 12)) + "px";
  const h = tip.getBoundingClientRect().height;
  tip.style.top = (r.bottom + 8 + h > window.innerHeight - 10 ? Math.max(10, r.top - h - 8) : r.bottom + 8) + "px";
  if (tipFor && tipFor !== btn) tipFor.classList.remove("on");
  tipFor = btn;
  btn.classList.add("on");
}
function hideTip(){
  $("tip").classList.add("hidden");
  if (tipFor) tipFor.classList.remove("on");
  tipFor = null;
}
function initTips(){
  const at = e => e.target.closest && e.target.closest(".info");
  document.addEventListener("pointerover", e => { const b = at(e); if (b) showTip(b); });
  document.addEventListener("pointerout", e => { const b = at(e); if (b && b === tipFor && !b.dataset.pin) hideTip(); });
  document.addEventListener("focusin", e => { const b = at(e); if (b) showTip(b); });
  document.addEventListener("focusout", e => { const b = at(e); if (b && b === tipFor) hideTip(); });
  document.addEventListener("click", e => {
    const b = at(e);
    if (!b) { hideTip(); return; }
    // The "?" sits inside cards and rows that select something when clicked.
    // Asking what a number means must never also change what is on screen.
    e.stopPropagation();
    e.preventDefault();
    if (b === tipFor && b.dataset.pin) { delete b.dataset.pin; hideTip(); }
    else { b.dataset.pin = "1"; showTip(b); }
  }, true);
  window.addEventListener("scroll", () => { if (tipFor) hideTip(); }, true);
  window.addEventListener("resize", () => { if (tipFor) hideTip(); });
}
// A metric name in product language, with its technical name kept beside it
// wherever the number is being audited rather than merely summarised.
function term(key, opts){
  const t = TERMS[key];
  if (!t) return esc(key);
  const showTech = opts && opts.tech;
  return `${esc(t.label)}${showTech ? ` <span class="techname">${esc(t.tech)}</span>` : ""}${info(t.help)}`;
}
// The inside of a section head, for a host element that already is the wrapper.
const inner = html => html.replace(/^<div class="sechead">/, "").replace(/<\/div>$/, "");
function sectionHead(step, title, lead){
  return `<div class="sechead"><h2>${step ? `<span class="step">${step}</span>` : ""}${title}</h2>${lead ? `<div class="lead">${lead}</div>` : ""}</div>`;
}
function glossary(keys){
  const rows = keys.filter(k => TERMS[k]).map(k => {
    const t = TERMS[k];
    return `<dt>${esc(t.label)}<span class="techname">${esc(t.tech)}</span></dt><dd>${esc(t.help)}</dd>`;
  }).join("");
  return `<details class="deep-detail"><summary>Sözlük — ekrandaki terimler ne anlama geliyor?</summary>
    <div class="inner"><div class="gloss" style="border:none;padding:0;margin:0"><dl>${rows}</dl></div></div></details>`;
}
// "233 → 68" with the direction read out loud, so a reader never has to work
// out whether a falling number is good news.
function deltaPill(from, to, lowerIsBetter){
  if (from === null || from === undefined || to === null || to === undefined) return "";
  const d = to - from;
  if (!d) return `<span class="delta flat">değişmedi</span>`;
  const better = lowerIsBetter === false ? d > 0 : d < 0;
  const share = from ? Math.round(Math.abs(d) / from * 100) : null;
  const sign = d < 0 ? "−" : "+";
  return `<span class="delta ${better ? "good" : "warn"}">${sign}${Math.abs(d)}${share !== null ? ` (%${share})` : ""} ${better ? "daha iyi" : "daha fazla"}</span>`;
}
function kpi(label, help, valueHtml, sub, extraClass){
  return `<div class="kpi ${extraClass || ""}"><div class="lab">${label}${info(help)}</div>
    <div class="v">${valueHtml}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
}
const arrowValue = (from, to) => `<span class="from">${from}</span><span class="arrow">→</span><span class="to">${to}</span>`;

const _baseId = id => String(id).split("#")[0];
function unitById(id){ return D()._byId[id]; }
function indexDoc(doc){
  doc._byId = {};
  doc.units.forEach(u => { doc._byId[u.i] = u; });
  doc._diffKey = new Set((doc.diffs || []).map(d => d.a + "|" + d.b));
  for (const arm of Object.values(doc.arms)) {
    arm._idx = {};
    arm.chunks.forEach((c, i) => { arm._idx[c.id] = i; });
  }
  return doc;
}
function indexDocs(){ for (const doc of Object.values(DATA.docs)) indexDoc(doc); }
indexDocs();
const isLive = id => Boolean((DATA.docs[id || state.doc] || {}).live);
function defaultArm(){ return hasArm("agentic") && isDeepArm("agentic") ? "agentic" : (hasArm("structure-only") ? "structure-only" : docArms()[0]); }
state.arm = defaultArm();
state.armB = hasArm("structure-only") && state.arm !== "structure-only" ? "structure-only" : (docArms().find(a => a !== state.arm) || state.arm);

/* -------- unit rendering (presentation-grade) -------- */
function unitHtml(u){
  if (u.h !== 0 && u.h !== null && u.h !== undefined) {
    if (u.t === "heading") {
      const lvl = Math.min(Math.max(u.l || 3, 1), 6);
      return "<h" + lvl + ">" + u.h + "</h" + lvl + ">";
    }
    if (u.t === "table" || u.t === "list") return u.h;
    return "<p>" + u.h + "</p>";
  }
  if (u.t === "heading") {
    const lvl = Math.min(Math.max(u.l || 3, 1), 6);
    return "<h" + lvl + ">" + esc(u.x) + "</h" + lvl + ">";
  }
  return "<p>" + esc(u.x) + "</p>";
}
// Lightweight markdown for chunk text that arrives from the chat server.
function mdLite(text){
  const lines = String(text || "").split(/\r?\n/);
  let out = "", para = [], list = [], table = [];
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/(^|[^\w*])_([^_\n]+)_(?![\w*])/g, "$1<em>$2</em>");
  const flushPara = () => { if (para.length) { out += "<p>" + inline(para.join(" ")) + "</p>"; para = []; } };
  const flushList = () => { if (list.length) { out += "<ul>" + list.map(l => "<li>" + inline(l) + "</li>").join("") + "</ul>"; list = []; } };
  const flushTable = () => {
    if (!table.length) return;
    let rows = "", header = true;
    for (const row of table) {
      const cells = row.replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => c.trim());
      if (cells.every(c => /^:?-{2,}:?$/.test(c || "-"))) { header = false; continue; }
      const tag = header ? "th" : "td"; header = false;
      rows += "<tr>" + cells.map(c => "<" + tag + ">" + inline(c).replace(/&lt;br&gt;/g, "<br>") + "</" + tag + ">").join("") + "</tr>";
    }
    out += '<div class="tblwrap"><table>' + rows + "</table></div>"; table = [];
  };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) { flushPara(); flushList(); flushTable(); continue; }
    if (line.startsWith("|")) { flushPara(); flushList(); table.push(line); continue; }
    if (/^[-*•]\s+/.test(line)) { flushPara(); flushTable(); list.push(line.replace(/^[-*•]\s+/, "")); continue; }
    if (/^#{1,6}\s/.test(line)) { flushPara(); flushList(); flushTable(); out += "<h4>" + inline(line.replace(/^#{1,6}\s+/, "")) + "</h4>"; continue; }
    flushList(); flushTable(); para.push(line);
  }
  flushPara(); flushList(); flushTable();
  return out;
}

/* -------- top bar -------- */
function initBar(){
  const docsel = $("docsel");
  syncDocOptions();
  docsel.onchange = () => selectDoc(docsel.value);
  $("modetabs").querySelectorAll("button").forEach(b => {
    b.onclick = () => { state.mode = b.dataset.mode; render(); window.scrollTo(0, 0); fitStage(); };
  });
  $("qsubtabs").querySelectorAll("button").forEach(b => {
    b.onclick = () => { state.qsub = b.dataset.sub; render(); };
  });
  $("wsopen").onclick = openWorkspaceModal;
  $("modal").onclick = e => { if (e.target === $("modal")) closeModal(); };
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { hideTip(); closeModal(); return; }
    // Left / right (or p / n) walk the disagreements while Sunum is open.
    if (state.mode !== "presentation" || $("modal").classList.contains("hidden") === false) return;
    const tag = (e.target && e.target.tagName || "").toLowerCase();
    if (["input", "select", "textarea"].includes(tag)) return;
    if (e.key === "ArrowRight" || e.key === "n") { stepLaneDiff(1); e.preventDefault(); }
    else if (e.key === "ArrowLeft" || e.key === "p") { stepLaneDiff(-1); e.preventDefault(); }
  });
  initTips();
  // Coming back to this tab after creating a knowledge base in the console is
  // the demo's natural gesture: re-read the console then, throttled so a busy
  // alt-tab does not turn into a request per switch.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && Date.now() - workspace.at > 10000) loadWorkspace();
  });
  measureBar();
  window.addEventListener("resize", () => { measureBar(); fitStage(); });
  loadWorkspace();
}

// The top bar wraps at narrow widths, so its height is a measurement, not
// a constant: sticky table headers, side cards and scroll targets read it.
function measureBar(){
  const h = Math.round(document.querySelector(".topbar").getBoundingClientRect().height);
  document.documentElement.style.setProperty("--barh", h + "px");
}

// The document's own sections, as a reader would name them: a run of units
// sharing one section path. This is what the reader navigates by -- a page is
// where something is printed, a section is what it is about.
function docSections(){
  const doc = D();
  if (doc._sections) return doc._sections;
  // Group at the document's own top level -- its chapters. The full section
  // path would give hundreds of two-unit slivers, which is a worse thing to
  // navigate than the pages it replaced.
  const out = [];
  let current = null;
  for (const unit of doc.units) {
    const key = (unit.sd || [])[0] || "";
    if (!current || current.key !== key) {
      current = {i: out.length, key, title: key || "Belge başı", units: [], pages: new Set()};
      out.push(current);
    }
    current.units.push(unit);
    current.pages.add(unit.p);
  }
  for (const section of out) section.pages = [...section.pages].sort((a, b) => a - b);
  doc._sections = out;
  return out;
}
// Open on the first chapter that has something to read, not on a cover page.

// Which methods the reader is comparing, LEFT TO RIGHT: the order is the
// order they were picked, so the first method chosen is the first column.
// Defaults to the two that answer the product's question -- the base method
// and the premium one -- when both are there.
function laneList(){
  const have = docArms();
  const wanted = (state.lanes || []).filter(a => have.includes(a));
  if (wanted.length) return wanted;
  if (have.includes("structure-only")) {
    const other = ["agentic", "markdown", "hybrid"].find(a => have.includes(a));
    return other ? have.filter(a => a === "structure-only" || a === other) : ["structure-only"];
  }
  return have.slice(0, 2);
}
function setLanes(lanes){
  const have = docArms();
  const kept = [];
  for (const a of lanes) if (have.includes(a) && !kept.includes(a)) kept.push(a);
  if (!kept.length) return;
  state.lanes = kept;
  if (!kept.includes(state.arm)) state.arm = kept[0];
  if (!kept.includes(selArm())) { state.selArm = kept[0]; state.selChunk = null; }
}
// One state for "which methods are on screen": a method card, a lane chip and
// a column head all toggle the same list, and none of them can empty it. A
// method joins at the right-hand end -- the column order is the pick order.
function toggleLane(arm){
  const lanes = laneList();
  const next = lanes.includes(arm) ? lanes.filter(a => a !== arm) : lanes.concat([arm]);
  if (!next.length) return;
  // Adding a method must not move the reader: the boundary they were standing
  // on stays the current one whenever it is still a disagreement.
  const was = state.diffIdx >= 0 ? stepDiffs()[state.diffIdx] : null;
  setLanes(next);
  const now = stepDiffs();
  state.diffIdx = was ? now.findIndex(d => d.before === was.before) : -1;
  if (state.diffIdx < 0) state.diffIdx = now.findIndex(d => d.p === state.page);
  state.unfolded = new Set();
  render();
}

// Where the compared methods disagree: between two consecutive content units,
// at least one lane cuts and at least one does not. Computed over the lanes on
// screen, so the count always matches what the reader is looking at.
function laneDiffs(){
  const lanes = laneList();
  if (lanes.length < 2) return [];
  const doc = D();
  const key = lanes.join("|");
  doc._diffs = doc._diffs || {};
  if (doc._diffs[key]) return doc._diffs[key];
  const content = doc.units.filter(u => u.t !== "heading");
  const points = [];
  for (let k = 1; k < content.length; k++) {
    const left = content[k - 1], right = content[k];
    const cuts = [];
    let usable = true;
    for (const arm of lanes) {
      const m = D().arms[arm].m;
      const a = m[left.i], b = m[right.i];
      if (a === undefined || b === undefined) { usable = false; break; }
      cuts.push(a !== b);
    }
    if (usable && cuts.some(Boolean) && !cuts.every(Boolean)) {
      points.push({after: left.i, before: right.i, p: right.p,
                   cut: lanes.filter((a, i) => cuts[i]), kept: lanes.filter((a, i) => !cuts[i])});
    }
  }
  doc._diffs[key] = points;
  return points;
}
// Reading-order index of a unit id, built once per document.
function uidx(id){
  const doc = D();
  if (!doc._uidx) { doc._uidx = new Map(); doc.units.forEach((u, i) => doc._uidx.set(u.i, i)); }
  return doc._uidx.get(id);
}

function pageList(){ return D().pages; }
function firstContentPage(){
  // Open on the first page with something to read: a cover, or a page holding
  // one stray line, is a poor first view of a comparison.
  const content = {};
  for (const unit of D().units) {
    if (unit.t !== "heading") content[unit.p] = (content[unit.p] || 0) + 1;
  }
  const pages = D().pages;
  return pages.find(p => (content[p] || 0) >= 3)
    || pages.find(p => content[p]) || pages[0];
}
function syncPage(){
  const pages = pageList();
  if (state.page === null) state.page = firstContentPage();
  if (!pages.includes(state.page)) state.page = pages[0];
}

function syncBar(){
  $("modetabs").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.mode === state.mode));
  if (state.mode !== "debug") return;
  // Debug reads the document page by page, from its own toolbar.
  syncPage();
  const pages = pageList();
  const at = pages.indexOf(state.page);
  const sel = $("pagesel");
  sel.innerHTML = pages.map(p => `<option value="${p}">${p}</option>`).join("");
  sel.value = state.page;
  sel.onchange = () => { state.page = Number(sel.value); render(); };
  $("dbgprev").disabled = at <= 0;
  $("dbgnext").disabled = at >= pages.length - 1;
  $("dbgprev").onclick = () => { state.page = pages[Math.max(0, at - 1)]; render(); };
  $("dbgnext").onclick = () => { state.page = pages[Math.min(pages.length - 1, at + 1)]; render(); };
}

/* -------- Sunum: methods + results -------- */
function renderMethods(){
  const doc = D();
  const an = analysisState();
  const present = PRODUCT_ARMS.filter(a => doc.arms[a]);
  const missing = PRODUCT_ARMS.filter(a => !doc.arms[a]);
  const lanes = laneList();
  $("methods").innerHTML = present.map(a => {
    const arm = doc.arms[a];
    const naming = modeName(a);
    const badge = a === "structure-only" ? `<span class="pill std">temel yöntem</span>` :
      (a === "agentic" ? (isDeepArm(a)
        ? `<span class="pill deep">premium mod</span>${an.tag ? ` <span class="pill ${an.pill}">${esc(an.tag)}</span>` : ""}`
        : `<span class="pill grey">araştırma koşusu</span>`) :
      (a === "hybrid" ? `<span class="pill grey">araştırma kolu</span>` : `<span class="pill grey">taban çizgisi</span>`));
    const facts = [`${arm.chunks.length} parça`,
      arm.sq && arm.sq.token_count ? `medyan ${fmt(arm.sq.token_count.median, 0)} token` : "",
      a === "agentic" && isDeepArm(a) ? (an.ranModel ? `${deepMeta().calls.total} model çağrısı` : "model çalışmadı") : ""
    ].filter(Boolean);
    // On a document where no model was consulted, describing the model layer
    // would be describing something that did not happen.
    const desc = a === "agentic" && isLegacyAgentic()
      ? "Yapısal adaylar bölüm başına tek çağrıda oylanır; final seçim ve limitler deterministik kuralda kalır. Ayrı, model bağımlı bir koşudur."
      : (a === "agentic" && isDeepArm(a) && an.desc ? an.desc : METHOD_DESC[a]);
    // One claim per card. The mechanism is a sentence a reader can ask for,
    // not a paragraph four cards wide that has to be read before choosing.
    const impact = (a === "agentic" && isDeepArm(a) && an.impact ? an.impact : METHOD_IMPACT[a]) || desc;
    const aside = a === "markdown" || a === "hybrid";
    const on = lanes.includes(a);
    return `<div class="method ${aside ? "aside" : ""} ${on ? "on" : ""}" data-arm="${a}"
        style="--c:${LANE_COLOR[a] || "#94a3b8"};--c-soft:${LANE_SOFT[a] || "#eef2f6"}" title="${on ? "Karşılaştırmadan çıkar" : "Karşılaştırmaya ekle"}">
      <div class="name">${esc(naming.top)} ${badge}${info(desc)}</div>
      <div class="desc">${esc(impact)}</div>
      <div class="facts">${facts.map(f => `<span>${esc(f)}</span>`).join("")}
        <span class="inlane ${on ? "" : "add"}">${on ? "✓ karşılaştırmada" : "+ karşılaştır"}</span></div>
    </div>`;
  }).join("");
  // An absent method is explained once, in a line -- never faked, never a card.
  $("methodnote").innerHTML = missing.length
    ? `<div class="help">${missing.map(a => esc(absentReason(a))).join(" ")}</div>`
    : "";
  $("methods").querySelectorAll(".method").forEach(el => {
    el.onclick = () => toggleLane(el.dataset.arm);
  });
}

function absentReason(arm){
  const live = D().live;
  const state = live && live.methods ? (live.methods[arm] || {}) : null;
  if (state && state.status === "failed") return `${modeName(arm).top} çalıştırıldı ama tamamlanamadı: ${state.error || "bilinmeyen hata"}`;
  if (live) return `${modeName(arm).top} bu doküman için çalıştırılmadı. RAG Console'da bu yöntemi ekleyebilirsiniz.`;
  return `${modeName(arm).top} bu doküman için üretilmedi.`;
}

function smellSum(t){ return ["orphan_label","lead_in_cut","continuation_cut","run_split_when_fits","fragment_cut","table_split"].reduce((s, k) => s + (t && t[k] || 0), 0); }

function renderResults(opts){
  const dm = deepMeta();
  const box = $("results");
  if (!dm) {
    if (isLegacyAgentic()) {
      const am = D().agenticMeta || {}, bd = am.diff || {}, s = am.summary || {};
      box.innerHTML = sectionHead(opts && opts.step, "Agentic Chunker — ayrı koşu",
        "Bu doküman için ayrı, model bağımlı bir koşu var; Deep Analysis sözleşmesinin dışındadır ve bir kazanan ilan etmez.") +
        `<div class="results legacy"><div class="title"><span class="pill grey">Agentic Chunker — ayrı koşu</span> <span class="muted" style="font-weight:400;font-size:13px">model: ${esc(am.model || "—")} · mod: ${esc(am.mode || "—")} · kazanan ilan edilmez</span></div>
        <div class="grid">
          <div class="item"><div class="v">${bd.decision_windows ?? s.decision_window_count ?? "—"}</div><div class="k">karar penceresi</div></div>
          <div class="item"><div class="v">${bd.final_boundary_moved ?? s.final_boundary_moved_count ?? "—"}</div><div class="k">final sınırı taşınan</div></div>
          <div class="item"><div class="v">${s.provider_call_count ?? "—"}</div><div class="k">provider çağrısı</div></div>
        </div></div>`;
    } else box.innerHTML = "";
    return;
  }
  box.innerHTML = deepStory(dm, {step: opts && opts.step});
}

// The Standard -> Deep Analysis story, in the order a first-time reader needs
// it: what happened, then what the two modes are, then what keeps the result
// honest, then when it is worth choosing. Anything a reader would only ask
// second is behind the disclosure at the bottom -- present, not in the way.
function deepStory(dm, opts){
  const ts = dm.totals.standard || {}, td = dm.totals.deep || {};
  const sc = dm.storyCounts || {};
  const origin = sc.final_boundaries_by_origin || {};
  const secs = (dm.timing.llm_calls || 0) + (dm.timing.verifier_calls || 0) + (dm.timing.selection || 0);
  const retr = dm.retrieval || {};
  const doc = D();
  const an = analysisState();
  const llm = an.ranModel;
  const fixed = Math.max(0, dm.smellTotal.standard - dm.smellTotal.deep);
  const share = dm.smellTotal.standard ? Math.round(fixed / dm.smellTotal.standard * 100) : 0;
  const cost = llm ? "≈ $" + dm.estCostUsd.toFixed(3) : "ücretsiz";

  // The result, as one object: what document, what happened, what it cost.
  // Everything else on this screen supports it, so it is the only thing here
  // that is loud.
  const facts = [llm && dm.model ? esc(dm.model) : null].filter(Boolean);
  const heroNums = `<div class="hero-nums">
    <div class="n">
      <div class="v">${arrowValue(dm.smellTotal.standard, dm.smellTotal.deep)}</div>
      <div class="k">${term("smell")}</div>
      ${fixed ? `<span class="gain">−${fixed} · %${share}</span>` : `<span class="sub">değişmedi — Standard zaten temizdi</span>`}
    </div>
    <div class="n">
      <div class="v"><span class="to">${dm.regressions}</span></div>
      <div class="k">${term("regression")}</div>
      <div class="sub">${dm.regressions === 0 ? "hiçbir bölüm geriye gitmedi" : "sözleşme ihlali — incelenmeli"}</div>
    </div>
    <div class="n">
      <div class="v"><span class="to">${llm ? esc(cost) : "yok"}</span></div>
      <div class="k">bir kerelik maliyet${info(llm
        ? "Deep Analysis yalnız yükleme sırasında çalışır; sorgu anında ne maliyet ne gecikme ekler."
        : an.help)}</div>
      <div class="sub">${llm
        ? `${dm.calls.total} model çağrısı · ${secs ? secs.toFixed(0) + " s" : "—"} · yüklemede`
        : esc(an.short)}</div>
    </div>
  </div>`;
  const headline = fixed
    ? `<b>${fixed} yapısal kalite problemi giderildi.</b> Hiçbir bölüm Standard'ın gerisine düşmedi.`
    : `<b>Standard bölümleme bu dokümanda zaten temizdi.</b> Deep Analysis düzeltilecek problem bulmadı, hiçbir sınırı da kötüleştirmedi.`;
  const hero = `<div class="hero ${llm ? "" : "flat"}">
    <div class="hero-head">
      <div>
        <div class="hero-doc">Standard → Deep Analysis</div>
        ${facts.length ? `<div class="hero-facts">${facts.map(f => `<span>${f}</span>`).join("")}</div>` : ""}
      </div>
      <div class="hero-badge"><span class="pill">Deep Analysis</span>${an.tag ? `<span class="pill">${esc(an.tag)}</span>` : ""}</div>
    </div>
    ${heroNums}
    <div class="hero-line">${headline}</div>
  </div>`;

  // When to prefer which method -- one line, because that is the only part of
  // the methodology a reader of this screen has to act on.
  const when = `<div class="when">
    <div class="w"><b>Deep Analysis ne zaman değer?</b>Tablo, liste ve çok sayıda alt başlık içeren dokümanlarda — cevabın bir tablo satırını ya da madde listesini eksiksiz vermesi gerektiğinde.</div>
    <div class="w"><b>Ne zaman gerekmez?</b>Düz, tablosuz, kısa metinlerde Standard zaten aynı sınırları bulur.</div>
    <div class="w"><b>Maliyeti</b>${llm ? "Bir kerelik " + cost + ", yalnız yüklemede. Sorgu anında ek maliyet ve gecikme yok." : "Bu dokümanda model çalışmadı; kazanç ücretsiz."}</div>
  </div>`;

  const detail = `<details class="deep-detail"><summary>Yöntem ve ölçüm ayrıntısı</summary><div class="inner">
    <div class="guards">
      <div class="g llm"><b>Parçaları model belirlemez.</b> ${llm
        ? "Model yalnız kuralın kararsız kaldığı " + (sc.llm_consulted_sections ?? "birkaç") + " bölümde öneri verir; her öneri iki ayrı sırada doğrulanır, doğrulanmayan geri alınır."
        : "Bu dokümanda sınırların hiçbirini model belirlemedi; sonucun tamamı kural katmanından geliyor."}</div>
      <div class="g rule"><b>Sonuç Standard'ın gerisine düşemez.</b> Hiçbir problem türünde daha kötü bir sonuç kabul edilmez; bu bir hedef değil, koşunun geçmek zorunda olduğu bir kural.</div>
    </div>
    <div class="kpis" style="margin-top:12px">
      ${kpi("Düzeltmeyi kim yaptı?", "Deep Analysis'in taşıdığı ya da eklediği chunk sınırlarının kaynağı.",
        `${origin.deterministic || 0}<span class="unit">kural</span><span class="arrow">+</span><span class="to">${origin.llm || 0}</span><span class="unit">model</span>`,
        (origin.deterministic || origin.llm)
          ? "Kazanımın büyük kısmı ücretsiz kural katmanından geliyor."
          : "Deep Analysis hiçbir sınırı taşımadı: Standard zaten temiz kesmişti.")}
      ${kpi(term("chunk"), null, arrowValue(dm.chunkCount.standard, dm.chunkCount.deep),
        "Parça sayısı tek başına iyi ya da kötü değildir; önemli olan sınırların nereden geçtiğidir.")}
      ${retr.deep && retr.standard
        ? kpi(term("hit"), null, arrowValue(fmt(retr.standard.hit_at_5, 3), fmt(retr.deep.hit_at_5, 3)),
            `${retr.deep.query_count} gold soruda. Fark bu örneklemde gürültü içindedir; iddia “daha iyi” değil, <b>“en az Standard kadar iyi”</b>dir.`)
        : kpi(term("goldset"), null, `<span class="unit" style="font-size:17px">ölçülmedi</span>`,
            "Bu dokümanın gold sorgu seti yok; arama karşılaştırması yapılmadı ve uydurulmadı.")}
      ${kpi(term("ceiling"), null, `${sc.ceiling_boundaries ?? "—"}`,
        "Tek bir tablo ya da paragraf bütçeden büyük olduğu için hiçbir yöntemin kaçınamayacağı kesim.")}
    </div>
    <div class="note" style="margin-top:12px">Her problem türü, parça sınırlarının şekline bakan deterministik bir sayaçtır — model yorumu değil. ${llm
      ? "Deep Analysis model kullandığı için aynı koşu birebir tekrarlanmaz; bir “kazanan yöntem” ilan edilmez."
      : "Bu koşuda model çalışmadı."} Eşikler PoC seviyesinde, optimize edilmemiş.</div>
  </div></details>`;

  return `<div class="results">
    ${sectionHead(opts && opts.step, "Sonuç", "Deep Analysis, Standard'ın bıraktığı yapısal problemlerin kaçını giderdi — ve bunun bedeli ne oldu?")}
    ${hero}
    ${an.warn ? `<div class="guard warn">${esc(an.short)} ${esc(an.help)}</div>` : ""}
    ${fixList(ts, td)}${when}${detail}
  </div>`;
}

// The improvement list: one row per defect type, plain label, Standard and
// Deep on the same scale. Silent when there was nothing to fix.
// One row per defect type: Standard's count above Deep's, drawn on one
// scale. A shorter lower bar is the message, so the rows that improved most
// look like it -- the previous drawing overlaid both bars from the same
// origin, which made an unchanged row the loudest thing in the chart.
function fixList(ts, td){
  const keys = ["orphan_label","lead_in_cut","continuation_cut","run_split_when_fits","table_split","fragment_cut"]
    .filter(k => (ts[k] || 0) + (td[k] || 0) > 0);
  if (!keys.length) return "";
  const max = Math.max(1, ...keys.map(k => Math.max(ts[k] || 0, td[k] || 0)));
  // Biggest wins first, unchanged rows last: the chart tells the story in
  // the order a reader would tell it.
  const ordered = keys.slice().sort((a, b) =>
    ((ts[b] || 0) - (td[b] || 0)) - ((ts[a] || 0) - (td[a] || 0)) || (ts[b] || 0) - (ts[a] || 0));
  const rows = ordered.map(k => {
    const s = ts[k] || 0, d = td[k] || 0;
    const gone = s > 0 && d === 0;
    const same = d >= s;
    const pct = v => Math.round(v / max * 100);
    return `<div class="fixrow ${gone ? "gone" : ""} ${same ? "flat" : ""}">
      <div class="name">${esc(SMELL_TEXT[k] || k)}${info(SMELL_HELP[k])}</div>
      <div class="bars">
        <div class="b std" title="Standard: ${s}">${s ? `<i style="width:${Math.max(2, pct(s))}%"></i>` : ""}</div>
        <div class="b deep" title="Deep Analysis: ${d}">${d ? `<i style="width:${Math.max(2, pct(d))}%"></i>` : ""}</div>
      </div>
      <div class="n">${s} <span class="muted">→</span> <span class="${same ? "kept" : "to"}">${d}</span>
        <small>${gone ? "tamamen giderildi" : same ? "değişmedi" : "−" + (s - d)}</small></div>
    </div>`;
  }).join("");
  return `<h3 class="sub" style="margin-top:20px">Ne düzeldi?</h3>
    <div class="fixlist">
      <div class="fixhead"><span>Problem türü</span>
        <span class="legend2">
          <span><i class="swatch" style="background:#9db4e8"></i>Standard</span>
          <span><i class="swatch" style="background:var(--deep)"></i>Deep Analysis</span>
        </span>
        <span style="text-align:right">Adet</span></div>
      ${rows}
    </div>`;
}

/* -------- Sunum: the comparison workspace -------- */
function pageUnits(page){ return D().units.filter(u => u.p === page); }
const baseId = raw => String(raw).split("#")[0];

// The divergences the reader walks. With three or four columns the list is
// dominated by the research arms -- 43 Standard/Deep points on kkb-2024 sit
// inside 423 once every method is on screen -- so the stepper can be asked
// to walk only the product's own story. Nothing is hidden either way: the
// board still draws every boundary, the numbering just follows the walk.
function pairFilterAvailable(){
  const lanes = laneList();
  return lanes.length > 2 && lanes.includes("structure-only") && lanes.includes("agentic");
}
function stepDiffs(){
  const all = laneDiffs();
  if (!state.pairOnly || !pairFilterAvailable()) return all;
  return all.filter(d => d.cut.includes("structure-only") !== d.cut.includes("agentic"));
}

// First and last reading-order position of every chunk of one method, built
// once. It is what lets a clipped card say how far it really runs.
function armRange(arm){
  const armData = D().arms[arm];
  if (armData._range) return armData._range;
  armData._range = armData.chunks.map(chunk => {
    let lo = Infinity, hi = -Infinity;
    for (const raw of chunk.u) {
      const j = uidx(baseId(raw));
      if (j === undefined) continue;
      if (j < lo) lo = j;
      if (j > hi) hi = j;
    }
    return lo === Infinity ? null : [lo, hi];
  });
  return armData._range;
}
// Which chunks of one method own one paragraph, in order. `seg` is the
// authority: `m` records only the FIRST chunk that contains a unit and drops
// the headings a method keeps out of its unit ids, so a card drawn from `m`
// alone would put Markdown's boundaries in the wrong places.
function unitOwners(armData, unit){
  const rows = armData.seg[unit.i];
  if (rows && rows.length) {
    const seen = [];
    for (const r of rows) if (!seen.includes(r[0])) seen.push(r[0]);
    return seen.sort((a, b) => a - b);
  }
  const c = armData.m[unit.i];
  return c === undefined ? [] : [c];
}
// Full paragraphs, or the first lines of each: three or four columns need the
// short form to fit a boundary and its context on one screen.
function shortText(){ return state.short === null ? laneList().length >= 3 : state.short; }

// Where the story opens: on the first place the compared methods disagree,
// so the first thing on screen is a real difference.
function syncCompareState(){
  const pages = D().pages;
  const diffs = stepDiffs();
  if (state.diffIdx >= diffs.length) state.diffIdx = -1;
  if (state.page === null || !pages.includes(state.page)) {
    if (diffs.length) { state.diffIdx = 0; state.page = diffs[0].p; }
    else state.page = firstContentPage();
    state.unfolded = new Set();
  }
  if (!laneList().includes(selArm())) { state.selArm = laneList()[0]; state.selChunk = null; }
}

// One line per method that cuts, one per method that continues, from the
// chunks that actually meet at this point -- never from a template alone.
function pointFacts(point){
  const doc = D();
  const at = arm => doc.arms[arm].chunks[doc.arms[arm].m[point.before]];
  const cut = point.cut.map(arm => {
    const chunk = at(arm);
    const isCont = chunk && chunk.cp !== null && chunk.cp !== undefined;
    const why = chunk ? (isCont ? (CONT_LABELS[chunk.rs] || "önceki parçanın devamı") : (REASONS[chunk.rs] || {label: chunk.rs}).label) : "";
    return {arm, chunk, why, short: shortReason(chunk)};
  });
  const kept = point.kept.map(arm => ({arm, chunk: at(arm)}));
  return {cut, kept, decision: pointDecision(point, cut, kept)};
}
// What Deep Analysis decided *at this boundary*, read from the chunk whose
// start this boundary is -- the one place the pipeline recorded it.
function pointDecision(point, cut, kept){
  if (!isDeepArm("agentic")) return "";
  const an = analysisState();
  const ranModel = Boolean(an && an.ranModel);
  const names = list => (list || []).map(s => SMELL_TEXT[s] || s).join(", ");
  // This boundary's own smells if the story recorded any; the change group's
  // set is a claim about the region, so it is worded as one.
  const why = d => {
    if (names(d.cut_smells)) return {text: names(d.cut_smells), own: true};
    if (names(d.removed_smells)) return {text: names(d.removed_smells), own: false};
    const size = d.size_effect && d.size_effect.below_min;
    if (size && size.final < size.standard) return {text: "çok kısa parça", own: true, size: true};
    return null;
  };
  // A model claim is only made when a model actually ran on this document.
  const how = d => d.origin === "llm" && ranModel ? "model önerisiyle" : "kalite kuralıyla";
  const std = cut.find(c => c.arm === "structure-only");
  if (std && point.kept.includes("agentic") && std.chunk && std.chunk.dec && std.chunk.dec.status === "std_changed") {
    const d = std.chunk.dec, w = why(d);
    const tail = !w ? "" : w.size ? ": kesim çok kısa bir parça bırakıyordu"
      : w.own ? `: kesim <i>${esc(w.text)}</i> üretiyordu`
      : `: bu bölgedeki Standard kesimleri <i>${esc(w.text)}</i> üretiyordu`;
    return `<b>Deep Analysis</b> Standard'ın bu kesimini ${how(d)} kaldırdı${tail}.`;
  }
  const deep = cut.find(c => c.arm === "agentic");
  if (deep && point.kept.includes("structure-only") && deep.chunk && deep.chunk.dec) {
    const d = deep.chunk.dec, w = why(d);
    const tail = !w ? "" : w.own ? `: Standard'ın kesimi <i>${esc(w.text)}</i> üretiyordu`
      : `: bu bölgedeki Standard kesimleri <i>${esc(w.text)}</i> üretiyordu`;
    if (d.status === "det_moved") return `<b>Deep Analysis</b> bu sınırı kalite kuralıyla ekledi${tail}.`;
    if (d.status === "llm_accepted") return ranModel
      ? `<b>Deep Analysis</b> bu sınırı modelin önerisiyle ekledi; öneriyi kural katmanı doğruladı.`
      : `<b>Deep Analysis</b> bu sınırı kural katmanıyla ekledi.`;
    if (d.status === "ceiling") return `<b>Zorunlu kesim:</b> bu blok tek başına bütçeden büyük; hiçbir yöntem bu kesimden kaçınamaz.`;
  }
  return "";
}
const laneVars = arm => `--c:${LANE_COLOR[arm] || "#94a3b8"};--c-soft:${LANE_SOFT[arm] || "#eef2f6"}`;

// The readout above the board: which divergence, where, and who did what.
// It is the sentence the board draws, so a presenter never has to say it.
function renderDvSum(){
  const box = $("dvsum");
  const lanes = laneList();
  const diffs = stepDiffs();
  const point = state.diffIdx >= 0 ? diffs[state.diffIdx] : null;
  const quiet = msg => { box.className = "dvsum quiet"; box.innerHTML = msg; };
  if (lanes.length < 2) return quiet("Karşılaştırmak için ikinci bir yöntem seçin — yanına ikinci kolon olarak eklenir.");
  if (!diffs.length) return quiet("Seçili yöntemler bu dokümanı her yerde aynı noktalardan kesiyor: ayrışma yok.");
  if (!point) return quiet("Bir ayrışma seçin: ← → tuşları, kolonların solundaki numaralar ya da doküman haritası.");
  const facts = pointFacts(point);
  const section = docSections().find(s => s.pages.includes(point.p));
  const ent = (arm, verb, cls, tail) => `<span class="ent" style="${laneVars(arm)}"><i class="dot"></i><b>${esc(modeName(arm).top)}</b>
    <span class="verb ${cls}">${verb}</span>${tail ? `<span class="m">${tail}</span>` : ""}</span>`;
  box.className = "dvsum";
  box.innerHTML = `<span class="ix">Ayrışma ${state.diffIdx + 1} / ${diffs.length}</span>
    <span class="pg">s. ${point.p}${section ? " · " + esc(section.title) : ""}</span>
    ${facts.cut.map(c => ent(c.arm, "burada yeni parça açtı", "cut",
      c.chunk ? `Parça ${c.chunk.num}${c.short ? " · " + esc(c.short) : ""}` : "")).join("")}
    ${facts.kept.map(k => ent(k.arm, "bölmedi, devam etti", "kept",
      k.chunk ? `Parça ${k.chunk.num} sürüyor` : "")).join("")}
    ${facts.decision ? `<span class="dec">${facts.decision}</span>` : ""}`;
}

// The toolbar: which methods are columns, which divergence, which page.
function renderCompareBar(step){
  const lanes = laneList();
  const have = docArms();
  const diffs = stepDiffs();
  const dm = deepMeta();
  // Left to right in the toolbar is left to right on the board.
  const order = lanes.concat(have.filter(a => !lanes.includes(a)));
  const chips = order.map(a => {
    const on = lanes.includes(a);
    const at = lanes.indexOf(a);
    return `<button class="lanechip ${on ? "on" : ""}" data-lane="${a}" style="${laneVars(a)}"
      aria-pressed="${on}" title="${on ? `${esc(modeName(a).top)}: ${at + 1}. kolon — karşılaştırmadan çıkarmak için tıklayın` : "Yeni kolon olarak ekle"}">${
      on ? `<span class="ord">${at + 1}</span>` : `<span class="dot"></span>`}${esc(modeName(a).top)} <span class="n">${D().arms[a].chunks.length}</span></button>`;
  }).join("");
  const off = PRODUCT_ARMS.filter(a => !have.includes(a)).map(a =>
    `<button class="lanechip off" disabled title="${esc(absentReason(a))}">${esc(modeName(a).top)} <span class="n">yok</span></button>`).join("");
  const pages = D().pages;
  const at = pages.indexOf(state.page);
  const pageOpts = pages.map(p => `<option value="${p}" ${p === state.page ? "selected" : ""}>${p}</option>`).join("");
  const counter = lanes.length < 2
    ? `<span class="count none">tek kolon — karşılaştırmak için ikinci bir yöntem seçin</span>`
    : (diffs.length
      ? `<span class="count">Ayrışma ${state.diffIdx >= 0 ? state.diffIdx + 1 : "–"} / ${diffs.length}</span>`
      : `<span class="count none">bu yöntemler her yerde aynı kesiyor</span>`);
  const short = shortText();
  $("cmpbar").innerHTML = `
    <div class="row">
      <span class="title"><span class="step">${step}</span>Parçaları karşılaştır</span>
      <span class="lab">Kolonlar</span>${chips}${off}
      <span class="grow">${dm ? `<button class="sonuc" id="gosonuc" title="Sonuç bandına in">Sonuç<span class="num"> · ${dm.smellTotal.standard} → ${dm.smellTotal.deep} yapısal problem</span> ↓</button>` : ""}</span>
    </div>
    <div class="row">
      <span class="diffstep"><span class="stepnav"><button id="prevdiff" ${diffs.length ? "" : "disabled"} title="Önceki ayrışma (←)">&#8592;</button>
        <button id="nextdiff" ${diffs.length ? "" : "disabled"} title="Sonraki ayrışma (→)">&#8594;</button></span>${counter}${
        info("Ayrışma: yöntemlerin farklı karar verdiği yer — bir kolon burada yeni bir parça açarken bir diğeri aynı parçada devam ediyor. Oklar (ya da ← → tuşları) sırayla hepsini gezer.")}</span>
      ${pairFilterAvailable() ? `<label class="conttoggle"><input type="checkbox" id="pairchk" ${state.pairOnly ? "checked" : ""}> Yalnız Standard ↔ Deep
        ${info("Üç ya da dört kolon açıkken ayrışmaların çoğu araştırma kollarından gelir. Bu kutu gezinmeyi ürünün kendi hikâyesiyle sınırlar; kolonlarda hiçbir sınır gizlenmez.")}</label>` : ""}
      <span class="sep"></span>
      <span class="lab">Sayfa</span><span class="stepnav"><button id="prevpage" ${at <= 0 ? "disabled" : ""}>&#8592;</button></span>
      <select id="pagenav">${pageOpts}</select><span class="stepnav"><button id="nextpage" ${at >= pages.length - 1 ? "disabled" : ""}>&#8594;</button></span>
      <span class="muted">${pages.length} sayfa</span>
      <span class="grow">
        <span class="lab">Metin</span><span class="seg2"><button data-short="0" class="${short ? "" : "on"}">Tam</button><button data-short="1" class="${short ? "on" : ""}">Kısa</button></span>
        <label class="conttoggle"><input type="checkbox" id="foldchk" ${state.foldAgree ? "checked" : ""}> Sadece ayrışmalar
          ${info("Bütün kolonların aynı kararı verdiği paragraf bloklarını tek satıra katlar; her ayrışmanın çevresinde iki paragraf bağlam kalır. Katlanan blok tıklanınca açılır.")}</label>
      </span>
    </div>`;
  $("cmpbar").querySelectorAll("button[data-lane]").forEach(el => { el.onclick = () => toggleLane(el.dataset.lane); });
  $("cmpbar").querySelectorAll("button[data-short]").forEach(el => {
    el.onclick = () => { state.short = el.dataset.short === "1"; state.tall = new Set(); render(); };
  });
  $("prevdiff").onclick = () => stepLaneDiff(-1);
  $("nextdiff").onclick = () => stepLaneDiff(1);
  $("pagenav").onchange = e => goPage(Number(e.target.value));
  $("prevpage").onclick = () => goPage(pages[Math.max(0, at - 1)]);
  $("nextpage").onclick = () => goPage(pages[Math.min(pages.length - 1, at + 1)]);
  $("foldchk").onchange = e => { state.foldAgree = e.target.checked; state.unfolded = new Set(); render(); };
  const pc = $("pairchk");
  // Switching the walk keeps the reader where they are: the boundary they
  // were standing on stays current whenever it survives the filter.
  if (pc) pc.onchange = e => {
    const was = state.diffIdx >= 0 ? diffs[state.diffIdx] : null;
    state.pairOnly = e.target.checked;
    const now = stepDiffs();
    state.diffIdx = was ? now.findIndex(d => d.before === was.before) : -1;
    if (state.diffIdx < 0) state.diffIdx = now.findIndex(d => d.p === state.page);
    render();
  };
  const go = $("gosonuc");
  if (go) go.onclick = () => $("results").scrollIntoView({behavior: "smooth", block: "start"});
}
function goPage(p){
  state.page = p;
  state.diffIdx = stepDiffs().findIndex(d => d.p === p);
  state.unfolded = new Set();
  render();
}

// Move to the next place the compared methods disagree, wherever it is: the
// page follows the difference, not the other way round.
function stepLaneDiff(delta){
  const diffs = stepDiffs();
  if (!diffs.length) return;
  state.diffIdx = (state.diffIdx + delta + diffs.length) % diffs.length;
  state.page = diffs[state.diffIdx].p;
  state.unfolded = new Set();
  render();
}

const NUMS = ["", "bir", "iki", "üç", "dört"];
function renderPresentation(){
  let step = 0;
  const hasStory = Boolean(deepMeta()) || isLegacyAgentic();
  syncCompareState();
  renderCompareBar(++step);
  renderDvSum();
  renderBoard();
  renderPresDetail();
  renderResults({step: hasStory ? ++step : null});
  $("methodhead").innerHTML = inner(sectionHead(++step, "Yöntemler",
    `Bu doküman ${NUMS[docArms().length] || docArms().length} yöntemle parçalandı. Karta tıklamak yöntemi yukarıdaki karşılaştırmaya bir kolon olarak ekler ya da çıkarır.`));
  renderMethods();
  fitStage();
  focusBoard();
}

// The workspace fills what is left of the first screen; the story starts below.
function fitStage(){
  const stage = $("stage");
  if (!stage || state.mode !== "presentation" || window.innerWidth <= 1100) return;
  const top = stage.getBoundingClientRect().top + window.scrollY;
  stage.style.height = Math.max(420, window.innerHeight - top - 18) + "px";
}
// Bring the thing the reader asked for into the board: the current
// divergence, else the selected chunk, else the first divergence on screen.
// The same landing fraction every time, so the boundary stops moving.
function focusBoard(){
  const bd = $("board");
  if (!bd) return;
  let el = null;
  if (state.diffIdx >= 0) el = bd.querySelector(`.gut[data-diff="${state.diffIdx}"]`);
  if (!el && state.selChunk !== null) el = bd.querySelector(".cell.sel");
  if (!el) el = bd.querySelector(".gut.bd.dv");
  bd.scrollTop = el ? Math.max(0, el.offsetTop - Math.round(bd.clientHeight * 0.32)) : 0;
}

// Which paragraphs the board draws: the open page with two paragraphs of
// context on each side, widened to hold the lead-in of every divergence on
// the page and the whole of the two chunks that meet at the current one.
function boardWindow(page, diffs, cur, lanes){
  const doc = D();
  const first = uidx(page[0].i), last = uidx(page[page.length - 1].i);
  let from = first - 2, to = last + 2;
  for (const d of diffs) if (d.p === state.page) from = Math.min(from, uidx(d.after));
  if (cur) {
    for (const arm of lanes) {
      for (const uid of [cur.after, cur.before]) {
        const unit = unitById(uid);
        if (!unit) continue;
        for (const c of unitOwners(doc.arms[arm], unit)) {
          const range = armRange(arm)[c];
          if (!range) continue;
          if (range[0] < from) from = range[0];
          if (range[1] > to) to = range[1];
        }
      }
    }
  }
  from = Math.max(0, from);
  to = Math.min(doc.units.length - 1, to);
  // A size-first chunk can cover a hundred paragraphs; the board is a screen,
  // not a document, so the window is capped around what the reader came for.
  const anchor = cur ? uidx(cur.after) : first;
  if (to - from > 120) {
    from = Math.max(from, Math.min(anchor - 40, first));
    to = Math.min(to, Math.max(anchor + 40, from + 80));
  }
  return {from, to};
}

// Every display piece of one paragraph in one method: a character range and
// the chunks that own it. A range owned by two chunks is a real overlap --
// the size-first splitter carries a tail forward -- and is drawn as one, so
// the shared characters are printed once and shaded, never repeated.
function unitPieces(armData, unit){
  const rows = armData.seg[unit.i];
  if (!rows || !rows.length) return null;
  const stops = [...new Set(rows.reduce((acc, r) => acc.concat([r[1], r[2]]), []))].sort((a, b) => a - b);
  const out = [];
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i], b = stops[i + 1];
    if (b <= a) continue;
    const owners = rows.filter(r => r[1] <= a && r[2] >= b).map(r => r[0]).sort((x, y) => x - y);
    if (!owners.length) continue;
    const last = out[out.length - 1];
    if (last && last.owners.length === owners.length && last.owners.every((c, k) => c === owners[k])) last.to = b;
    else out.push({from: a, to: b, owners});
  }
  return out.length ? out : null;
}

// One method's column over the window: which chunk each paragraph enters and
// leaves in, the chunk it was in just before the window, and the pieces to
// draw when a boundary falls inside a paragraph.
function laneCells(arm, rows, from){
  const doc = D(), armData = doc.arms[arm];
  const owners = rows.map(r => unitOwners(armData, r.unit));
  const pieces = rows.map(r => unitPieces(armData, r.unit));
  const ent = new Array(rows.length), ext = new Array(rows.length);
  for (let k = 0; k < rows.length; k++) {
    ent[k] = owners[k].length ? owners[k][0] : undefined;
    ext[k] = owners[k].length ? owners[k][owners[k].length - 1] : undefined;
  }
  // A unit no chunk claims (a heading a method keeps out of both maps) is
  // read with the chunk that follows it, as the reader would read it.
  let below;
  for (let k = rows.length - 1; k >= 0; k--) {
    if (ent[k] !== undefined) below = ent[k];
    else { ent[k] = below; ext[k] = below; }
  }
  let before;
  for (let i = from - 1; i >= 0 && before === undefined; i--) {
    const own = unitOwners(armData, doc.units[i]);
    if (own.length) before = own[own.length - 1];
  }
  return {ent, ext, owners, pieces, before};
}

// The board: one grid, one column per method, one row per paragraph.
function renderBoard(){
  const doc = D();
  const lanes = laneList();
  const bd = $("board");
  const all = doc.units;
  const page = pageUnits(state.page);
  bd.style.setProperty("--n", lanes.length);
  if (!page.length) { bd.innerHTML = `<div class="empty">Bu sayfada birim yok.</div>`; renderDocMap(); return; }
  const diffs = stepDiffs();
  const cur = state.diffIdx >= 0 ? diffs[state.diffIdx] : null;
  const win = boardWindow(page, diffs, cur, lanes);
  const from = win.from, to = win.to;
  const rows = [];
  for (let i = from; i <= to; i++) rows.push({unit: all[i], ctx: all[i].p !== state.page});

  const lane = {};
  for (const arm of lanes) lane[arm] = laneCells(arm, rows, from);
  const sel = selArm();
  const startsAt = (arm, k) => {
    const L = lane[arm];
    return L.ent[k] !== undefined && L.ent[k] !== (k > 0 ? L.ext[k - 1] : L.before);
  };
  // The chunks that meet at the current divergence are what the reader was
  // sent here to look at, so they are the only ones drawn in colour.
  const foc = {};
  for (const arm of lanes) {
    const set = new Set();
    if (cur) {
      const a = unitById(cur.after), b = unitById(cur.before);
      const oa = a ? unitOwners(doc.arms[arm], a) : [], ob = b ? unitOwners(doc.arms[arm], b) : [];
      if (oa.length) set.add(oa[oa.length - 1]);
      if (ob.length) set.add(ob[0]);
    }
    foc[arm] = set;
  }
  // A divergence is defined between two CONTENT units, and headings can sit
  // between them; its badge belongs on the row where a cutting column really
  // opens a chunk, not on an arbitrary offset from the lead-in.
  const dvAt = new Map();
  diffs.forEach((point, idx) => {
    const lo = uidx(point.after) - from + 1, hi = uidx(point.before) - from;
    let row = -1;
    for (let k = Math.max(1, lo); k <= Math.min(rows.length - 1, hi) && row < 0; k++) {
      if (point.cut.some(arm => lanes.includes(arm) && startsAt(arm, k))) row = k;
    }
    if (row < 0 && lo > 0 && lo < rows.length) row = lo;
    if (row > 0 && !dvAt.has(row)) dvAt.set(row, {point, idx});
  });
  const num = (arm, c) => doc.arms[arm].chunks[c] ? "Parça " + doc.arms[arm].chunks[c].num : "";
  // What every column must draw for one paragraph, decided ONCE for the row.
  // A table or a list is never sliced -- its rendering is a table, not a
  // string -- so a chunk that starts inside one is named on a note line
  // instead; a paragraph is sliced at the union of every column's offsets,
  // which is what keeps the columns level whatever each method decided.
  const isRich = u => u.t === "table" || u.t === "list";
  const rowPlan = rows.map((row, k) => {
    const stops = new Set();
    let anySplit = false;
    for (const arm of lanes) {
      const p = lane[arm].pieces[k];
      if (!p || p.length < 2) continue;
      anySplit = true;
      for (let i = 1; i < p.length; i++) stops.add(p[i].from);
    }
    const slice = anySplit && !isRich(row.unit);
    const notes = {};
    let hasNote = false;
    for (const arm of lanes) {
      const p = lane[arm].pieces[k];
      const prev = k > 0 ? lane[arm].ext[k - 1] : lane[arm].before;
      let text = "";
      if (p && !slice) {
        const fresh = [...new Set(p.reduce((acc, x) => acc.concat(x.owners), []))].filter(c => c !== prev);
        if (fresh.length) {
          const names = fresh.map(c => num(arm, c)).filter(Boolean).join(" → ");
          text = p.length > 1 ? `${names} · bu bloğun içinde başlıyor`
            : `${names} · önceki parçayla örtüşüyor`;
        }
      }
      notes[arm] = text;
      if (text) hasNote = true;
    }
    return {slice, stops: [...stops].sort((a, b) => a - b), notes, hasNote};
  });
  // "Sadece ayrışmalar": keep every divergence with two paragraphs of context.
  let keep = null;
  if (state.foldAgree && lanes.length > 1 && dvAt.size) {
    keep = new Set();
    for (const [k] of dvAt) for (let j = Math.max(0, k - 2); j <= Math.min(rows.length - 1, k + 2); j++) keep.add(j);
  }

  const cellCls = (arm, k, extra) => {
    const L = lane[arm], own = L.owners[k] || [];
    const c = L.ent[k];
    return ["cell", extra, c === undefined ? "none" : (c % 2 ? "alt" : ""),
      [...foc[arm]].some(f => f === c || f === L.ext[k] || own.includes(f)) ? "foc" : "",
      arm === sel && state.selChunk !== null && (c === state.selChunk || L.ext[k] === state.selChunk || own.includes(state.selChunk)) ? "sel" : "",
      rows[k] && rows[k].ctx ? "ctx" : ""].filter(Boolean).join(" ");
  };
  const openCell = (arm, k, chunk, cont, extra) => {
    const why = chunk ? (REASONS[chunk.rs] || {label: chunk.rs}).label : "";
    if (cont) {
      const range = chunk ? armRange(arm)[lane[arm].ent[k]] : null;
      const back = range ? from - range[0] : 0;
      return `<div class="${cellCls(arm, k, extra)}" style="${laneVars(arm)}">
        <div class="open cont"><span class="num">${chunk ? "Parça " + chunk.num : "—"}</span><span class="why">${
          chunk ? (back > 0 ? `${back} paragraf önce başladı, burada sürüyor` : "yukarıdan sürüyor") : "bu yöntemde parça yok"}</span></div></div>`;
    }
    return `<div class="${cellCls(arm, k, extra)}" style="${laneVars(arm)}">
      ${k > 0 || lane[arm].before !== undefined ? `<div class="close${k === 0 ? " dash" : ""}"></div>` : ""}<div class="gap"></div>
      <button class="open" data-chunk="${lane[arm].ent[k]}" data-arm="${arm}"
        title="${esc(modeName(arm).top)} · Parça ${chunk.num} · ${chunk.n} token · ${esc(why)}">
        <span class="num">Parça ${chunk.num}</span><span class="why">${esc(why)}</span><span class="tk">${chunk.n} tk</span></button></div>`;
  };
  // A boundary row: whoever cut closes a card and opens the next one,
  // whoever did not runs a card straight through the same height.
  const boundaryRow = k => {
    const dv = dvAt.get(k);
    const here = Boolean(dv) && dv.idx === state.diffIdx;
    const mark = ["bd", dv ? "dv" : "", here ? "here" : ""].filter(Boolean).join(" ");
    let out = `<div class="gut ${mark}"${dv ? ` data-diff="${dv.idx}"` : ""}>${dv
      ? `<button class="dvchip" data-godiff="${dv.idx}" title="Ayrışma ${dv.idx + 1} / ${diffs.length} — buraya git">${dv.idx + 1}</button>` : ""}</div>`;
    for (const arm of lanes) {
      const c = lane[arm].ent[k];
      const chunk = c === undefined ? null : doc.arms[arm].chunks[c];
      if (startsAt(arm, k) && chunk) { out += openCell(arm, k, chunk, false, mark); continue; }
      const prev = k > 0 ? lane[arm].ext[k - 1] : lane[arm].before;
      const running = prev === undefined ? null : doc.arms[arm].chunks[prev];
      out += `<div class="${cellCls(arm, k, mark)}" style="${laneVars(arm)}"><div class="thru">${
        dv ? `<span class="lbl">${running ? `Parça ${running.num} sürüyor` : "parça yok"}</span>` : ""}</div></div>`;
    }
    return out;
  };
  // A paragraph row: the same text in every column, so only the cards move.
  const seamLine = (arm, text) => `<div class="seamrow">${
    text ? `<span class="seam" style="${laneVars(arm)}">${esc(text)}</span>` : ""}</div>`;
  const ownersIn = (pieces, a, b) => {
    if (!pieces) return [];
    const hit = pieces.find(p => p.from <= a && p.to >= b) || pieces.find(p => p.from < b && p.to > a);
    return hit ? hit.owners : [];
  };
  const cellBody = (arm, k, unit) => {
    const L = lane[arm];
    const plan = rowPlan[k];
    if (L.ent[k] === undefined) {
      return `${plan.hasNote ? seamLine(arm, "") : ""}<div class="miss">${
        unit.t === "heading" ? "başlık · parçaya sayılmadı" : "bu yöntemde parça yok"}</div>`;
    }
    const pieces = L.pieces[k];
    const prev = k > 0 ? L.ext[k - 1] : L.before;
    if (plan.slice) {
      // Sliced at the union of every column's offsets, so the same character
      // starts a new block in every column and the row stays level.
      const stops = plan.stops.concat([unit.x.length]);
      let seen = prev === undefined ? [] : [prev];
      let out = "", at = 0;
      for (let i = 0; i < stops.length; i++) {
        const end = stops[i];
        const own = ownersIn(pieces, at, end);
        if (i > 0) {
          const fresh = own.filter(c => !seen.includes(c));
          out += seamLine(arm, fresh.length
            ? `${fresh.map(c => num(arm, c)).filter(Boolean).join(" + ")} · buradan itibaren${own.length > 1 ? " · örtüşme" : ""}`
            : "");
        }
        out += `<div class="body pre${own.length > 1 ? " ov" : ""}" style="${laneVars(arm)}">${esc(unit.x.slice(at, end))}</div>`;
        if (own.length) seen = own.slice();
        at = end;
      }
      return out;
    }
    const own = pieces ? [...new Set(pieces.reduce((acc, x) => acc.concat(x.owners), []))] : [];
    return `${plan.hasNote ? seamLine(arm, plan.notes[arm]) : ""}<div class="body${
      own.length > 1 ? " ov" : ""}" style="${laneVars(arm)}">${unitHtml(unit)}</div>`;
  };
  const short = shortText();
  const unitRow = (k, pageMark) => {
    const row = rows[k];
    const len = (row.unit.x || "").length;
    const clippable = short ? len > 300 : len > 1400;
    const opened = state.tall.has(row.unit.i);
    const clip = clippable && !opened;
    let out = `<div class="gut ur">${pageMark ? `<span class="pg">s.${row.unit.p}</span>` : ""}${
      clippable ? `<button class="tall" data-tall="${esc(row.unit.i)}" title="${opened ? "Kısalt" : "Paragrafın tamamını göster"}">${opened ? "▴" : "▾"}</button>` : ""}</div>`;
    for (const arm of lanes) {
      out += `<div class="${cellCls(arm, k, "ur" + (clip ? " clip" : ""))}" style="${laneVars(arm)}${short ? ";--cliph:118px" : ""}"
        data-uid="${esc(row.unit.i)}" data-arm="${arm}"${lane[arm].ent[k] !== undefined ? ` data-chunk="${lane[arm].ent[k]}"` : ""}>
        <div class="ck">${cellBody(arm, k, row.unit)}</div></div>`;
    }
    return out;
  };

  const first = uidx(page[0].i), last = uidx(page[page.length - 1].i);
  const edge = (label, p) => `<div class="wide edge"><button data-page="${p}">${esc(label)}</button></div>`;
  const seen = arm => {
    const set = new Set();
    for (let k = 0; k < rows.length; k++) for (const c of (lane[arm].owners[k] || [])) set.add(c);
    return set.size;
  };
  let out = `<div class="colhead gut"></div>` + lanes.map(arm => `<div class="colhead" style="${laneVars(arm)}">
      <span class="dot"></span><span class="nm">${esc(modeName(arm).top)}</span>
      <span class="n">${doc.arms[arm].chunks.length} parça · burada ${seen(arm)}</span>
      ${lanes.length > 1 ? `<button class="drop" data-drop="${arm}" title="Bu kolonu kaldır">&times;</button>` : ""}</div>`).join("");
  if (from < first) out += edge(`← s. ${all[from].p} sonu`, all[from].p);
  // The opening row says which chunk each column is already inside.
  out += `<div class="gut bd"></div>` + lanes.map(arm => {
    const c = lane[arm].ent[0];
    const chunk = c === undefined ? null : doc.arms[arm].chunks[c];
    return startsAt(arm, 0) && chunk ? openCell(arm, 0, chunk, false, "bd") : openCell(arm, 0, chunk, true, "bd");
  }).join("");

  let k = 0, openUntil = -1, lastPage = null;
  while (k < rows.length) {
    if (keep && !keep.has(k) && k >= openUntil) {
      // A run every column agrees on: one line that says what it hides.
      let j = k;
      while (j < rows.length && !keep.has(j)) j++;
      const run = rows.slice(k, j), id = run[0].unit.i;
      if (!state.unfolded.has(id)) {
        let common = 0;
        for (let r = k; r < j; r++) if (r > 0 && lanes.every(arm => startsAt(arm, r))) common++;
        out += `<button class="wide fold" data-unfold="${esc(id)}">··· ${run.length} paragraf gizli — ${
          lanes.length === 2 ? esc(modeName(lanes[0]).top) + " ve " + esc(modeName(lanes[1]).top) : "bütün kolonlar"} burada aynı kararı verdi${
          common ? `, ${common} yerde hepsi böldü` : ""} · <span class="op">aç</span></button>`;
        k = j;
        lastPage = null;
        continue;
      }
      openUntil = j;
    }
    if (k > 0 && lanes.some(arm => startsAt(arm, k))) out += boundaryRow(k);
    out += unitRow(k, rows[k].unit.p !== lastPage);
    lastPage = rows[k].unit.p;
    k++;
  }
  // The closing row: a card left open says how much further it really runs.
  out += `<div class="gut bd"></div>` + lanes.map(arm => {
    const c = lane[arm].ext[rows.length - 1];
    const range = c === undefined ? null : armRange(arm)[c];
    const more = range ? range[1] - to : 0;
    return `<div class="${cellCls(arm, rows.length - 1, "bd")}" style="${laneVars(arm)}"><div class="close dash"></div>${
      more > 0 ? `<div class="tail">${num(arm, c)} · ${more} paragraf daha sürüyor</div>` : ""}</div>`;
  }).join("");
  if (to > last) out += edge(`s. ${all[to].p} başı →`, all[to].p);
  bd.innerHTML = out;

  bd.querySelectorAll("button[data-page]").forEach(b => { b.onclick = () => goPage(Number(b.dataset.page)); });
  bd.querySelectorAll("button[data-drop]").forEach(b => { b.onclick = () => toggleLane(b.dataset.drop); });
  bd.querySelectorAll("button[data-godiff]").forEach(b => {
    b.onclick = () => { state.diffIdx = Number(b.dataset.godiff); state.page = diffs[state.diffIdx].p; state.unfolded = new Set(); render(); };
  });
  bd.querySelectorAll("button[data-unfold]").forEach(b => {
    b.onclick = () => { const top = bd.scrollTop; state.unfolded.add(b.dataset.unfold); renderBoard(); bd.scrollTop = top; };
  });
  bd.querySelectorAll("button[data-tall]").forEach(b => {
    b.onclick = () => {
      const id = b.dataset.tall, top = bd.scrollTop;
      if (state.tall.has(id)) state.tall.delete(id); else state.tall.add(id);
      renderBoard();
      bd.scrollTop = top;
    };
  });
  bd.querySelectorAll("[data-chunk][data-arm]").forEach(el => {
    el.onclick = e => { e.stopPropagation(); pickChunk(el.dataset.arm, Number(el.dataset.chunk)); };
  });
  renderDocMap();
}

// A chunk is picked from its head or from any paragraph it owns; the whole
// card lights up in its own column and the panel explains that boundary.
function pickChunk(arm, idx){
  state.selArm = arm;
  state.selChunk = idx;
  const bd = $("board"), top = bd.scrollTop;
  renderBoard();
  renderPresDetail();
  bd.scrollTop = top;
}

// The whole document as one vertical strip: where the divergences are, and
// where the reader is. Click to go there.
function renderDocMap(){
  const box = $("docmap");
  const doc = D();
  const U = doc.units.length;
  const diffs = stepDiffs();
  const page = pageUnits(state.page);
  const W = 26;
  let svg = `<svg viewBox="0 0 ${W} ${U}" preserveAspectRatio="none">`;
  const tick = Math.max(1, Math.round(U / 320));
  if (diffs.length > 320) {
    const bins = 160, size = U / bins, counts = new Array(bins).fill(0);
    for (const d of diffs) counts[Math.min(bins - 1, Math.floor(uidx(d.before) / size))]++;
    const max = Math.max(...counts);
    counts.forEach((c, b) => { if (c) svg += `<rect x="5" y="${b * size}" width="${(W - 5) * c / max}" height="${size}" fill="#94a3b8"><title>${c} ayrışma</title></rect>`; });
  } else {
    diffs.forEach((d, i) => { svg += `<rect x="5" y="${uidx(d.before)}" width="${W - 5}" height="${tick}" fill="${i === state.diffIdx ? "#0f172a" : "#94a3b8"}"/>`; });
  }
  if (page.length) svg += `<rect x="0" y="${uidx(page[0].i)}" width="${W}" height="${Math.max(tick, uidx(page[page.length - 1].i) - uidx(page[0].i) + 1)}" fill="rgba(29,78,216,.16)" stroke="rgba(29,78,216,.55)" stroke-width="0.6" vector-effect="non-scaling-stroke"/>`;
  if (state.diffIdx >= 0 && diffs[state.diffIdx]) svg += `<rect x="0" y="${uidx(diffs[state.diffIdx].before)}" width="${W}" height="${tick * 1.8}" fill="#0f172a"/>`;
  box.innerHTML = svg + `</svg>`;
  box.onclick = e => {
    const r = box.getBoundingClientRect();
    const idx = Math.min(U - 1, Math.max(0, Math.floor((e.clientY - r.top) / r.height * U)));
    let best = -1, dist = Infinity;
    diffs.forEach((d, i) => { const di = Math.abs(uidx(d.before) - idx); if (di < dist) { dist = di; best = i; } });
    state.unfolded = new Set();
    if (best >= 0 && dist <= U / 100) { state.diffIdx = best; state.page = diffs[best].p; }
    else { state.page = doc.units[idx].p; state.diffIdx = diffs.findIndex(d => d.p === state.page); }
    render();
  };
}

function expansionBudget(){ const budgets = D().meta.budgets || {}; return budgets.hard_max_tokens || 1126; }
function jumpToChunk(idx, arm){
  if (arm) state.arm = arm;
  if (!laneList().includes(state.arm)) setLanes(laneList().concat([state.arm]));
  const chunk = D().arms[state.arm].chunks[idx];
  state.selArm = state.arm;
  state.selChunk = idx;
  state.mode = "presentation";
  state.diffIdx = -1;
  state.unfolded = new Set();
  if (chunk.pg.length) state.page = chunk.pg[0];
  render();
  $("stage").scrollIntoView({block: "start"});
}

function sectionStory(si){
  const story = D().story;
  if (!story || si === null || si === undefined) return null;
  return story.sections.find(s => s.i === si) || null;
}

function armNoteFor(arm){
  if (arm === "hybrid") return "Hybrid: bütçeyi aşan bölümlerde kesim yerini embedding benzerliği seçer. Araştırma koludur.";
  if (arm === "markdown") {
    const diag = D().meta.diag[arm] || {};
    return `Markdown: bölüm yapısına bakmaz; ${diag.chunk_size_tokens ?? 700} token hedefi, ${diag.chunk_overlap_tokens ?? 140} token örtüşme.`;
  }
  if (arm === "agentic" && isLegacyAgentic()) return "Agentic Chunker: ayrı, model bağımlı bir koşu. Kazanan iddiası yoktur.";
  if (arm === "agentic") {
    const an = analysisState();
    return "Deep Analysis: Standard'ın sınırlarını kalite kurallarıyla düzeltir" +
      (an && an.ranModel ? ", kararsız kalınan bölümlerde modele danışır ve her öneriyi doğrulatır." : "; bu koşuda model çalışmadı.");
  }
  return "Standard: her bölüm kendi başlığı altında kalır; yalnız bütçeyi aşan bölümler bölünür.";
}

function renderPresDetail(){
  const box = $("chunkdetail");
  const arm = selArm();
  const armData = SA();
  const armNote = armNoteFor(arm);
  if (state.selChunk === null || !armData.chunks[state.selChunk]) {
    box.innerHTML = `<h3>Parça detayı</h3><div class="empty">Bir kolondaki parça başlığına ya da metnine tıklayın: o sınırın neden orada olduğunu burada anlatırız.</div><div class="arminfo">${esc(armNote)}</div>`;
    return;
  }
  const chunk = armData.chunks[state.selChunk];
  const reason = REASONS[chunk.rs] || {label: chunk.rs, sent: ""};
  const prev = chunk.cp, next = chunk.cn;
  const link = idx => `<button data-jump="${idx}">Parça ${armData.chunks[idx].num}</button>`;
  const inType = chunk.rt;
  const outType = (next !== null && next !== undefined) ? armData.chunks[next].rt : null;

  let deepBlock = "";
  const d = chunk.dec;
  if (arm === "agentic" && isDeepArm("agentic")) {
    const st = sectionStory(chunk.si);
    let sent = "";
    if (d) {
      if (d.status === "kept") sent = d.llm_reverted ? `Bu sınır Standard'ın sınırıyla aynı. Model burada farklı bir sınır önerdi, ancak öneri iki ayrı sırada denenince <b>tutmadı</b> (${esc(d.llm_reverted === "order_dependent" ? "cevap sunum sırasına göre değişti" : d.llm_reverted === "base_preferred" ? "model kural sınırını tercih etti" : d.llm_reverted)}); kural sınırı korundu.` : "Bu sınır Standard'ın sınırıyla aynı: ne kalite kuralı ne model değişiklik gerektiren bir şey buldu.";
      else if (d.status === "det_moved") sent = `Kalite kuralı bu sınırı taşıdı${(d.cut_smells || d.removed_smells || []).length ? ": Standard'ın kesimi <b>" + esc((d.cut_smells || d.removed_smells).map(s => SMELL_TEXT[s] || s).join(", ")) + "</b> üretiyordu; yeni kesim bu kusuru taşımıyor" : " (çok kısa parçalar birleşti)"}. Modelsiz, tekrarlanabilir karar.` + (d.llm_reverted ? " Model bu bölgede başka bir sınır önerdi, doğrulamadan geçmedi." : "");
      else if (d.status === "llm_accepted") sent = (analysisState() || {}).ranModel
        ? "Bu sınırı model önerdi. Öneri iki ayrı sunum sırasında da tercih edildiği için kabul edildi, ardından kalite kurallarından yeniden geçti — boyut, kapsama ve yapısal problem sayaçlarının tamamı yeniden kontrol edildi."
        : "Bu sınırı kural katmanı yerleştirdi; bu koşuda model çalışmadı.";
      else if (d.status === "ceiling") sent = "Zorunlu kesim: bu parça tek bir tablonun ya da paragrafın ortasından başlıyor, çünkü o blok tek başına bütçeden büyük. Hiçbir bölümleme yöntemi bu kesimden kaçınamaz.";
    }
    deepBlock = `<div class="reason-sent deep"><b>Deep Analysis kararı.</b> ${sent || "Bu parça bölüm başlangıcında; kesim kararı bölüm sınırının kendisi."}</div>` +
      (st ? `<details class="adv"><summary>Teknik detay — bölüm ${st.i}: ${esc(SECTION_STATUS[st.st] || st.st)}</summary><pre>${esc(JSON.stringify({
        section: st.h, status: st.st, llm_consulted: st.cons, reverted: st.rv, verdict_tiered: st.vt,
        standard_cuts_after: st.std, deterministic_cuts_after: st.det, final_cuts_after: st.fin,
        smells_standard: st.sm.standard, smells_deep: st.sm.deep,
        change_groups: st.gr, llm_proposals: st.pr, this_boundary: d || null
      }, null, 1))}</pre></details>`: "");
  } else if (arm === "structure-only" && d && d.status === "std_changed") {
    deepBlock = `<div class="reason-sent deep"><b>Deep Analysis bu kesimi değiştirdi.</b> ${(d.cut_smells || d.removed_smells || []).length ? "Standard'ın bu kesimi <b>" + esc((d.cut_smells || d.removed_smells).map(s => SMELL_TEXT[s] || s).join(", ")) + "</b> üretiyordu." : "Boyut dengesi için taşındı/birleştirildi."} Karar ${d.origin === "llm" && (analysisState() || {}).ranModel ? "model önerisi ve iki sıralı doğrulamayla" : "deterministik kalite kuralıyla"} verildi. Deep Analysis'i seçip aynı sayfayı açarak yeni sınırı görebilirsiniz.</div>`;
  }

  box.innerHTML = `<h3>Parça ${chunk.num} <span class="muted" style="font-weight:400;font-size:12.5px">· ${esc(modeName(arm).top)}</span></h3>
    <dl class="kv">
      <dt>Sınır nedeni</dt><dd>${esc(reason.label)}</dd>
      <dt>Başlık</dt><dd>${chunk.hh ? chunk.hh : "<span class='empty'>—</span>"}</dd>
      <dt>Bölüm</dt><dd>${chunk.sd.length ? esc(chunk.sd.join(" › ")) : "<span class='empty'>—</span>"}</dd>
      <dt>Sayfa · token</dt><dd>${chunk.pg.join(", ")} · ${chunk.n}</dd>
      <dt>Önceki</dt><dd class="detail-links">${prev !== null && prev !== undefined ? link(prev) + " (devamı bu parça)" : "<span class='empty'>—</span>"}</dd>
      <dt>Sonraki</dt><dd class="detail-links">${next !== null && next !== undefined ? link(next) + " (bu parçanın devamı)" : "<span class='empty'>—</span>"}</dd>
    </dl>
    <div class="reason-sent"><b>${esc(reason.label)}.</b> ${esc(reason.sent || "")}</div>
    ${deepBlock}
    <div class="detail-links" style="margin-top:10px"><button data-showchunk="1">Parça metnini aç</button></div>
    <details class="adv"><summary>Teknik alanlar</summary><dl class="kv" style="margin-top:8px">
      <dt>Sınır tipi</dt><dd class="mono">${inType ? esc(inType) : (outType ? esc(outType) + " →" : "—")}</dd>
      ${chunk.llm ? `<dt>Model oyu</dt><dd>${chunk.llm.m ? "sınır taşındı" + (chunk.llm.rc ? " (" + esc(chunk.llm.rc) + ")" : "") : "değerlendirildi; kesim korundu"}</dd>` : ""}
      <dt>Parça kimliği</dt><dd class="mono" style="word-break:break-all">${esc(chunk.id)}</dd>
    </dl></details>
    <div class="arminfo">${esc(armNote)}</div>`;
  box.querySelectorAll("button[data-jump]").forEach(b => { b.onclick = () => jumpToChunk(Number(b.dataset.jump), arm); });
  const show = box.querySelector("button[data-showchunk]");
  if (show) show.onclick = () => openChunkModal(arm, state.selChunk);
}

function chunkPieces(chunkIdx, arm){
  const armData = D().arms[arm];
  const chunk = armData.chunks[chunkIdx];
  const pieces = [];
  const seen = new Set();
  for (const raw of chunk.u) {
    const baseId = raw.split("#")[0];
    if (seen.has(baseId)) continue;
    seen.add(baseId);
    const u = unitById(baseId);
    if (!u) continue;
    const segs = (armData.seg[baseId] || []).filter(s => s[0] === chunkIdx);
    if (!segs.length) { pieces.push({u, text:u.x}); continue; }
    for (const s of segs) pieces.push({u, text:u.x.slice(s[1], s[2])});
  }
  return pieces;
}
function renderedChunk(chunkIdx, arm, evidence){
  const chunk = D().arms[arm].chunks[chunkIdx];
  const evSet = new Set(evidence || []);
  let out = `<div class="rchunk"><div class="rhead">Parça ${chunk.num} · ${chunk.n} token · sayfa ${chunk.pg.join(", ")}</div>`;
  if (chunk.hh) out += `<div class="piece"><b>${chunk.hh}</b></div>`;
  for (const piece of chunkPieces(chunkIdx, arm)) {
    const body = piece.text === piece.u.x ? unitHtml(piece.u) : "<p>" + esc(piece.text) + "</p>";
    out += `<div class="piece">` + (evSet.has(piece.u.i) ? "<mark>" + body + "</mark>" : body) + `</div>`;
  }
  return out + "</div>";
}

/* -------- modal -------- */
function openModal(title, facts, bodyHtml, actions){
  $("modal").innerHTML = `<div class="box"><div class="mhead"><h3>${title}</h3><button class="btn small" id="mclose">Kapat</button></div>
    <div class="mfacts">${facts}</div><div class="mbody">${bodyHtml}</div>${actions ? `<div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">${actions}</div>` : ""}</div>`;
  $("modal").classList.remove("hidden");
  $("mclose").onclick = closeModal;
}
function closeModal(){ $("modal").classList.add("hidden"); $("modal").innerHTML = ""; }
function openChunkModal(arm, idx){
  const chunk = D().arms[arm].chunks[idx];
  openModal(`Parça ${chunk.num} · ${esc(modeName(arm).top)}`,
    `<span>${chunk.n} token</span><span>sayfa ${chunk.pg.join(", ")}</span><span>${esc(chunk.sd.join(" › "))}</span><span class="mono">${esc(chunk.id)}</span>`,
    renderedChunk(idx, arm, []),
    `<button class="btn small" id="mjump">Sunum'da göster</button>`);
  $("mjump").onclick = () => { closeModal(); jumpToChunk(idx, arm); };
}

/* -------- Sorgu: chat -------- */
async function checkOnline(){
  if (state.chat.online !== null) return state.chat.online;
  if (location.protocol === "file:") { state.chat.online = false; return false; }
  try {
    const r = await fetch("/api/health", {cache:"no-store"});
    if (!r.ok) throw new Error("health " + r.status);
    state.chat.health = await r.json();
    state.chat.online = true;
  } catch (e) { state.chat.online = false; }
  return state.chat.online;
}

function renderChatArms(){
  const arms = docArms();
  if (!state.chat.arm || !hasArm(state.chat.arm)) state.chat.arm = hasArm("agentic") ? "agentic" : arms[0];
  $("chatarms").innerHTML = arms.map(a => `<button data-arm="${a}" class="${state.chat.arm === a ? "on" : ""} ${isDeepArm(a) ? "deep" : ""}">${esc(modeName(a).top)}</button>`).join("");
  $("chatarms").querySelectorAll("button").forEach(b => { b.onclick = () => { state.chat.arm = b.dataset.arm; renderChatArms(); }; });
}

function renderChatSide(){
  const h = state.chat.health;
  const dm = deepMeta();
  $("chatside").innerHTML = `<h3>Kurulum${info("Soru, seçtiğiniz yöntemin parçaları arasında aranır; en iyi eşleşenler ve aynı bölümün devam parçaları cevap modeline verilir. Parçalama yüklemede bitmiştir — soru sorarken yeniden bölümleme yapılmaz.")}</h3>
    <dl class="kv" style="margin-top:10px">
      <dt>Embedding</dt><dd>${h ? esc(h.embedding_model || "yok (BM25)") : "—"}</dd>
      <dt>Cevap modeli</dt><dd>${h ? esc(h.answer_model || "yok") : "—"}</dd>
      <dt>Retrieval</dt><dd>${h ? (h.dense ? "dense + BM25, RRF" : "BM25") + ` · top-k ${h.retrieval && h.retrieval.top_k}` : "—"}</dd>
      <dt>Bağlam</dt><dd>${h && h.context ? `${h.context.max_context_tokens} token bütçe · devam genişletme ${h.context.expansion_enabled ? "açık" : "kapalı"}` : "—"}</dd>
      <dt>Yöntem</dt><dd>${esc(modeName(state.chat.arm).top)}${state.chat.arm === "agentic" && dm ? ` · ${dm.chunkCount.deep} parça` : ""}</dd>
    </dl>
    <div class="muted" style="font-size:12px;margin-top:10px">Yöntemler aynı arama hattını kullanır; değişen tek şey dokümanın nasıl parçalandığıdır. Kaynak yetersizse model tahmin yürütmez.</div>`;
}

function renderSuggest(){
  const gold = D().gold || [];
  const picks = gold.slice(0, 6);
  $("suggest").innerHTML = picks.length ? `<span class="muted" style="font-size:12px;align-self:center">Örnek sorular:</span>` + picks.map(g => `<button data-q="${esc(g.q)}">${esc(g.q.length > 90 ? g.q.slice(0, 88) + "…" : g.q)}</button>`).join("") : "";
  $("suggest").querySelectorAll("button").forEach(b => { b.onclick = () => { $("chatq").value = b.dataset.q; $("chatq").focus(); }; });
}

async function renderChat(){
  renderChatArms();
  renderSuggest();
  const online = await checkOnline();
  // A live document is indexed in the RAG console, not in this page's demo
  // engine: asking here would query the wrong corpus, so the chat says where
  // the answer actually lives instead of pretending to have one.
  if (isLive()) {
    const consoleUrl = (workspace.data && workspace.data.url) || "";
    $("offline").classList.remove("hidden");
    $("offline").innerHTML = `<b>Bu dokümanı RAG Console'daki sohbetten sorabilirsiniz.</b>
      Buradaki sohbet dondurulmuş karşılaştırma setini sorgular; canlı dokümanlar Console'un kendi bilgi tabanında indekslidir.
      ${consoleUrl ? `<a href="${esc(consoleUrl)}/chat" target="_blank" rel="noopener">Console'da sor ↗</a>` : ""}
      <span class="muted">Sunum, Debug ve Benchmark bu doküman için burada çalışır.</span>`;
    $("chatsend").disabled = true;
    $("chatq").disabled = true;
    renderChatSide();
    renderTurns();
    return;
  }
  $("offline").classList.toggle("hidden", online);
  if (!online) {
    $("offline").innerHTML = `<b>Sohbet için sunucu gerekiyor.</b> Bu dosya tek başına açıldığında Sunum, Debug, Benchmark ve ölçüm soruları çalışır.<br>
      <code>py -3.11 -m amsc.viewer_server --viewer artifacts/viewer-v2/index.html --config configs/rag-poc.yaml</code> → <code>http://127.0.0.1:8765/</code>
      <span class="muted">Anahtarlar yalnız sunucuda kalır.</span>`;
  }
  $("chatsend").disabled = !online || state.chat.busy;
  $("chatq").disabled = !online;
  renderChatSide();
  renderTurns();
  $("chatsend").onclick = sendChat;
  $("chatq").onkeydown = e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) sendChat(); };
}

async function sendChat(){
  const q = $("chatq").value.trim();
  if (!q || state.chat.busy) return;
  state.chat.busy = true;
  $("chatsend").disabled = true;
  const compare = $("chatcmp").checked;
  const topK = Number($("chatk").value);
  $("chatstatus").textContent = compare ? "Dört yöntemle retrieval + cevap üretiliyor…" : "Retrieval + cevap üretiliyor…";
  const turn = {q, arm: state.chat.arm, compare, pending: true};
  state.chat.turns.unshift(turn);
  renderTurns();
  try {
    const body = compare ? {doc: state.doc, question: q, top_k: topK} : {doc: state.doc, arm: state.chat.arm, question: q, top_k: topK};
    const r = await fetch(compare ? "/api/compare" : "/api/chat", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)});
    const payload = await r.json();
    if (!r.ok) throw new Error(payload.error || ("HTTP " + r.status));
    turn.result = payload;
  } catch (e) {
    turn.error = String(e.message || e);
  }
  turn.pending = false;
  state.chat.busy = false;
  $("chatstatus").textContent = "";
  $("chatsend").disabled = false;
  renderTurns();
}

// A chunk heading as a reader should see it: no markdown markers.
const plainHeading = h => String(h || "").replace(/\*\*/g, "").replace(/#{1,6}\s*/g, " ").replace(/\s+/g, " ").trim();
function citeHtml(text){
  return esc(text).replace(/\[(S\d+)\]/g, (m, s) => `<button class="cite" data-cite="${s}">${s}</button>`).replace(/\n/g, "<br>");
}
function statusPill(res){
  if (!res) return "";
  if (res.status === "ok") return `<span class="pill ok">✓ kaynaklar yeterli</span>`;
  if (res.status === "insufficient") return `<span class="pill mid">! kaynaklar yetersiz — model tahmin yürütmedi</span>`;
  if (res.status === "answer_error") return `<span class="pill miss">× cevap modeline ulaşılamadı</span>`;
  if (res.status === "no_answer_model") return `<span class="pill grey">cevap modeli yok — yalnız kaynaklar</span>`;
  return `<span class="pill grey">${esc(res.status)}</span>`;
}
function sourceCard(s, key){
  const role = s.role === "hit" ? `eşleşme #${s.rank}` : (s.role === "neighbour_before" ? "önceki devam parçası" : "sonraki devam parçası");
  return `<div class="src ${s.used ? "used" : ""}" data-src="${key}" id="src-${key}">
    ${s.used ? `<span class="usedmark">✓ kullanıldı</span>` : ""}
    <span class="lab">${esc(s.label)}</span><span class="muted" style="font-size:12px">${esc(role)}</span>
    <div class="hd">${esc(plainHeading(s.heading) || "(başlıksız)")}</div>
    <div class="path" title="${esc((s.section_path || []).map(plainHeading).join(" › "))}">${esc((s.section_path || []).map(plainHeading).join(" › ") || "—")}</div>
    <div class="facts"><span>sayfa ${(s.pages || []).join(", ") || "—"}</span><span>${s.token_count} token</span><span>${esc(armLabel(s.arm))}</span></div>
  </div>`;
}
function renderAnswerBlock(res, key){
  const a = res.answer;
  const sources = res.sources || [];
  let out = `<div class="answer">`;
  if (a) out += `<div class="txt">${citeHtml(a.text)}</div>`;
  else if (res.error) out += `<div class="txt muted">${esc(res.error)}</div>`;
  out += `<div class="meta">${statusPill(res)}<span>${esc(modeName(res.arm).top)}</span>${res.timing_seconds ? `<span>retrieval ${fmt(res.timing_seconds.retrieval, 1)} s${res.timing_seconds.answer ? " · cevap " + fmt(res.timing_seconds.answer, 1) + " s" : ""}</span>` : ""}${res.retrieval && res.retrieval.note ? `<span class="pill mid">${esc(res.retrieval.note)}</span>` : ""}</div>`;
  out += `<div class="sources">${sources.map((s, i) => sourceCard(s, key + "-" + i)).join("")}</div>`;
  out += `<details class="adv"><summary>Gelişmiş: retrieval sıralaması, bağlam bütçesi, model kullanımı</summary><pre>${esc(JSON.stringify({
    hits: res.hits, context: res.context, retrieval: res.retrieval, models: res.models, usage: res.usage, sources_used: a && a.sources_used, prompt_version: res.prompt_version
  }, null, 1))}</pre></details></div>`;
  return out;
}
function renderTurns(){
  const box = $("turns");
  box.innerHTML = state.chat.turns.map((t, ti) => {
    let body;
    if (t.pending) body = `<div class="answer"><div class="txt muted">Bekleniyor…</div></div>`;
    else if (t.error) body = `<div class="answer"><div class="txt muted">Hata: ${esc(t.error)}</div></div>`;
    else if (t.compare) {
      const arms = t.result.arms || {};
      const ov = t.result.unit_overlap_with_other_arms || {};
      body = `<div class="cmpcols">` + PRODUCT_ARMS.filter(a => arms[a]).map(a => {
        const res = arms[a];
        return `<div class="cmpcol"><div class="armname">${esc(modeName(a).top)} ${statusPill(res)}</div>
          <div class="txt">${res.answer ? citeHtml(res.answer.text) : esc(res.error || "")}</div>
          <div class="srcs">${(res.sources || []).map((s, i) => `<div data-open="${a}|${i}|${ti}"><span class="lab" style="color:var(--accent);font-weight:700">${esc(s.label)}</span><span>${esc(plainHeading(s.heading).slice(0, 48) || "(başlıksız)")}</span><span class="muted">s.${(s.pages || []).join(",")} · ${s.token_count} tok${s.used ? " · ✓" : ""}</span></div>`).join("")}</div>
          <div class="muted" style="font-size:12px;margin-top:6px">diğer yöntemlerle unit örtüşmesi: ${pct(ov[a])}${res.timing_seconds ? " · " + fmt(res.timing_seconds.total, 1) + " s" : ""}</div></div>`;
      }).join("") + `</div>`;
    } else body = renderAnswerBlock(t.result, "t" + ti);
    return `<div class="turn"><div class="q"><span class="who">Soru</span>${esc(t.q)}<span class="muted" style="font-size:12px;font-weight:400">${t.compare ? "dört yöntem karşılaştırması" : esc(modeName(t.arm).top)}</span></div>${body}</div>`;
  }).join("");
  box.querySelectorAll(".src").forEach(el => {
    el.onclick = () => {
      const [tkey, idx] = [el.dataset.src.replace(/-\d+$/, ""), Number(el.dataset.src.split("-").pop())];
      const turn = state.chat.turns[Number(tkey.slice(1))];
      const s = turn && turn.result && turn.result.sources && turn.result.sources[idx];
      if (s) openSourceModal(s);
    };
  });
  box.querySelectorAll(".cite").forEach(el => {
    el.onclick = () => {
      const card = el.closest(".answer").querySelector(`.src .lab`) ? Array.from(el.closest(".answer").querySelectorAll(".src")).find(c => c.querySelector(".lab").textContent === el.dataset.cite) : null;
      if (card) { card.scrollIntoView({block:"center"}); card.classList.add("hl"); setTimeout(() => card.classList.remove("hl"), 1600); }
    };
  });
  box.querySelectorAll("[data-open]").forEach(el => {
    el.onclick = () => {
      const [arm, i, ti] = el.dataset.open.split("|");
      const s = state.chat.turns[Number(ti)].result.arms[arm].sources[Number(i)];
      if (s) openSourceModal(s);
    };
  });
}
function openSourceModal(s){
  const armData = D().arms[s.arm];
  const idx = armData ? armData._idx[s.chunk_id] : undefined;
  openModal(`${esc(s.label)} · ${esc(plainHeading(s.heading) || "kaynak parça")}`,
    `<span>${esc(modeName(s.arm).top)}</span><span>sayfa ${(s.pages || []).join(", ") || "—"}</span><span>${s.token_count} token</span><span>${esc(s.role === "hit" ? "eşleşme #" + s.rank : "aynı bölümün devam parçası")}</span><span class="mono">${esc(s.chunk_id)}</span>`,
    mdLite(s.text),
    idx !== undefined ? `<button class="btn small" id="mjump">Sunum'da göster</button>` : "");
  if (idx !== undefined) $("mjump").onclick = () => { closeModal(); jumpToChunk(idx, s.arm); };
}

/* -------- Sorgu: gold -------- */
function statusOf(frr){
  if (frr === 1) return {cls:"ok", glyph:"✓", text:"Rank 1"};
  if (frr !== null && frr !== undefined && frr <= 5) return {cls:"mid", glyph:"!", text:"Rank " + frr + " — top-5 içinde"};
  return {cls:"miss", glyph:"×", text:"Top-5 dışında"};
}
function renderQuery(){
  $("qsubtabs").querySelectorAll("button").forEach(b => {
    b.classList.toggle("on", b.dataset.sub === state.qsub);
    if (b.dataset.sub === "gold") b.classList.toggle("hidden", !(D().gold || []).length);
  });
  if (!(D().gold || []).length) state.qsub = "chat";
  $("chatview").classList.toggle("hidden", state.qsub !== "chat");
  $("goldview").classList.toggle("hidden", state.qsub !== "gold");
  if (state.qsub === "chat") { renderChat(); return; }
  const gold = D().gold;
  const sel = $("querysel");
  // The agentic column appears only when its tree carries query results; the frozen three columns never move.
  const qArms = ARMS.filter(hasArm).concat(hasArm("agentic") && Object.keys(D().arms.agentic.q).length ? ["agentic"] : []);
  if (state.query === null || !gold.some(g => g.id === state.query)) state.query = gold[0] && gold[0].id;
  sel.innerHTML = gold.map(g => {
    const worst = Math.max(...qArms.map(a => { const f = (D().arms[a].q[g.id] || {}).f; return f === null || f === undefined ? 9 : f; }));
    const mark = worst === 1 ? "✓" : worst <= 5 ? "!" : "×";
    return `<option value="${g.id}">${mark} ${g.id} — ${esc(g.q)}</option>`;
  }).join("");
  sel.value = state.query;
  sel.onchange = () => { state.query = sel.value; render(); };
  const g = gold.find(x => x.id === state.query);
  if (!g) { $("queryhead").innerHTML = ""; $("querycols").innerHTML = ""; return; }
  const evHtml = g.ev.map(id => { const u = unitById(id); return u ? `<div>${unitHtml(u)}</div>` : ""; }).join("");
  $("queryhead").innerHTML = `<div class="qhead"><div class="qq">${esc(g.q)}</div>
    ${g.a ? `<div class="qa">Beklenen cevap: ${esc(g.a)}</div>` : ""}
    <div class="qmeta">${g.id} · kanıt türü: ${esc(g.ty || "—")} · zorluk: ${esc(g.df || "—")} · kanıt sayfaları: ${g.pg.join(", ")}${info("Kanıt, cevabın dayandığı ve elle işaretlenmiş metin parçasıdır. Aşağıdaki her sütun, o yöntemin bu kanıtı kaçıncı sırada getirdiğini gösterir.")}</div>
    <div class="evbox"><div class="evlabel">Kanıt metni (${g.ev.length} birim)</div>${evHtml}</div></div>`;
  $("querycols").innerHTML = qArms.map(arm => {
    const qres = D().arms[arm].q[g.id];
    if (!qres) return `<div class="qcol"><div class="armname">${esc(armLabel(arm))}</div><div class="covline">sonuç yok</div></div>`;
    const st = statusOf(qres.f);
    const relevant = qres.res.find(r => r.r === qres.f && r.m.length);
    const body = (relevant && relevant.c !== null) ? renderedChunk(relevant.c, arm, g.ev) : `<div class="rchunk"><div class="rhead">İlk 5 sonucun hiçbiri kanıtı taşımıyor.</div></div>`;
    const rows = qres.res.map(r => {
      const chunk = r.c === null ? null : D().arms[arm].chunks[r.c];
      return `<div class="row"><span class="rk">#${r.r}</span><span>${chunk ? "Parça " + chunk.num : "—"}</span><span>s.${r.pg.join(",")}</span><span>${r.tk} tok</span>${r.m.length ? `<span class="mt">✓ ${r.m.length} kanıt unit</span>` : ""}</div>`;
    }).join("");
    return `<div class="qcol"><div class="armname">${esc(armLabel(arm))} <span class="pill ${st.cls}">${st.glyph} ${st.text}</span></div>
      <div class="covline">kanıt kapsaması: ${qres.cov === null || qres.cov === undefined ? "—" : (qres.cov * 100).toFixed(0) + "%"}${info(TERMS.coverage.help)}</div>${body}
      <details class="top5"><summary>İlk 5 sonucun tamamı</summary>${rows}</details>
      <div class="qlink"><button data-goto="${arm}">Bu yöntemin sınırlarını sayfada gör →</button></div></div>`;
  }).join("");
  $("querycols").querySelectorAll("button[data-goto]").forEach(b => {
    b.onclick = () => {
      state.mode = "presentation";
      const arm = b.dataset.goto;
      if (!laneList().includes(arm)) setLanes(laneList().concat([arm]));
      state.arm = arm; state.selArm = arm;
      const evidence = g.ev.length ? unitById(g.ev[0]) : null;
      state.page = (evidence && evidence.p) || g.pg[0] || D().pages[0];
      state.diffIdx = -1; state.selChunk = null; state.unfolded = new Set();
      render();
      const bd = $("board");
      g.ev.forEach(id => {
        bd.querySelectorAll(`.cell.ur[data-uid="${id}"][data-arm="${arm}"]`).forEach(el => el.classList.add("evflash"));
      });
      const first = bd.querySelector(".cell.evflash");
      if (first) bd.scrollTop = Math.max(0, first.offsetTop - Math.round(bd.clientHeight * 0.3));
      $("stage").scrollIntoView({block: "start"});
    };
  });
}

/* -------- Debug -------- */
function renderDebugBar(){
  const f = state.dbg;
  const roles = ["all","section","group","item","display"];
  $("dbgbar").innerHTML = `<span class="lab">Filtre</span>
    <select id="dbgtype"><option value="all">tüm tipler</option>${["heading","paragraph","list","table"].map(t => `<option value="${t}" ${f.type === t ? "selected" : ""}>${t}</option>`).join("")}</select>
    <select id="dbgrole">${roles.map(r => `<option value="${r}" ${f.role === r ? "selected" : ""}>${r === "all" ? "tüm roller" : "rol: " + r}</option>`).join("")}</select>
    <input type="text" id="dbgtext" placeholder="metin / unit id ara (bu sayfa)" value="${esc(f.text)}">
    <label><input type="checkbox" id="dbgbig" ${f.onlyBig ? "checked" : ""}> tek başına bütçeden büyük birimler${info("Bu birimin kendisi hard cap'ten büyük: hangi yöntem kullanılırsa kullanılsın ortasından kesilmek zorunda. Kalan yapısal problemlerin bir kısmı buradan gelir.")}</label>
    <label><input type="checkbox" id="dbgpf" ${f.onlyPf ? "checked" : ""}> ayrıştırıcı notu olan birimler${info("PDF'ten metin çıkarılırken kaydedilen gözlem: birleşmiş satır, kopmuş tablo başlığı gibi. Bölümleme yönteminin değil, kaynağın özelliğidir.")}</label>
    <span class="muted">dokümanda ${D().parser.count} ayrıştırıcı notu</span>`;
  $("dbgtype").onchange = e => { f.type = e.target.value; renderDebug(); };
  $("dbgrole").onchange = e => { f.role = e.target.value; renderDebug(); };
  $("dbgtext").oninput = e => { f.text = e.target.value; renderDebugList(); };
  $("dbgbig").onchange = e => { f.onlyBig = e.target.checked; renderDebug(); };
  $("dbgpf").onchange = e => { f.onlyPf = e.target.checked; renderDebug(); };
}
function debugUnits(){
  const f = state.dbg;
  const needle = f.text.trim().toLowerCase();
  return pageUnits(state.page).filter(u =>
    (f.type === "all" || u.t === f.type) &&
    (f.role === "all" || u.r === f.role) &&
    (!f.onlyBig || u.big) && (!f.onlyPf || (u.pf && u.pf.length)) &&
    (!needle || u.i.toLowerCase().includes(needle) || u.x.toLowerCase().includes(needle)));
}
function renderDebugList(){
  const units = debugUnits();
  const arms = docArms();
  $("dbglist").innerHTML = units.length ? units.map(u => {
    const chips = [
      `<span class="chip">${u.i}</span>`, `<span class="chip">${u.t}</span>`,
      u.r ? `<span class="chip role">${u.r}</span>` : "",
      u.o === true ? `<span class="chip opens">opens_section</span>` : u.o === false ? `<span class="chip noopen">opens=false</span>` : "",
      u.l !== null && u.l !== undefined ? `<span class="chip">level ${u.l}</span>` : "",
      u.b !== null && u.b !== undefined ? `<span class="chip">block ${u.b}</span>` : "",
      `<span class="chip">p.${u.p}</span>`,
      u.big ? `<span class="chip big">${u.big} token — tek başına bütçeden büyük</span>` : "",
      ...(u.pf || []).map(r => `<span class="chip pf">parser: ${esc(r)}</span>`)
    ].join("");
    const rows = arms.map(arm => {
      const armData = D().arms[arm];
      const segs = armData.seg[u.i] || [];
      if (!segs.length) return `<tr><td>${esc(armLabel(arm))}</td><td colspan="3">bu yöntemde hiçbir parçaya girmedi</td></tr>`;
      return segs.map(s => {
        const chunk = armData.chunks[s[0]];
        const frag = chunk.u.find(x => x.split("#")[0] === u.i && x.includes("#"));
        return `<tr><td>${esc(armLabel(arm))}</td><td>${chunk.id}${frag ? " · " + frag.split("#")[1] : ""}</td><td>${s[1]}–${s[2]}</td><td>${s[3]}</td></tr>`;
      }).join("");
    }).join("");
    return `<div class="dbgunit${state.selUnit === u.i ? " sel" : ""}" data-uid="${u.i}">
      <div class="head">${chips}</div><div class="path">${esc((u.sd || []).join(" › ") || "bölüm yolu yok")}</div><div class="txt">${esc(u.x)}</div>
      <table class="dbgtable"><tr><th>yöntem</th><th>parça · fragman</th><th>karakter aralığı</th><th>eşleme</th></tr>${rows}</table></div>`;
  }).join("") : `<div class="card muted">Bu sayfada filtreye uyan birim yok.</div>`;
  $("dbglist").querySelectorAll(".dbgunit").forEach(el => {
    el.onclick = () => { state.selUnit = el.dataset.uid; renderInspector();
      $("dbglist").querySelectorAll(".dbgunit").forEach(x => x.classList.toggle("sel", x.dataset.uid === state.selUnit)); };
  });
}
function renderDebug(){
  renderDebugBar();
  renderDebugList();
  renderInspector();
  renderSectionPanel();
}
function groupHtml(g, si){
  const fixed = (g.rm || []).map(s => SMELL_FIXED[s] || s).join(", ");
  const intro = (g.in || []).map(s => SMELL_TEXT[s] || s).join(", ");
  const se = g.se ? ` · min altı ${g.se.below_min.standard}→${g.se.below_min.final}, soft-max üstü ${g.se.above_soft_max.standard}→${g.se.above_soft_max.final}` : "";
  return `<div class="grp"><b>${g.or === "llm" ? "Model önerisi" : "Kalite kuralı"}</b> — Standard kesimleri: <span class="mono">${esc((g.sc || []).join(", ") || "—")}</span> → final: <span class="mono">${esc((g.fc || []).join(", ") || "— (birleştirildi)")}</span>
    <div>${fixed ? "giderilen problem: " + esc(fixed) : "yapısal problem değişmedi"}${intro ? " · eklenen: " + esc(intro) : ""}${esc(se)}</div>
    <div class="ids">grup: ${esc((g.u || []).join(" "))}</div></div>`;
}
function renderInspector(){
  const box = $("inspector");
  const u = state.selUnit && unitById(state.selUnit);
  if (!u) { box.innerHTML = "<b>Birim incelemesi</b><div class='muted' style='margin-top:8px'>Soldan bir birime tıklayın: alanları, ayrıştırıcı notları ve varsa bölümünün Deep Analysis karar izi burada açılır.</div>"; return; }
  const row = (key, value) => `<div class="row"><dt>${esc(key)}</dt><dd>${value}</dd></div>`;
  let out = `<b>Birim incelemesi</b><div class="trail" style="border:none;margin-top:6px;padding-top:0">
    ${row("Kimlik", `<span class="mono">${esc(u.i)}</span>`)}
    ${row("Tür", esc(u.t) + (u.r ? ` · ${esc(u.r)}` : "") + (u.l !== null && u.l !== undefined ? ` · seviye ${u.l}` : ""))}
    ${row("Sayfa", u.p + (u.b !== null && u.b !== undefined ? ` · blok ${u.b}` : ""))}
    ${row("Bölüm", esc((u.sd || []).join(" › ") || "—"))}
    ${row("Bölüm açar mı", u.o === true ? "evet" : u.o === false ? "hayır" : "belirtilmemiş")}
  </div>`;
  // Which chunk this unit fell into, per method: the one question a unit
  // raises in a comparison tool, answered where the unit is selected.
  out += `<div class="trail"><b>Hangi parçaya düştü?</b>` + docArms().map(arm => {
    const data = D().arms[arm];
    const segs = data.seg[u.i] || [];
    if (!segs.length) return row(modeName(arm).top, "<span class='muted'>bu yöntemde hiçbir parçaya girmedi</span>");
    const parts = segs.map(s => {
      const chunk = data.chunks[s[0]];
      return `<button class="linkbtn" data-goarm="${arm}" data-gochunk="${s[0]}">Parça ${chunk.num}</button> <span class="muted">${chunk.n} tok</span>`;
    }).join(", ");
    return row(modeName(arm).top, parts + (segs.length > 1 ? ` <span class="muted">(${segs.length} parçaya bölündü)</span>` : ""));
  }).join("") + `</div>`;
  if (u.big) out += `<div class="guard" style="margin:8px 0"><b>Kaçınılmaz kesim.</b> Bu birim ${u.big} token — tek başına bütçenin (${expansionBudget()}) üstünde. Hangi yöntem seçilirse seçilsin ortasından kesilmek zorunda; düzeltmek için kaynağın kendisinin değişmesi gerekir.</div>`;
  const pf = D().parser.findings.filter(f => f.t === u.i);
  if (pf.length) out += `<div class="trail"><b>Ayrıştırıcı notları</b>${pf.map(f => `<div class="row"><dt>${esc(f.r)} · ${esc(f.c)}</dt><dd>${esc(f.why)}${f.ev ? " — <i>" + esc(f.ev) + "</i>" : ""}</dd></div>`).join("")}</div>`;
  const story = D().story;
  if (story) {
    const si = story.sectionOf[u.i];
    const st = sectionStory(si);
    if (st) {
      out += `<div class="trail"><b>Deep Analysis karar izi — bölüm ${st.i}</b> <span class="stpill ${st.st}">${esc(SECTION_STATUS[st.st] || st.st)}</span>
        <div class="row"><dt>Başlık</dt><dd>${esc(st.h || "—")}</dd></div>
        <div class="row"><dt>Standard kesim</dt><dd class="mono">${esc(st.std.join(", ") || "—")}</dd></div>
        <div class="row"><dt>Deterministik</dt><dd class="mono">${esc(st.det.join(", ") || "—")}</dd></div>
        <div class="row"><dt>Final</dt><dd class="mono">${esc(st.fin.join(", ") || "—")}</dd></div>
        <div class="row"><dt>Modele danışıldı</dt><dd>${st.cons ? "evet" : "hayır — bölümde kararsız kalınan bir sınır yoktu"}</dd></div>
        <div class="row"><dt>Geri alma</dt><dd>${esc(st.rv || "—")}${st.sz ? " · boyut takası" : ""}</dd></div>
        <div class="row"><dt>Yapısal problem (S→D)</dt><dd>${st.sm && st.sm.standard ? esc(Object.keys(st.sm.standard).filter(k => st.sm.standard[k] || st.sm.deep[k]).map(k => `${k} ${st.sm.standard[k]}→${st.sm.deep[k]}`).join(", ") || "0") : "—"}</dd></div>
        ${st.gr.map(g => groupHtml(g, st.i)).join("")}
        ${st.pr.length ? `<div style="margin-top:8px"><b>Model önerileri ve doğrulama sonucu</b>${st.pr.map(p => `<div class="grp"><span class="stpill ${p.a ? "llm_accepted" : "llm_reverted"}">${p.a ? "kabul" : "ret"}</span> ${esc(p.r)} <div class="ids">${esc(p.u.join(" "))}</div></div>`).join("")}</div>` : ""}
      </div>`;
    }
  }
  out += `<details class="adv"><summary>Ham metin</summary><pre>${esc(u.x)}</pre></details>`;
  box.innerHTML = out;
  box.querySelectorAll("button[data-gochunk]").forEach(el => {
    el.onclick = () => jumpToChunk(Number(el.dataset.gochunk), el.dataset.goarm);
  });
}
function renderSectionPanel(){
  const story = D().story;
  const box = $("secpanel");
  if (!story) { box.innerHTML = ""; return; }
  const all = story.sections;
  const changedCount = all.filter(s => s.st !== "standard_kept").length;
  // A document Deep Analysis left alone would otherwise open on an empty
  // table, which reads as a broken panel rather than as the answer it is.
  const fellBack = state.dbg.secStatus === "changed" && !changedCount && all.length;
  const f = fellBack ? "all" : state.dbg.secStatus;
  const shown = all.filter(s => f === "all" || (f === "changed" ? s.st !== "standard_kept" : s.st === f));
  const counts = story.counts || {};
  box.innerHTML = `<details class="deep-detail" style="margin-top:22px"><summary>Bölüm kararları — Deep Analysis her bölümde ne yaptı? (${all.length} bölüm${changedCount ? `, ${changedCount} tanesinde değişiklik` : ", değişiklik yok"})</summary><div class="inner">
    ${fellBack ? `<div class="help" style="margin-top:10px">Bu dokümanda Deep Analysis hiçbir bölümün sınırlarını değiştirmedi — Standard zaten temiz kesmişti. Aşağıda bölümlerin tamamı listeleniyor.</div>` : ""}
    <div class="dbgbar"><span>Durum:</span><select id="secstatus">
      <option value="changed" ${f === "changed" ? "selected" : ""}>değişen bölümler (${all.filter(s => s.st !== "standard_kept").length})</option>
      <option value="all" ${f === "all" ? "selected" : ""}>tümü (${all.length})</option>
      ${Object.keys(SECTION_STATUS).map(k => `<option value="${k}" ${f === k ? "selected" : ""}>${esc(SECTION_STATUS[k])} (${counts[k] ?? 0})</option>`).join("")}
    </select><span class="muted">· modele danışılan bölüm: ${counts.llm_consulted_sections ?? "—"} · final sınır kökeni: ${(o => `${o.standard ?? 0} Standard / ${o.deterministic ?? 0} kural / ${o.llm ?? 0} model`)(counts.final_boundaries_by_origin || {})} · kaçınılmaz kesim: ${counts.ceiling_boundaries ?? "—"}</span></div>
    <div class="scrollx"><table class="sectable"><tr><th>#</th><th>Bölüm</th><th>Sayfa</th><th>Durum</th><th>Model</th><th>Standard → Final kesimler</th><th>Değişim grupları</th></tr>
    ${shown.map(s => `<tr class="clk" data-si="${s.i}"><td>${s.i}</td><td>${esc(s.h || "—")}</td><td>${s.pg.slice(0, 3).join(", ")}${s.pg.length > 3 ? "…" : ""}</td><td><span class="stpill ${s.st}">${esc(SECTION_STATUS[s.st] || s.st)}</span>${s.rv ? `<div class="muted" style="font-size:11.5px">${esc(s.rv)}</div>` : ""}</td><td>${s.cons ? (s.pr.length ? `${s.pr.filter(p => p.a).length}/${s.pr.length} kabul` : "danışıldı") : "—"}</td><td class="mono" style="font-size:11.5px">${esc(s.std.join(", ") || "—")} → ${esc(s.fin.join(", ") || "—")}</td><td style="font-size:12px">${s.gr.map(g => (g.or === "llm" ? "model" : "kural") + (g.rm.length ? ": " + g.rm.map(x => SMELL_FIXED[x] || x).join(", ") : (g.fc.length ? ": taşındı" : ": birleştirildi"))).join("<br>") || "—"}</td></tr>`).join("")}
    </table></div></div></details>`;
  $("secstatus").onchange = e => { state.dbg.secStatus = e.target.value; renderSectionPanel(); };
  box.querySelectorAll("tr.clk").forEach(tr => {
    tr.onclick = () => {
      const s = all.find(x => x.i === Number(tr.dataset.si));
      if (!s) return;
      const first = s.fin[0] || s.std[0] || (s.gr[0] && s.gr[0].u[0]);
      state.page = s.pg[0] || state.page;
      state.selUnit = first ? first.split("#")[0] : null;
      render();
      const el = document.querySelector(`.dbgunit[data-uid="${state.selUnit}"]`);
      if (el) el.scrollIntoView({block:"center"});
    };
  });
}

/* -------- Benchmark -------- */
function benchTable(title, rows, columns, higherBetter, deepArms){
  const best = {};
  for (const col of columns) {
    const vals = rows.map(r => r.values[col.k]).filter(v => v !== null && v !== undefined);
    if (vals.length) best[col.k] = higherBetter === false ? Math.min(...vals) : Math.max(...vals);
  }
  let out = `<h2>${esc(title)}</h2><div class="scrollx"><table class="t"><tr><th>Yöntem</th>` + columns.map(c => `<th>${esc(c.t)}${info(c.h)}</th>`).join("") + "</tr>";
  for (const row of rows) {
    out += `<tr><td>${row.arm}</td>` + columns.map(c => {
      const v = row.values[c.k];
      const cls = (higherBetter !== undefined && best[c.k] !== undefined && v === best[c.k] && rows.length > 1 ? "best " : "") + (deepArms && deepArms.has(row.arm) ? "deepcol" : "");
      return `<td class="${cls}">${fmt(v, c.d)}</td>`;
    }).join("") + "</tr>";
  }
  return out + "</table></div>";
}
const RET_COLS = [
  {k:"hit_at_1", t:"Hit@1"}, {k:"hit_at_3", t:"Hit@3"}, {k:"hit_at_5", t:"Hit@5"},
  {k:"mrr", t:"MRR"}, {k:"evidence_coverage_at_5", t:"Kanıt kaps.@5"}, {k:"source_evidence_coverage", t:"Kaynak kapsama"}
];
// The same numbers, named the way a reader without the metric vocabulary would
// name them. Used in the top-level summary; RET_COLS stays for the audit view.
const RET_COLS_PLAIN = [
  {k:"hit_at_1", t:"İlk sonuçta doğru", d:3, h:"Gold soruların hangi oranında doğru cevabı içeren parça ilk sırada geldi. Yüksek olan iyi. (Hit@1)"},
  {k:"hit_at_3", t:"İlk 3'te doğru", d:3, h:"Doğru parça ilk üç sonuç arasında geldi mi? (Hit@3)"},
  {k:"hit_at_5", t:"İlk 5'te doğru", d:3, h:"Doğru parça ilk beş sonuç arasında geldi mi? Modele genelde bu kadarı verilir. (Hit@5)"},
  {k:"mrr", t:"Sıralama kalitesi", d:3, h:"Doğru parça listenin ne kadar üstünde çıkıyor. Yüksek olan iyi. (MRR)"},
  {k:"evidence_coverage_at_5", t:"Kanıt kapsama", d:3, h:"Cevabın dayandığı kanıt metninin ne kadarı getirilen parçaların içinde. (evidence coverage@5)"}
];
function sqValues(s){
  return {
    chunk_count: s.chunk_count, tok_med: s.token_count && s.token_count.median, tok_p90: s.token_count && s.token_count.p90_nearest_rank,
    tok_max: s.token_count && s.token_count.max, below_min: s.size_bands && s.size_bands.below_min_count, above_soft: s.size_bands && s.size_bands.above_soft_max_count,
    over_hard: s.size_bands && s.size_bands.over_hard_cap_count, heading_led: s.structure && s.structure.heading_led_ratio, multi_sec: s.structure && s.structure.multi_section_count,
    mid_sent: s.fragmentation && s.fragmentation.mid_sentence_split_count, tab_frag: s.fragmentation && s.fragmentation.table_units_fragmented,
    list_frag: s.fragmentation && s.fragmentation.list_units_fragmented, dup_mass: s.duplication && s.duplication.duplicate_token_mass_ratio,
    coverage: s.coverage && s.coverage.content_unit_coverage
  };
}
const SQ_COLS = [
  {k:"chunk_count", t:"Chunk", d:0}, {k:"tok_med", t:"Token medyan", d:1}, {k:"tok_p90", t:"p90", d:0}, {k:"tok_max", t:"maks", d:0},
  {k:"below_min", t:"<160", d:0}, {k:"above_soft", t:">900", d:0}, {k:"over_hard", t:">hard cap", d:0}, {k:"coverage", t:"Kapsama", d:3},
  {k:"heading_led", t:"Başlıkla açılan", d:4}, {k:"multi_sec", t:"Çok bölümlü", d:0}, {k:"mid_sent", t:"Cümle ortası", d:0},
  {k:"tab_frag", t:"Tablo böl.", d:0}, {k:"list_frag", t:"Liste böl.", d:0}, {k:"dup_mass", t:"Tekrar kütlesi", d:4}
];

function renderFrozenBenchmark(doc){
  const meta = doc.meta, arms = doc.arms;
  const frozen = ARMS.filter(a => arms[a] && arms[a].ret);
  if (frozen.length < 3) return "";
  let out = `<h2 class="sec" style="margin-top:0">Frozen benchmark v5 — üç kol (metodolojik referans, değişmez)</h2>`;
  out += `<div class="guard">${esc(meta.guard || "")}</div>`;
  out += `<div class="cards" style="margin-top:12px"><div class="card stat"><div class="v">${meta.queryCount}</div><div class="k">gold sorgu</div></div>` +
    frozen.map(a => `<div class="card stat"><div class="v">${arms[a].ret.chunk_count}</div><div class="k">${esc(armLabel(a))} parça</div></div>`).join("") +
    `<div class="card stat"><div class="v">${meta.parserFindings ?? "—"}</div><div class="k">parser taban bulgusu (kola ait değil)</div></div></div>`;
  out += benchTable("Retrieval — birincil gold set (BM25)", frozen.map(a => ({arm: armFull(a), values: arms[a].ret})), RET_COLS, true);
  out += `<div class="legend">● = en iyi gözlenen değer (bu koşuda). Tek bir yöntem her metrikte önde değildir; sonuçlar PoC parametreleriyle alınmıştır.</div>`;
  const et = meta.etypes, etKeys = Object.keys(et).sort();
  if (etKeys.length) {
    out += `<h2>Kanıt türüne göre Hit@5</h2><div class="scrollx"><table class="t"><tr><th>Tür</th><th>Sorgu</th>` + frozen.map(a => `<th>${esc(armLabel(a))}</th>`).join("") + "</tr>" +
      etKeys.map(k => `<tr><td>${esc(k)}</td><td>${et[k].query_count}</td>` + frozen.map(a => `<td>${et[k][a] ?? "—"}</td>`).join("") + "</tr>").join("") + "</table></div>";
  }
  const qc = meta.qcomp;
  if (qc && qc.pairwise_hit_at_5) {
    out += `<h2>Sorgu düzeyi karşılaştırma (Hit@5)</h2><div class="pairlists">`;
    for (const [pair, sides] of Object.entries(qc.pairwise_hit_at_5)) {
      const nice = pair.replace(/_vs_/, " ↔ ").replace(/_hit_at_5/, "");
      out += `<div class="pl"><b>${esc(nice)}</b><br>kazanılan: ${sides.gained.length ? sides.gained.map(q => `<span class="qidchip" data-q="${q}">${q}</span>`).join(" ") : "—"}<br>kaybedilen: ${sides.lost.length ? sides.lost.map(q => `<span class="qidchip" data-q="${q}">${q}</span>`).join(" ") : "—"}</div>`;
    }
    out += `<div class="pl"><b>Üç yöntemin de kaçırdığı</b><br>` + ((qc.missed_by_all_at_5 || []).map(q => `<span class="qidchip" data-q="${q}">${q}</span>`).join(" ") || "—") + `</div></div>`;
  }
  out += benchTable("Yapısal kalite (chunk türevli)", frozen.map(a => ({arm: armFull(a), values: sqValues(arms[a].sq)})), SQ_COLS, undefined);
  out += `<div class="legend">Bu tabloda "en iyi" işareti yoktur: metriklerin bir kısmı yöntem tanımının sonucudur (örn. markdown örtüşmesi tekrarlanan kütleyi yapısal olarak yükseltir).</div>`;
  const timing = meta.timing || {};
  out += benchTable("Zamanlama", frozen.map(a => { const t = timing[a] || arms[a].tim || {}; return {arm: armFull(a), values: {chunk: t.chunk_ms_median, index: t.index_build_ms, p50: t.search_p50_ms, p90: t.search_p90_ms, cold: t.cold ? t.cold.chunk_ms_cold : null}}; }),
    [{k:"chunk", t:"Chunking medyan (ms)", d:1}, {k:"index", t:"İndeks (ms)", d:1}, {k:"p50", t:"Arama p50 (ms)", d:2}, {k:"p90", t:"Arama p90 (ms)", d:2}, {k:"cold", t:"Cold embedding (ms)", d:0}], false);
  out += `<div class="legend">Cold sütunu yalnız Hybrid için anlamlıdır (boundary-embedding önbelleği boşken). Markdown ve Structure-only model yüklemez; cold ≡ warm.</div>`;
  const sec = meta.secondary;
  if (sec && sec.metrics) {
    out += `<details class="secgold"><summary>İkincil gold set (${esc((sec.gold_queries || "").split("/").pop() || "v1")})</summary>`;
    out += benchTable("Retrieval — ikincil set", frozen.map(a => ({arm: armFull(a), values: sec.metrics[a] || {}})), RET_COLS) + "</details>";
  }
  return out;
}


// Formats a counter map the way a reader reads it, instead of printing the
// object literal the pipeline happened to store it in.
function counts(obj, names){
  const entries = Object.entries(obj || {}).filter(([, v]) => v);
  if (!entries.length) return "—";
  return entries.map(([k, v]) => `${esc((names && names[k]) || k)} ${v}`).join(" · ");
}
const REVERT_NAMES = {
  order_dependent: "sıraya bağlı cevap", base_preferred: "deterministik sınır tercih edildi",
  contract: "kalite sözleşmesi", coverage: "kapsama kaybı", hard_cap: "boyut sınırı"
};

function renderDeepPanel(doc){
  const dm = doc.meta.deep;
  if (!dm) return "";
  const an = analysisState();
  const arms = doc.arms;
  const std = arms["structure-only"], deep = arms.agentic;
  const sc = dm.storyCounts || {};
  const origin = sc.final_boundaries_by_origin || {};
  let out = `<h2 style="margin-top:14px">Standard ile Deep Analysis — aynı canonical, iki bölümleme</h2>`;
  out += `<div class="help">${esc(an.short)} Bu panel dondurulmuş üç kol karşılaştırmasının dışındadır ve bir kazanan ilan etmez; eşikler PoC seviyesindedir.</div>`;
  out += `<div class="mfacts" style="margin-top:8px">${[
    ["mod", dm.mode], ["model", an.ranModel ? dm.model : null],
    ["doğrulayıcı", an.ranModel && dm.verifierModel && dm.verifierModel !== dm.model ? dm.verifierModel : null],
    ["prompt", dm.promptVersion], ["durum", dm.status]
  ].filter(([, v]) => v).map(([k, v]) => `<span>${esc(k)}: ${esc(v)}</span>`).join("")}</div>`;
  out += `<div class="cards" style="margin-top:12px">
    <div class="card stat"><div class="v">${dm.changeGroups}</div><div class="k">değişim grubu — Deep'in dokunduğu sınır kümesi</div></div>
    <div class="card stat"><div class="v">${dm.strictRegressions}</div><div class="k">${term("sizetrade")}</div></div>
    <div class="card stat"><div class="v">${dm.verifier ? dm.verifier.accepted : 0}<small>/ ${dm.verifier ? dm.verifier.group_count : 0}</small></div><div class="k">doğrulanan / gelen model önerisi</div></div>
  </div>`;
  out += `<div class="legend" style="margin-top:14px"><b>Sözleşme.</b> Deep Analysis'in her bölümde, her problem türünde ürettiği sayı Standard'ınkini geçemez. Parça boyutu sayaçları yalnız toplam problem sayısı kesin azalırken bir miktar büyüyebilir — bilinçli bir takas. Kalan “tablo ortadan bölündü” ve “paragraf ortasından kesildi” değerleri tek bir tablonun ya da paragrafın kendisi bütçeden büyük olduğu için zorunludur; hiçbir yöntem bunlardan kaçınamaz.</div>`;
  const deepSet = new Set([armFull("agentic")]);
  if (std && std.sq && deep && deep.sq) {
    out += benchTable("Yapısal kalite (parser tabanı çıkarılmış)", [
      {arm: armFull("structure-only"), values: sqValues(std.sq)}, {arm: armFull("agentic"), values: sqValues(deep.sq)}
    ], SQ_COLS, undefined, deepSet);
  }
  const r = dm.retrieval || {};
  if (r.deep && r.standard) {
    out += benchTable("Arama — aynı gold set, aynı BM25 (frozen değerler kopya, Deep yeniden skorlandı)", [
      {arm: armFull("structure-only"), values: r.standard}, {arm: armFull("agentic"), values: r.deep}
    ], RET_COLS, undefined, deepSet);
  }
  out += `<h2>Sınır kökeni ve model kullanımı</h2><div class="scrollx"><table class="t"><tr><th>Ölçüm</th><th>Değer</th></tr>
    <tr><td>Bölüm sayısı</td><td>${sc.sections ?? "—"}</td></tr>
    <tr><td>Yapısal sınır korunan bölüm</td><td>${sc.standard_kept ?? "—"}</td></tr>
    <tr><td>Kalite kuralının iyileştirdiği bölüm</td><td>${sc.deterministic_improved ?? "—"}</td></tr>
    <tr><td>Model önerisi kabul edilen bölüm</td><td>${sc.llm_accepted ?? "—"}</td></tr>
    <tr><td>Model önerisi reddedilen bölüm</td><td>${sc.llm_reverted ?? "—"}</td></tr>
    <tr><td>Kalite kontrolünün geri aldığı bölüm</td><td>${sc.contract_reverted ?? "—"}</td></tr>
    <tr><td>Final sınır kökeni — Standard / kural / model</td><td>${origin.standard ?? "—"} / ${origin.deterministic ?? "—"} / ${origin.llm ?? "—"}</td></tr>
    <tr><td>Modele danışılan bölüm</td><td>${sc.llm_consulted_sections ?? "—"}</td></tr>
    <tr><td>Öneri çağrısı</td><td>${dm.calls.proposer}${dm.proposer && dm.proposer.call_status ? " — " + counts(dm.proposer.call_status) : ""}</td></tr>
    <tr><td>İşaretlenen / yasaklanan sınır oyu</td><td>${dm.proposer ? dm.proposer.boundary_count : "—"} / ${dm.proposer ? dm.proposer.forbidden_boundary_count : "—"}</td></tr>
    <tr><td>Doğrulama çağrısı — her grup iki sırada</td><td>${dm.calls.verifier}</td></tr>
    <tr><td>Doğrulama kararları</td><td>${dm.verifier ? counts(dm.verifier.reasons, REVERT_NAMES) : "—"}</td></tr>
    <tr><td>Geri alma nedenleri</td><td>${counts(dm.selection.revert_reasons, REVERT_NAMES)}</td></tr>
    <tr><td>Süre (s) — öneri / doğrulama / seçim${dm.timing.standard ? ` · Standard ${fmt(dm.timing.standard, 2)}` : ""}</td><td>${fmt(dm.timing.llm_calls, 1)} / ${fmt(dm.timing.verifier_calls, 1)} / ${fmt(dm.timing.selection, 1)}</td></tr>
    <tr><td>Token tahmini — istek / cevap</td><td>≈ ${dm.estTokens.prompt.toLocaleString("tr-TR")} / ${dm.estTokens.completion.toLocaleString("tr-TR")} <span class="muted">(karakter ÷ 2,45)</span></td></tr>
    <tr><td>Yaklaşık maliyet</td><td>≈ $${dm.estCostUsd.toFixed(4)} <span class="muted">(${esc(DATA.price.note)}; $${DATA.price.prompt}/M istek, $${DATA.price.completion}/M cevap)</span></td></tr>
  </table></div>`;
  return out;
}

function renderCrossDoc(){
  const docs = FROZEN_ORDER.map(id => [id, DATA.docs[id]]).filter(([, d]) => d && d.meta.deep && !d.live);
  if (docs.length < 2) return "";
  let out = `<div class="scrollx"><table class="t"><tr><th>Doküman</th><th>Sayfa</th><th>Unit</th><th>Parça S→D</th><th>Yapısal problem S→D${info(TERMS.smell.help)}</th><th>Kötüleşen bölüm${info(TERMS.regression.help)}</th><th>Kural / LLM sınır</th><th>LLM çağrısı</th><th>Doğrulanan öneri</th><th>Süre (s)</th><th>İlk 5'te doğru S→D${info(TERMS.hit.help)}</th></tr>`;
  for (const [id, d] of docs) {
    const dm = d.meta.deep, sc = dm.storyCounts || {}, o = sc.final_boundaries_by_origin || {}, r = dm.retrieval || {};
    out += `<tr><td>${esc(d.label)}${id === "arcelik-2024" ? ' <span class="pill grey">holdout — tuning görmedi</span>' : ""}</td><td>${d.meta.pageCount}</td><td>${d.meta.unitCount}</td><td>${dm.chunkCount.standard} → ${dm.chunkCount.deep}</td><td>${dm.smellTotal.standard} → <b>${dm.smellTotal.deep}</b></td><td>${dm.regressions}</td><td>${o.deterministic ?? "—"} / ${o.llm ?? "—"}</td><td>${dm.calls.total}</td><td>${dm.verifier ? dm.verifier.accepted + "/" + dm.verifier.group_count : "—"}</td><td>${((dm.timing.llm_calls || 0) + (dm.timing.verifier_calls || 0) + (dm.timing.selection || 0)).toFixed(0)}</td><td>${r.deep && r.standard ? fmt(r.standard.hit_at_5, 3) + " → " + fmt(r.deep.hit_at_5, 3) : "gold yok"}</td></tr>`;
  }
  return out + `</table></div><div class="legend">KKB 2024 kuralların ayarlandığı dokümandır; KKB 2022 ve Arçelik 2024 ${term("holdout")} — üzerlerinde hiçbir ayar yapılmadı. Aynı sözleşmenin bu dokümanlarda da tutması, sonucun tek bir dokümana özel ayarla elde edilmediğini gösterir. Kalan problemlerin tamamı ${term("ceiling")} ya da parser kaynaklıdır.</div>`;
}

// -- the product layer over the measurements -------------------------------
// Benchmark opens with the answer ("bu dokümanda ne kazandık, neye mal oldu"),
// then the side-by-side method view, and only then the audit tables. Nothing
// is removed: every technical table is one click away, with its own caption.

function benchSummary(doc, dm, step){
  const ts = dm.totals.standard || {}, td = dm.totals.deep || {};
  const sc = dm.storyCounts || {};
  const origin = sc.final_boundaries_by_origin || {};
  const secs = (dm.timing.llm_calls || 0) + (dm.timing.verifier_calls || 0) + (dm.timing.selection || 0);
  const retr = dm.retrieval || {};
  const fixed = Math.max(0, dm.smellTotal.standard - dm.smellTotal.deep);
  const live = Boolean(doc.live);
  const llm = dm.calls && dm.calls.total > 0;
  let out = sectionHead(step, live ? "Bu dokümanda kalite" : "Kalite özeti",
    live
      ? `<b>${esc(doc.label)}</b> için yüklemede üretilen parçalar üzerinden ölçüldü.`
      : `<b>${esc(doc.label)}</b> üzerinde Standard ile Deep Analysis arasındaki ölçülen fark.`);
  out += `<div class="kpis">
    ${kpi(term("smell"), null, arrowValue(dm.smellTotal.standard, dm.smellTotal.deep),
      `<b>${fixed}</b> sorunlu sınır ortadan kalktı.`, "hero")}
    ${kpi(term("regression"), null, `<span style="color:var(--good)">${dm.regressions}</span>`,
      dm.regressions === 0 ? "Deep Analysis hiçbir bölümde, hiçbir problem türünde Standard'ın gerisine düşmedi." : "Sözleşme ihlali — bu koşu incelenmeli.")}
    ${kpi("Düzeltmeyi kim yaptı?", "Deep Analysis'in taşıdığı ya da eklediği chunk sınırlarının kaynağı: ücretsiz kural katmanı mı, LLM mi.",
      `${origin.deterministic || 0}<span class="unit">kural</span><span class="arrow">+</span><span class="to">${origin.llm || 0}</span><span class="unit">LLM</span>`,
      (origin.deterministic || origin.llm)
        ? `LLM ${sc.llm_consulted_sections ?? "—"} bölümde devreye girdi; kazanımın çoğu LLM'siz katmandan geliyor.`
        : "Deep Analysis bu dokümanda hiçbir sınırı taşımadı: Standard zaten temiz kesmişti.")}
    ${retr.deep && retr.standard ? kpi(term("hit"), null,
      arrowValue(fmt(retr.standard.hit_at_5, 3), fmt(retr.deep.hit_at_5, 3)),
      `${retr.deep.query_count} gold soruda, ilk 5 sonuç içinde. Bu örneklemde fark gürültü içindedir: iddia “Deep daha iyi” değil, <b>“Deep en az Standard kadar iyi”</b>dir.`)
      : kpi(term("goldset"), null, `<span class="unit" style="font-size:17px">ölçülmedi</span>`,
        "Bu dokümanın gold sorgu seti yok; arama karşılaştırması yapılmadı ve uydurulmadı.")}
    ${llm
      ? kpi("Ek maliyet", "Deep Analysis yalnız yükleme sırasında çalışır: sorgu anına ne maliyet ne gecikme ekler.",
          `≈ $${dm.estCostUsd.toFixed(3)}`,
          `${dm.calls.total} LLM çağrısı · ${secs ? secs.toFixed(0) + " s" : "—"} · yüklemede tek sefer`)
      : kpi("Ek maliyet", "Bu koşuda hiçbir model çağrısı yapılmadı: kazanımın tamamı deterministik kalite sözleşmesinden geliyor.",
          `<span style="color:var(--good)">yok</span>`, `0 LLM çağrısı · sonuç tekrarlanabilir`)}
    ${kpi(term("ceiling"), null, `${sc.ceiling_boundaries ?? "—"}`,
      `Tek bir tablo ya da paragraf bütçeden büyük olduğu için hiçbir yöntemin kaçınamayacağı kesim. Deep'te kalan ${dm.smellTotal.deep} problem ağırlıklı olarak buradan geliyor.`)}
  </div>`;
  out += boundaryQualityTable(ts, td, dm);
  out += llm
    ? `<div class="guard deep" style="margin-top:16px"><b>Neyi iddia etmiyoruz.</b> Deep Analysis model kullanır; aynı koşu birebir tekrarlanmaz ve bir “kazanan yöntem” ilan edilmez. Ölçülen ve garanti edilen şey şudur: yapısal problemler azalır, hiçbir bölüm kötüleşmez, arama kalitesi en azından korunur. Eşikler PoC seviyesindedir, optimize edilmemiştir.</div>`
    : `<div class="guard deep" style="margin-top:16px"><b>Bu koşuda model kullanılmadı.</b> Karşılaştırmanın Deep tarafını yalnız deterministik kalite sözleşmesi üretti: sonuç tekrarlanabilir, maliyeti yok ve model katmanının ekleyeceği kazanç bu tabloda <b>yer almıyor</b>. Onu görmek için dokümanı RAG Console'da Deep Analysis seçeneğiyle yükleyin. Eşikler PoC seviyesindedir, optimize edilmemiştir.</div>`;
  return out;
}

// The per-type contract counters, at the top level of the tab that exists to
// show them. The same six rows appear in Sunum as bars; here they carry the
// delta and the counter's own name, because this is where they are audited.
function boundaryQualityTable(ts, td, dm){
  const rows = ["orphan_label","lead_in_cut","continuation_cut","run_split_when_fits",
                "table_split","fragment_cut","below_min","above_soft_max"];
  return `<h3 class="sub" style="margin-top:22px">Sınır kalitesi — problem türü başına<span class="muted" style="font-weight:400;font-size:13.5px;margin-left:10px">bölüm bazında sözleşme sayaçları</span></h3>
    <div class="scrollx"><table class="t"><tr><th>Problem türü</th><th>Standard</th><th>Deep</th><th>Δ</th></tr>` +
    rows.map(k => {
      const s = ts[k] ?? 0, d = td[k] ?? 0, delta = d - s;
      return `<tr><td>${esc(SMELL_TEXT[k] || k)}${info(SMELL_HELP[k])} <span class="mono muted">${k}</span></td>
        <td>${s}</td><td class="deepcol">${d}</td><td${delta < 0 ? ' style="color:var(--good);font-weight:650"' : ""}>${delta > 0 ? "+" : ""}${delta || "—"}</td></tr>`;
    }).join("") +
    `<tr><td><b>toplam</b></td><td><b>${dm.smellTotal.standard}</b></td><td class="deepcol"><b>${dm.smellTotal.deep}</b></td><td><b>${dm.smellTotal.deep - dm.smellTotal.standard}</b></td></tr>
    </table></div>`;
}

function benchMethods(doc, step){
  const arms = doc.arms;
  const frozen = ARMS.filter(a => arms[a] && arms[a].ret);
  if (frozen.length < 3) return "";
  let out = sectionHead(step, "Yöntemler yan yana",
    `Aynı ${doc.meta.queryCount} soruyla arandı. Sayılar 0–1 arası, yüksek olan iyi.`);
  const rows = frozen.map(a => ({arm: armFull(a), values: arms[a].ret}));
  const deepArm = arms.agentic && isDeepArm("agentic") && arms.agentic.ret ? [{arm: armFull("agentic"), values: arms.agentic.ret}] : [];
  out += benchTable("Arama başarısı — hangi yöntem doğru parçayı getiriyor?", rows.concat(deepArm), RET_COLS_PLAIN, true,
    new Set(deepArm.map(r => r.arm)));
  out += `<div class="legend">● işareti bu koşuda gözlenen en iyi değeri gösterir. Tek bir yöntem her sütunda önde değildir — bu beklenen bir sonuçtur ve tek başına bir kazanan ilan etmez. Değerler PoC parametreleriyle, tek koşuda alınmıştır.</div>`;
  return out;
}

function renderBenchmark(){
  const doc = D();
  const dm = doc.meta.deep;
  let out = "";
  let step = 0;
  const nextStep = () => ++step;
  if (doc.live) {
    out += `<div class="guard"><b>Canlı çalışma alanı dokümanı.</b> Ölçümler bu dokümanın RAG Console'daki kendi yüklemesinden geliyor. Dondurulmuş karşılaştırma setinin parçası değildir ve o tabloları değiştirmez; gold sorgusu olmadığı için arama metrikleri hesaplanmaz.</div>`;
  }
  if (dm) out += benchSummary(doc, dm, nextStep());
  const methods = benchMethods(doc, step + 1);
  if (methods) nextStep();
  out += methods;
  if (!dm && !methods) out += `<div class="guard">Bu doküman için ne dondurulmuş üç kol karşılaştırması ne de Deep Analysis paneli var.</div>`;
  const frozen = renderFrozenBenchmark(doc);
  if (frozen) {
    out += sectionHead(nextStep(), "Ölçüm ayrıntısı",
      "Yukarıdaki sayıların arkasındaki ham ölçümler.");
    out += `<details class="deep-detail"><summary>Dondurulmuş üç kol karşılaştırması — tüm metrikler (frozen benchmark v5)</summary><div class="inner">${frozen}</div></details>`;
  } else if (dm) {
    out += sectionHead(nextStep(), "Ölçüm ayrıntısı",
      "Bu dokümanın ölçüm sorusu olmadığı için arama karşılaştırması yok; aşağıdaki panel yapısal ölçümleri verir.");
  }
  const ag = doc.arms.agentic;
  if (ag && isLegacyAgentic()) {
    const am = doc.agenticMeta || {}, s = am.summary || {}, bd = am.diff || {};
    out += `<h2>Agentic Chunker — ayrı koşu</h2><div class="guard">Model-bağımlı sonuç (yalnız replay-deterministic); frozen üç kolun karşılaştırmasına dahil değildir ve kazanan ilan edilmez. Model: ${esc(am.model || "—")} · mod: ${esc(am.mode || "—")}.</div>
      <div class="cards"><div class="card stat"><div class="v">${ag.chunks.length}</div><div class="k">Agentic chunk</div></div>
      <div class="card stat"><div class="v">${bd.decision_windows ?? s.decision_window_count ?? "—"}</div><div class="k">karar penceresi</div></div>
      <div class="card stat"><div class="v">${bd.window_moved ?? s.window_moved_count ?? "—"}</div><div class="k">pencere düzeyinde farklı seçim</div></div>
      <div class="card stat"><div class="v">${bd.final_boundary_moved ?? s.final_boundary_moved_count ?? "—"}</div><div class="k">final chunk sınırı taşınan</div></div>
      <div class="card stat"><div class="v">${bd.rejoined_after_agentic_cut ?? s.rejoined_after_agentic_cut_count ?? "—"}</div><div class="k">rejoin ile geri birleşen</div></div>
      <div class="card stat"><div class="v">${s.provider_call_count ?? "—"}</div><div class="k">provider çağrısı</div></div></div>`;
    if (ag.ret) {
      out += benchTable("Retrieval — Agentic Chunker (ayrı koşu, aynı gold + BM25 ayarları)", [{arm: armFull("agentic"), values: ag.ret}], RET_COLS);
      out += `<div class="legend">Bu tablo tek satırdır ve frozen üçlü tablodaki "en iyi" işaretlerine katılmaz; yan yana okuma yaparken model bağımlılığı ve tek koşu olduğu unutulmamalıdır.</div>`;
    } else out += `<div class="legend">Bu ağaçta agentic retrieval değerlendirmesi yok — amsc.agentic_benchmark henüz koşulmamış.</div>`;
  }
  const deepPanel = renderDeepPanel(doc);
  if (deepPanel) {
    out += `<details class="deep-detail"><summary>Deep Analysis ölçüm paneli — sınır kalitesi, model kullanımı, maliyet</summary>
      <div class="inner"><div class="help" style="margin:0 0 6px">Yukarıdaki özetin arkasındaki bölüm bazlı sözleşme sayaçları, LLM çağrı dökümü ve token/maliyet tahmini.</div>${deepPanel}</div></details>`;
  }
  const crossDoc = doc.live ? "" : renderCrossDoc();
  if (crossDoc) {
    out += `<details class="deep-detail"><summary>Dokümanlar arası — aynı sözleşme üç dokümanda</summary>
      <div class="inner"><div class="help" style="margin:0 0 6px">Aynı kurallar, üzerinde hiç ayar yapılmamış dokümanlarda da tutuyor mu? Bu tablo o sorunun cevabıdır.</div>${crossDoc}</div></details>`;
  }
  out += glossary(doc.live
    ? ["smell","regression","ceiling","goldset","llmrole","chunk","sizetrade"]
    : ["smell","regression","ceiling","hit","mrr","coverage","goldset","holdout","llmrole","chunk","sizetrade","frozen"]);
  $("view-benchmark").innerHTML = out;
  $("view-benchmark").querySelectorAll(".qidchip[data-q]").forEach(el => {
    el.onclick = () => { state.mode = "query"; state.qsub = "gold"; state.query = el.dataset.q; render(); };
  });
}

/* -------- workspace: the RAG console's live state --------
   The console owns knowledge bases and documents; this page owns the chunking
   analysis. Rather than keeping a second copy of the console's state, the page
   asks its own server for it (/api/workspace proxies the console), so a
   knowledge base created over there shows up here on the next refresh with
   nothing to update by hand. */
const workspace = {status: "idle", data: null, modalOpen: false, at: 0, error: null,
  loading: null, preparing: new Set(), poll: null};

// A live document's payload is built by the console from its own ingest and
// relayed by this page's own server. It is merged into the same DATA.docs the
// frozen corpus lives in -- every renderer then works unchanged -- but it is
// flagged, so nothing that belongs to the frozen benchmark can pick it up.
async function openLiveDoc(docId, label){
  if (LIVE_LOADED.has(docId)) { selectDoc(docId); return; }
  if (workspace.loading === docId) return;
  workspace.loading = docId;
  renderWorkspace();
  try {
    const r = await fetch("/api/live-document?doc=" + encodeURIComponent(docId), {cache: "no-store"});
    const body = await r.json();
    if (!r.ok || !body.connected || !body.payload) throw new Error(body.reason || body.error || ("HTTP " + r.status));
    const doc = body.payload;
    doc.live = Object.assign({docId, label: label || doc.label}, doc.live || {});
    DATA.docs[docId] = indexDoc(doc);
    if (!DOC_ORDER.includes(docId)) DOC_ORDER.push(docId);
    LIVE_LOADED.add(docId);
    workspace.error = null;
    selectDoc(docId);
  } catch (e) {
    workspace.error = String(e.message || e);
    syncDocOptions();
  } finally {
    workspace.loading = null;
    renderWorkspace();
  }
}

// Everything that changes when the document changes, in one place, so the
// picker, the workspace dialog and a jump from a table cannot drift apart.
function selectDoc(docId){
  // A live document listed by the console but not yet fetched: get it first,
  // so choosing it from the picker and opening it from the dialog are the
  // same action to the reader and the same code path here.
  if (!DATA.docs[docId]) {
    const row = liveDocs().find(({doc}) => doc.doc_id === docId);
    if (row) openLiveDoc(docId, row.doc.name);
    else syncDocOptions();
    return;
  }
  state.doc = docId;
  state.page = null; state.query = null; state.selChunk = null; state.selUnit = null; state.diffIdx = -1;
  state.arm = defaultArm();
  state.armB = hasArm("structure-only") && state.arm !== "structure-only"
    ? "structure-only" : (docArms().find(a => a !== state.arm) || state.arm);
  state.chat.turns = []; state.chat.arm = null;
  state.selArm = state.arm; state.lanes = null; state.page = null; state.unfolded = new Set();
  if (isLive() && state.qsub === "gold") state.qsub = "chat";
  syncDocOptions();
  render();
}

async function prepareLiveDoc(docId){
  workspace.preparing.add(docId);
  renderWorkspace();
  try {
    await fetch("/api/live-prepare", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({doc: docId})});
  } catch (e) { workspace.error = String(e.message || e); }
  workspace.preparing.delete(docId);
  await loadWorkspace();
}

async function loadWorkspace(){
  if (location.protocol === "file:") { workspace.status = "standalone"; renderWorkspace(); return; }
  workspace.status = workspace.data ? "refreshing" : "loading";
  renderWorkspace();
  try {
    // prepare=1 asks the console to queue an analysis for every document that
    // has none. Queuing only: the console packages on its own worker, so this
    // call returns at status speed however much work is outstanding.
    const r = await fetch("/api/workspace?prepare=1", {cache: "no-store"});
    const payload = await r.json();
    if (!r.ok) throw new Error(payload.error || ("HTTP " + r.status));
    workspace.data = payload.connected ? payload : null;
    workspace.status = payload.connected ? "live" : (payload.configured ? "down" : "standalone");
    workspace.error = payload.connected ? null : (payload.reason || null);
  } catch (e) {
    workspace.data = null;
    workspace.status = "down";
    workspace.error = String(e.message || e);
  }
  workspace.at = Date.now();
  renderWorkspace();
  syncDocOptions();
  scheduleWorkspacePoll();
}

// While the console is still packaging something, look again shortly. The
// poll stops as soon as nothing is outstanding, so an idle page is idle.
function scheduleWorkspacePoll(){
  if (workspace.poll) { clearTimeout(workspace.poll); workspace.poll = null; }
  const busy = liveDocs().some(d => ["pending","running"].includes((d.doc.viewer || {}).status));
  if (busy) workspace.poll = setTimeout(loadWorkspace, 4000);
}

// Every console document, flattened, with its knowledge base beside it.
function liveDocs(){
  const kbs = (workspace.data && workspace.data.knowledge_bases) || [];
  const out = [], seen = new Set();
  for (const kb of kbs) for (const doc of (kb.documents || [])) {
    if (seen.has(doc.doc_id)) continue;  // the same record must not read as two
    seen.add(doc.doc_id);
    out.push({kb, doc});
  }
  return out;
}
// The same file uploaded to two knowledge bases is two documents, and a reader
// picking between them needs to see which is which.
function liveDocLabel(entry, rows){
  const name = entry.doc.name || entry.doc.doc_id;
  const twin = rows.some(r => r.doc.doc_id !== entry.doc.doc_id && (r.doc.name || r.doc.doc_id) === name);
  return twin && entry.kb && entry.kb.name ? `${name} · ${entry.kb.name}` : name;
}
const liveReady = () => liveDocs().filter(d => (d.doc.viewer || {}).status === "ready");

// Console records that are the same document: same bytes, one analysis. The
// picker shows the document, not the number of times it was uploaded.
function liveDocuments(){
  const seen = new Map();
  for (const row of liveDocs()) {
    const key = (row.doc.viewer || {}).analysis_key || row.doc.doc_id;
    if (!seen.has(key)) seen.set(key, row);
  }
  return [...seen.values()];
}

// One picker for everything a reader can actually open. The frozen corpus and
// the console's live documents are two groups inside it, not two places to
// look -- and a live document appears here as soon as its analysis is ready,
// whether or not this page has loaded it yet.
function syncDocOptions(){
  const sel = $("docsel");
  if (!sel) return;
  const frozen = FROZEN_ORDER.map(id =>
    `<option value="${esc(id)}">${esc(DATA.docs[id].label)}</option>`).join("");
  const rows = liveDocuments();
  const live = rows.map(entry => {
    const doc = entry.doc;
    const status = (doc.viewer || {}).status;
    const name = liveDocLabel(entry, rows);
    if (status === "ready") return `<option value="${esc(doc.doc_id)}">${esc(name)}</option>`;
    const note = (status === "pending" || status === "running") ? "analiz hazırlanıyor…"
      : (status === "failed" ? "analiz hazırlanamadı" : "analiz yok");
    return `<option value="${esc(doc.doc_id)}" disabled>${esc(name)} — ${note}</option>`;
  }).join("");
  // A document opened earlier but no longer listed by the console (deleted
  // over there) stays selectable only while it is the one being shown.
  const orphan = isLive() && !rows.some(({doc}) => doc.doc_id === state.doc)
    ? `<option value="${esc(state.doc)}">${esc(DATA.docs[state.doc].label)} — konsolda yok</option>` : "";
  sel.innerHTML = `<optgroup label="Dondurulmuş karşılaştırma seti">${frozen}</optgroup>` +
    (live || orphan ? `<optgroup label="RAG Console — canlı dokümanlar">${live}${orphan}</optgroup>` : "");
  sel.value = state.doc;
}

// The button in the top bar is the whole resting state of the workspace: a
// dot, a name and a count. Everything else waits behind a click.
function renderWorkspace(){
  const button = $("wsopen");
  if (!button) return;
  const data = workspace.data;
  const live = workspace.status === "live";
  button.className = "btn small" + (live ? " live" : (workspace.status === "down" ? " down" : ""));
  const totals = (data && data.totals) || {};
  let label = "RAG Console";
  if (workspace.status === "loading") label = "RAG Console · okunuyor…";
  else if (live) {
    const docs = liveDocuments().length;
    const ready = liveDocuments().filter(d => (d.doc.viewer || {}).status === "ready").length;
    label = `RAG Console · ${ready}/${docs} doküman hazır`;
  }
  else if (workspace.status === "down") label = "RAG Console · bağlı değil";
  $("wslabel").textContent = label;
  button.title = live && data.url ? `${data.url} — bilgi tabanlarını ve dokümanları gör`
    : (workspace.error || "RAG Console bağlantısı");
  if (workspace.modalOpen) renderWorkspaceModal();
}

function openWorkspaceModal(){
  workspace.modalOpen = true;
  renderWorkspaceModal();
  loadWorkspace();
}

function renderWorkspaceModal(){
  const data = workspace.data;
  const live = workspace.status === "live";
  const totals = (data && data.totals) || {};
  const facts = live
    ? `<span>${totals.knowledge_bases ?? 0} bilgi tabanı</span><span>${totals.documents ?? 0} doküman</span><span>${(totals.chunks ?? 0).toLocaleString("tr-TR")} parça</span><span>${totals.viewer_ready ?? 0} tanesi Viewer'da hazır</span>`
    : `<span>${workspace.status === "loading" ? "durum okunuyor…" : "bağlanılamadı"}</span>`;
  let body;
  if (!live) {
    body = `<p>RAG Console'a ulaşılamıyor. Konsol kapalıysa bu sayfanın geri kalanı etkilenmez; dondurulmuş karşılaştırma seti çalışmaya devam eder.</p>
      ${workspace.error ? `<p class="muted mono" style="font-size:12.5px">${esc(workspace.error)}</p>` : ""}`;
  } else {
    const kbs = data.knowledge_bases || [];
    body = `<p style="font-size:14.5px">Konsola yüklediğiniz dokümanların analizi <b>kendiliğinden hazırlanır</b> — yüklemede üretilen parçalar ve kalite ölçümleri yeniden kullanılır, doküman ikinci kez ne ayrıştırılır ne de modele gönderilir. Hazır olanları üstteki <b>doküman seçiciden</b> de açabilirsiniz.</p>` +
      kbs.map(kb => {
        const docs = kb.documents || [];
        const rows = docs.map(doc => liveDocRow({kb, doc})).join("");
        return `<div class="wskb"${kb.orphan ? ' style="opacity:.72"' : ""}>
          <div class="kbname">${kb.orphan ? "Bilgi tabanı silinmiş kayıtlar" : esc(kb.name)}</div>
          <div class="kbmeta">${(kb.orphan ? ["bilgi tabanı silindi, doküman kayıtları duruyor"] : [kb.chunker ? "bölümleme: " + (KB_CHUNKERS[kb.chunker] || kb.chunker) : "", kb.retrieval_method ? "arama: " + kb.retrieval_method : ""]).filter(Boolean).map(x => `<span>${esc(x)}</span>`).join("")}<span>${docs.length} doküman</span><span>${(kb.chunk_count || 0).toLocaleString("tr-TR")} parça</span></div>
          ${docs.length
            ? (kb.orphan
              ? `<details><summary>${docs.length} doküman kaydını göster</summary><div class="docs">${rows}</div></details>`
              : `<div class="docs">${rows}</div>`)
            : `<div class="none">Henüz doküman yüklenmemiş.</div>`}
        </div>`;
      }).join("");
  }
  const actions = `<button class="btn small" id="wsrefresh">Yenile</button>` +
    (live && data.url ? ` <a class="btn small" href="${esc(data.url)}" target="_blank" rel="noopener">Konsolu aç ↗</a>` : "");
  openModal("RAG Console", facts, `<div class="wsbody">${body}</div>`, actions);
  const previous = $("mclose").onclick;
  $("mclose").onclick = () => { workspace.modalOpen = false; previous(); };
  const refresh = $("wsrefresh");
  if (refresh) refresh.onclick = loadWorkspace;
  $("modal").querySelectorAll(".linkbtn[data-live]").forEach(el => {
    el.onclick = () => { workspace.modalOpen = false; closeModal(); openLiveDoc(el.dataset.live, el.dataset.label); };
  });
  $("modal").querySelectorAll(".linkbtn[data-prepare]").forEach(el => {
    el.onclick = () => prepareLiveDoc(el.dataset.prepare);
  });
}

// The console's own vocabulary, in the words the rest of the page uses.
const INGEST_MODES = {deep_analysis: "Deep Analysis", standard: "Standard"};
const KB_CHUNKERS = {structure_first: "Standard (structure-first)", legacy: "eski bölümleyici", v4: "V4 (araştırma)"};

// One console document's row: what the Viewer can do with it, and the single
// action that moves it forward.
function liveDocRow(entry){
  const doc = entry.doc;
  const viewer = doc.viewer || {};
  const status = viewer.status || "missing";
  const id = doc.doc_id;
  const preparing = workspace.preparing.has(id);
  let action = "", note = "";
  if (status === "ready") {
    action = `<button class="linkbtn" data-live="${esc(id)}" data-label="${esc(doc.name || id)}">${workspace.loading === id ? "açılıyor…" : "Viewer'da aç"}</button>`;
    // What this document *has*, not how its upload was labelled: a document
    // with no Deep variant must never be badged as a Deep ingest.
    const ready = viewer.ready_methods || [];
    note = ready.includes("agentic")
      ? `<span class="pill deep">Deep Analysis ile yüklendi</span>${info("Yükleme sırasında çalışan Deep Analysis koşusu olduğu gibi paketlendi; Viewer için ikinci bir model çağrısı yapılmadı. Modelin gerçekten çağrılıp çağrılmadığını dokümanın kendi Sunum ekranı söyler.")}`
      : `<span class="pill grey">Deep Analysis çalıştırılmadı</span>${info("Bu doküman için Deep Analysis istenmedi. Ekleyebilirsiniz: analiz yeniden hazırlanır, doküman ikinci kez okunmaz.")}`;
  } else if (status === "pending" || status === "running" || preparing) {
    action = `<span class="pill grey">Viewer analizi hazırlanıyor…</span>`;
  } else if (status === "failed") {
    action = `<button class="linkbtn" data-prepare="${esc(id)}">Yeniden dene</button>`;
    note = `<span class="pill miss" title="${esc(viewer.error || "")}">hazırlanamadı</span>`;
  } else {
    action = `<button class="linkbtn" data-prepare="${esc(id)}">Viewer analizi hazırla</button>`;
  }
  const ready = (viewer.ready_methods || []).map(m => modeName(m).top);
  const shared = (viewer.shared_with || []).length;
  return `<div class="wsdoc"><span class="dname">${esc(doc.name || id)}</span>${action}${note}
    ${shared ? `<span class="pill grey" title="Aynı dosya birden çok kez yüklendi; hepsi tek analiz olarak tutuluyor.">aynı doküman ×${shared + 1}</span>` : ""}
    <span class="dmeta">${(doc.chunk_count || 0).toLocaleString("tr-TR")} parça${ready.length ? " · " + esc(ready.join(", ")) : ""}</span></div>`;
}

/* -------- shell -------- */
// Every screen opens the same way -- which screen, which document, what for --
// so a reader landing on any tab knows where they are before reading a number.
const MODE_TITLES = {presentation: "Sunum", query: "Sorgu", debug: "Debug", benchmark: "Benchmark"};
const PAGE_LEADS = {
  presentation: "Sonuç, çalışan yöntemler ve parçaların yan yana karşılaştırması — sunuma hazır görünüm.",
  debug: "Her kart ayrıştırıcının çıkardığı bir birim — başlık, paragraf ya da tablo — ve altında her yöntemde hangi parçaya düştüğü. Karta tıklayın; sağdaki panel alanları ve Deep Analysis karar izini açar.",
  benchmark: "Ölçülen sonuçlar: kalite sayaçları, arama başarısı ve ham metodoloji tabloları."
};
function renderPageHead(){
  const doc = D();
  const an = analysisState();
  const compact = state.mode === "presentation";
  const lead = state.mode === "query"
    ? ((doc.gold || []).length
        ? "Kendi sorunuzu sorun ya da ölçüm sorularında yöntemlerin doğru parçayı kaçıncı sırada getirdiğini görün."
        : "Bu dokümana bir soru sorun; cevabın hangi parçalardan geldiği altında listelenir.")
    : PAGE_LEADS[state.mode];
  const kind = isLive()
    ? `<span class="pill ok">RAG Console · canlı doküman</span>`
    : `<span class="pill std">Dondurulmuş karşılaştırma seti</span>`;
  const deep = an ? `<span class="pill ${an.pill || "deep"}">Deep Analysis${an.tag ? " · " + esc(an.tag) : ""}</span>` : "";
  const facts = [compact ? null : `${doc.meta.unitCount.toLocaleString("tr-TR")} birim`,
                 `${doc.meta.pageCount || Math.max(...doc.pages)} sayfa`,
                 `${docArms().length} yöntem`].filter(Boolean);
  $("pagehead").className = "pagehead" + (compact ? " compact" : "");
  $("pagehead").innerHTML = `<div class="ph-main">
      <div class="eyebrow">${MODE_TITLES[state.mode]}</div>
      <h1>${esc(doc.label)}</h1>
      ${compact ? "" : `<div class="lead">${lead}</div>`}
    </div>
    <div class="facts">${kind}${deep}${facts.map(f => `<span>${f}</span>`).join("")}</div>`;
}
function render(){
  syncBar();
  renderPageHead();
  for (const mode of ["presentation","query","debug","benchmark"]) $("view-" + mode).classList.toggle("hidden", state.mode !== mode);
  if (state.mode === "presentation") renderPresentation();
  else if (state.mode === "query") renderQuery();
  else if (state.mode === "debug") renderDebug();
  else renderBenchmark();
  measureBar();  // section heads and toolbars change height with the mode
  $("foot").textContent = D().label + " · " + (isLive() ? "canlı çalışma alanı dokümanı" : "dondurulmuş karşılaştırma seti") +
    " · canonical " + (D().meta.canonicalSha || "").slice(0, 12) + "… · " + DATA.generator;
}
initBar();
render();
</script>
</body>
</html>
"""
