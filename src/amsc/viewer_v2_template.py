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
  --paper:#f7f6f2; --panel:#ffffff; --ink:#1f2328; --muted:#66707a;
  --line:#e2e0d9; --line-strong:#cfcbc0; --accent:#1f4f9c; --accent-soft:#e6eefb;
  --deep:#5b3ea6; --deep-soft:#efe9fb; --good:#1a7f37; --good-soft:#e6f4ea;
  --warn:#b45309; --warn-soft:#fdf1df; --bad:#b42318; --bad-soft:#fbe9e6;
  --tintA:#f1f5fc; --tintB:#faf5ec; --mark:#fff2a8;
  --font:"Segoe UI",system-ui,-apple-system,"Helvetica Neue",sans-serif;
  --serif:Georgia,"Times New Roman",serif;
  --mono:Consolas,"Cascadia Mono",Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--paper);color:var(--ink);font:15px/1.55 var(--font)}
button{font:inherit;color:inherit;background:none;border:none;cursor:pointer}
button:focus-visible,select:focus-visible,textarea:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
select,textarea,input[type=text]{font:inherit;color:inherit;padding:5px 9px;border:1px solid var(--line-strong);border-radius:7px;background:#fff}
a{color:var(--accent)}
.hidden{display:none!important}
.muted{color:var(--muted)}
.mono{font-family:var(--mono);font-size:12.5px}
.nowrap{white-space:nowrap}

/* ---- top bar ---- */
.topbar{position:sticky;top:0;z-index:40;background:var(--panel);border-bottom:1px solid var(--line);
  padding:10px 22px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.brand{font-weight:650;letter-spacing:.2px;display:flex;align-items:baseline;gap:8px}
.brand small{color:var(--muted);font-weight:400}
.brand .tag{font-size:10.5px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;
  color:var(--accent);background:var(--accent-soft);border-radius:999px;padding:2px 8px}
.tabs{display:flex;gap:3px;background:#efeee8;border-radius:10px;padding:3px}
.tabs button{padding:6px 16px;border-radius:8px;color:var(--muted);font-weight:500}
.tabs button.on{background:#fff;color:var(--ink);box-shadow:0 1px 2px rgba(0,0,0,.08)}
.tabs button small{display:block;font-size:10.5px;font-weight:400;line-height:1.1;opacity:.75}
.seg{display:flex;gap:3px;background:#efeee8;border-radius:10px;padding:3px;flex-wrap:wrap}
.seg button{padding:5px 12px;border-radius:8px;color:var(--muted)}
.seg button.on{background:var(--accent);color:#fff}
.seg button.on.deep{background:var(--deep)}
.seg button small{display:block;font-size:10.5px;font-weight:400;line-height:1.1;opacity:.8}
.bar-right{margin-left:auto;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.filterseg button.on{background:#3d3f43;color:#fff}
.diffnav button{border:1px solid var(--line-strong);border-radius:7px;padding:4px 10px;background:#fff}
.diffnav button:disabled{opacity:.4;cursor:default}
.diffcount{color:var(--muted);font-size:13px}
.conttoggle{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--muted);cursor:pointer}
.modehint{font-size:12.5px;color:var(--muted);width:100%;padding-left:2px}
main{max-width:1760px;margin:0 auto;padding:20px 22px 40px}

/* ---- shared cards ---- */
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 18px}
.cards{display:flex;gap:12px;flex-wrap:wrap}
.stat{min-width:140px}
.stat .v{font-size:24px;font-weight:650;font-variant-numeric:tabular-nums;line-height:1.15}
.stat .v small{font-size:13px;font-weight:500;color:var(--muted);margin-left:4px}
.stat .k{color:var(--muted);font-size:12.5px;margin-top:2px}
.stat.deep .v{color:var(--deep)}
.stat.good .v{color:var(--good)}
.pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:2px 10px;font-size:12.5px;font-weight:600;white-space:nowrap}
.pill.ok{background:var(--good-soft);color:var(--good)}
.pill.mid{background:var(--warn-soft);color:var(--warn)}
.pill.miss{background:var(--bad-soft);color:var(--bad)}
.pill.deep{background:var(--deep-soft);color:var(--deep)}
.pill.std{background:var(--accent-soft);color:var(--accent)}
.pill.grey{background:#efeee8;color:#4b5259}
.chip{font:12px/1.5 var(--mono);background:#f0efe9;border-radius:5px;padding:1px 7px}
.chip.role{background:#e8e2f6}
.chip.opens{background:#dcefe2}
.chip.noopen{background:#f6e3e0}
.chip.big{background:var(--bad-soft);color:var(--bad)}
.chip.pf{background:var(--warn-soft);color:var(--warn)}
.note{color:var(--muted);font-size:13px;max-width:960px}
.guard{border-left:3px solid var(--accent);background:var(--accent-soft);padding:10px 16px;
  border-radius:0 8px 8px 0;font-size:13.5px;margin:12px 0 4px;max-width:960px}
.guard.deep{border-left-color:var(--deep);background:var(--deep-soft)}
h2.sec{margin:26px 0 10px;font-size:18px;font-weight:650}
h3.sub{margin:16px 0 8px;font-size:15px;font-weight:650}
details.adv{margin-top:10px}
details.adv summary{cursor:pointer;color:var(--accent);font-size:13px}
details.adv pre{white-space:pre-wrap;font:12px var(--mono);background:#f6f5f0;border-radius:8px;padding:10px;margin-top:8px;max-height:320px;overflow:auto}
table.t{border-collapse:collapse;background:var(--panel);font-variant-numeric:tabular-nums;font-size:13.5px}
table.t th,table.t td{border:1px solid var(--line);padding:6px 12px;text-align:right}
table.t th:first-child,table.t td:first-child{text-align:left}
table.t th{background:#f4f3ee;font-weight:600}
table.t td.best{font-weight:700;color:var(--accent)}
table.t td.best::after{content:" \25CF";font-size:9px;vertical-align:2px}
table.t td.deepcol{background:#faf7ff}
.scrollx{overflow-x:auto;max-width:100%}
.btn{border:1px solid var(--line-strong);border-radius:8px;padding:6px 14px;background:#fff;font-weight:500}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.deep{background:var(--deep);border-color:var(--deep);color:#fff}
.btn:disabled{opacity:.5;cursor:default}
.btn.small{padding:3px 10px;font-size:12.5px}
.linkbtn{color:var(--accent);text-decoration:underline;padding:0}

/* ---- Sunum: methods + results ---- */
.methods{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-bottom:16px}
.method{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;cursor:pointer;
  position:relative;transition:box-shadow .12s,border-color .12s}
.method:hover{box-shadow:0 2px 10px rgba(0,0,0,.06)}
.method.on{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}
.method.on.deepm{border-color:var(--deep);box-shadow:0 0 0 2px var(--deep-soft)}
.method .name{font-weight:650;font-size:15px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.method .desc{color:#3f4750;font-size:13px;margin-top:6px;line-height:1.45}
.method .facts{color:var(--muted);font-size:12px;margin-top:8px;display:flex;gap:10px;flex-wrap:wrap}
.method.absent{opacity:.55;cursor:default}
.results{background:linear-gradient(135deg,#f4f0ff 0%,#fff 60%);border:1px solid #e3dcf5;border-radius:12px;padding:14px 18px;margin-bottom:16px}
.results .title{font-weight:650;display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.results .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.results .item .v{font-size:20px;font-weight:650;font-variant-numeric:tabular-nums}
.results .item .v .arrow{color:var(--muted);font-weight:400;margin:0 5px}
.results .item .v .to{color:var(--deep)}
.results .item .k{font-size:12px;color:var(--muted)}
.smellbars{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:6px 18px;margin-top:10px;font-size:12.5px}
.smellbar{display:grid;grid-template-columns:150px 1fr 60px;gap:8px;align-items:center}
.smellbar .bar{height:8px;background:#ece8f8;border-radius:4px;position:relative;overflow:hidden}
.smellbar .bar i{position:absolute;left:0;top:0;bottom:0;background:#cdbff0;border-radius:4px}
.smellbar .bar b{position:absolute;left:0;top:0;bottom:0;background:var(--deep);border-radius:4px}
.smellbar .n{font-variant-numeric:tabular-nums;text-align:right}

/* ---- Sunum: reader ---- */
.pres-layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:20px}
.readerbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px;font-size:13px;color:var(--muted)}
.readerbar select{padding:3px 8px}
.docpage{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:34px 42px;
  font-family:var(--serif);font-size:16px}
.docpage .pagehead{font-family:var(--font);color:var(--muted);font-size:13px;margin-bottom:16px;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
.chunkline{display:flex;align-items:center;gap:10px;margin:18px 0 10px;font-family:var(--font);flex-wrap:wrap}
.chunkline .rule{flex:1;border-top:3px solid var(--accent);opacity:.5;min-width:30px}
.chunkline.tech .rule{border-top:2px dashed #c9a24b;opacity:.75}
.chunkline .kind{font-size:11.5px;font-weight:700;letter-spacing:.6px;color:var(--accent);text-transform:uppercase;white-space:nowrap}
.chunkline.tech .kind{color:#8a5a09}
.chunkpill{background:var(--accent-soft);color:var(--accent);border:1px solid #c8d8f2;border-radius:999px;
  padding:3px 13px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap}
.chunkline.tech .chunkpill{background:#fdf6e7;color:#8a5a09;border-color:#ecd9ab}
.chunkpill .why{font-weight:400;color:#41537a}
.chunkline.tech .chunkpill .why{color:#8a6a2f}
.chunkpill.sel{box-shadow:0 0 0 3px #f2d9a4}
.decpill{border-radius:999px;padding:2px 10px;font-size:12px;font-weight:600;white-space:nowrap;border:1px solid transparent}
.decpill.kept{background:#eef1f5;color:#4b5259;border-color:#dfe3e8}
.decpill.det{background:var(--good-soft);color:var(--good);border-color:#c6e6cf}
.decpill.llm{background:var(--deep-soft);color:var(--deep);border-color:#d8cbf3}
.decpill.rev{background:var(--warn-soft);color:var(--warn);border-color:#f2d9a4}
.decpill.ceil{background:var(--bad-soft);color:var(--bad);border-color:#f2c8c2}
.decpill.std{background:#fdf6e7;color:#8a5a09;border-color:#ecd9ab}
.u{padding:2px 10px;border-left:3px solid transparent;border-radius:4px}
.u.tintA{background:var(--tintA)}
.u.tintB{background:var(--tintB)}
.u.contedge{border-left:3px solid #e4c988}
.u.expmember{border-left:3px solid #c9861b;background:#fdf6e7}
.u.evflash{outline:3px solid var(--warn);outline-offset:2px}
.u.selchunk{outline:2px solid var(--accent);outline-offset:-2px}
.u h1,.u h2,.u h3,.u h4,.u h5,.u h6{font-family:var(--font);line-height:1.3;margin:14px 0 6px}
.u h1{font-size:24px}.u h2{font-size:21px}.u h3{font-size:18px}
.u h4{font-size:16px}.u h5{font-size:15px}.u h6{font-size:14px;color:#3c4046}
.u p{margin:7px 0}
.u ul{margin:7px 0 7px 22px}
.u li{margin:3px 0}
.tblwrap{overflow-x:auto;margin:10px 0}
.tblwrap table{border-collapse:collapse;font-size:13.5px;font-family:var(--font)}
.tblwrap th,.tblwrap td{border:1px solid var(--line);padding:4px 9px;text-align:left}
.tblwrap th{background:#f4f3ee}
.diffbadge{background:#fdecc8;color:var(--warn);border:1px solid #f2d9a4;border-radius:999px;padding:3px 10px;font-size:12px;font-weight:600;white-space:nowrap}
.diffbadge .glyphs{font-weight:400;margin-left:6px}
/* compare grid */
.cmp{display:grid;grid-template-columns:1fr 1fr;gap:0 18px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:24px 28px;font-family:var(--serif);font-size:15.5px}
.cmp .colhead{font-family:var(--font);font-weight:650;padding-bottom:8px;border-bottom:1px solid var(--line);margin-bottom:6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.cmp .cell{min-width:0;padding:2px 0}
.cmp .cell .chunkline{margin:12px 0 6px}
.cmp .cell .chunkpill{font-size:12px;padding:2px 10px}
.sidecard{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;
  position:sticky;top:74px;max-height:calc(100vh - 96px);overflow:auto}
.sidecard h3{font-size:15px;margin-bottom:10px}
.sidecard .kv{display:grid;grid-template-columns:100px 1fr;gap:5px 10px;font-size:13.5px}
.sidecard .kv dt{color:var(--muted)}
.sidecard .empty{color:var(--muted);font-size:13.5px}
.reason-sent{margin-top:12px;padding:10px 12px;background:#f6f5f0;border-radius:8px;font-size:13.5px}
.reason-sent.deep{background:var(--deep-soft)}
.arminfo{margin-top:14px;border-top:1px solid var(--line);padding-top:12px;font-size:12.5px;color:var(--muted)}
.detail-links button{color:var(--accent);text-decoration:underline;padding:0;font-size:13px}

/* ---- Sorgu ---- */
.subtabs{display:flex;gap:4px;margin-bottom:14px}
.subtabs button{padding:6px 14px;border-radius:8px;border:1px solid var(--line-strong);background:#fff;color:var(--muted)}
.subtabs button.on{background:#3d3f43;border-color:#3d3f43;color:#fff}
.chatwrap{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:20px}
.chatbox{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px}
.chatbox textarea{width:100%;min-height:76px;resize:vertical;font-size:15px}
.chatctl{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px}
.chatctl label{font-size:13px;color:var(--muted);display:flex;align-items:center;gap:6px}
.offline{border:1px dashed var(--line-strong);border-radius:12px;padding:14px 18px;color:var(--muted);font-size:13.5px;background:#fcfbf8;margin-bottom:14px}
.offline code{font-family:var(--mono);font-size:12.5px;background:#f0efe9;padding:1px 6px;border-radius:4px}
.suggest{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.suggest button{border:1px solid var(--line);border-radius:999px;padding:3px 11px;font-size:12.5px;background:#fff;color:#3f4750;text-align:left}
.turn{margin-top:18px}
.turn .q{font-weight:650;font-size:16px;margin-bottom:8px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.turn .q .who{font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--muted)}
.answer{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.answer .txt{font-size:15.5px;line-height:1.6;white-space:pre-wrap}
.answer .meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px;font-size:12.5px;color:var(--muted)}
.cite{display:inline-block;background:var(--accent-soft);color:var(--accent);border-radius:6px;padding:0 6px;font-size:12px;font-weight:700;margin:0 1px;vertical-align:baseline;font-family:var(--font)}
.cite:hover{background:var(--accent);color:#fff}
.sources{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px;margin-top:12px}
.src{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px;cursor:pointer;font-size:13px;position:relative}
.src:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}
.src.used{border-color:#9db7e6;background:#fbfcff}
.src.hl{outline:2px solid var(--warn)}
.src .lab{font-weight:700;color:var(--accent);font-size:12px;margin-right:6px}
.src .hd{font-weight:600;margin:3px 0}
.src .path{color:var(--muted);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.src .facts{color:var(--muted);font-size:12px;margin-top:5px;display:flex;gap:8px;flex-wrap:wrap}
.src .usedmark{position:absolute;right:10px;top:8px;color:var(--good);font-weight:700;font-size:12px}
.cmpcols{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-top:14px}
.cmpcol{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;min-width:0}
.cmpcol .armname{font-weight:650;display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap}
.cmpcol .txt{font-size:14px;line-height:1.55;white-space:pre-wrap;max-height:260px;overflow:auto;border-left:3px solid var(--line);padding-left:10px}
.cmpcol .srcs{margin-top:10px;font-size:12.5px}
.cmpcol .srcs div{padding:4px 0;border-bottom:1px solid var(--line);display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;cursor:pointer}
.chatside h3{font-size:14px;margin-bottom:8px}
.chatside .kv{display:grid;grid-template-columns:110px 1fr;gap:4px 8px;font-size:12.5px}
.chatside .kv dt{color:var(--muted)}
.qhead{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 22px;margin-bottom:16px}
.qhead .qq{font-size:18px;font-weight:600;margin-bottom:6px}
.qhead .qa{color:#374151;margin-bottom:10px}
.qhead .qmeta{color:var(--muted);font-size:13px;margin-bottom:10px}
.evbox{border-left:3px solid var(--warn);background:#fdf9ef;padding:10px 14px;border-radius:0 8px 8px 0;font-family:var(--serif);font-size:14.5px;max-height:210px;overflow:auto}
.evbox .evlabel{font-family:var(--font);font-size:12px;color:var(--warn);font-weight:600;letter-spacing:.4px;text-transform:uppercase;margin-bottom:6px}
.qcols{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.qcol{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;min-width:0}
.qcol .armname{font-weight:600;margin-bottom:8px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.qcol .covline{color:var(--muted);font-size:12.5px;margin-bottom:10px}
.rchunk{border:1px solid var(--line);border-radius:9px;padding:12px;font-family:var(--serif);font-size:14px;max-height:330px;overflow:auto}
.rchunk mark{background:var(--mark);padding:0 2px;border-radius:2px}
.rchunk .rhead{font-family:var(--font);font-size:12.5px;color:var(--muted);margin-bottom:8px}
.rchunk .piece{margin:6px 0}
.top5{margin-top:12px}
.top5 summary{cursor:pointer;color:var(--accent);font-size:13.5px}
.top5 .row{display:flex;gap:8px;align-items:baseline;padding:6px 4px;border-bottom:1px solid var(--line);font-size:13px;flex-wrap:wrap}
.top5 .row .rk{font-weight:600;min-width:44px}
.top5 .row .mt{color:var(--good)}
.qlink{margin-top:10px;font-size:13px}
.qlink button{color:var(--accent);text-decoration:underline;padding:0}

/* ---- Debug ---- */
.dbg{display:grid;grid-template-columns:minmax(0,1fr) 420px;gap:20px}
.dbgbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px;font-size:13px}
.dbgbar input[type=text]{min-width:220px}
.dbgunit{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:10px;cursor:pointer}
.dbgunit.sel{outline:2px solid var(--accent)}
.dbgunit .head{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:6px}
.dbgunit .path{font-size:12px;color:var(--muted);margin-bottom:6px;font-family:var(--mono);word-break:break-all}
.dbgunit .txt{font-size:13px;color:#374151;white-space:pre-wrap;max-height:80px;overflow:hidden}
.dbgtable{width:100%;border-collapse:collapse;font:12px var(--mono);margin-top:8px}
.dbgtable th,.dbgtable td{border:1px solid var(--line);padding:2px 7px;text-align:left}
.dbgtable th{background:#f4f3ee;font-family:var(--font)}
.inspector{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;
  position:sticky;top:74px;max-height:calc(100vh - 96px);overflow:auto;font-size:13px}
.inspector pre{white-space:pre-wrap;font:12.5px var(--mono);background:#f6f5f0;border-radius:8px;padding:10px;margin-top:8px;max-height:260px;overflow:auto}
.trail{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}
.trail .row{display:grid;grid-template-columns:110px 1fr;gap:4px 8px;font-size:12.5px;margin-bottom:4px}
.trail .row dt{color:var(--muted)}
.trail .grp{background:#f8f7f3;border-radius:8px;padding:8px 10px;margin-top:8px;font-size:12.5px}
.trail .grp .ids{font-family:var(--mono);font-size:11.5px;color:var(--muted);word-break:break-all}
.secpanel{margin-top:22px}
.sectable{width:100%;border-collapse:collapse;font-size:13px;background:var(--panel)}
.sectable th,.sectable td{border:1px solid var(--line);padding:5px 9px;text-align:left;vertical-align:top}
.sectable th{background:#f4f3ee;position:sticky;top:64px}
.sectable tr.clk{cursor:pointer}
.sectable tr.clk:hover{background:#fbfaf6}
.stpill{display:inline-block;border-radius:999px;padding:1px 9px;font-size:11.5px;font-weight:600}
.stpill.standard_kept{background:#eef1f5;color:#4b5259}
.stpill.deterministic_improved{background:var(--good-soft);color:var(--good)}
.stpill.llm_accepted{background:var(--deep-soft);color:var(--deep)}
.stpill.llm_reverted{background:var(--warn-soft);color:var(--warn)}
.stpill.contract_reverted{background:var(--bad-soft);color:var(--bad)}

/* ---- Benchmark ---- */
.bench h2{margin:26px 0 10px;font-size:18px}
.legend{color:var(--muted);font-size:12.5px;margin-top:6px}
.pairlists{display:flex;gap:16px;flex-wrap:wrap;margin-top:8px}
.pairlists .pl{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;font-size:13px}
.pairlists .pl b{font-weight:600}
.qidchip{font-family:var(--mono);background:#f0efe9;border-radius:4px;padding:0 6px;font-size:12px;cursor:pointer}
details.secgold{margin-top:14px}
details.secgold summary{cursor:pointer;color:var(--accent)}
.interp{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 18px;font-size:14px;max-width:960px;margin-top:12px}
.interp b{font-weight:650}

/* ---- modal ---- */
.modal{position:fixed;inset:0;background:rgba(20,22,26,.45);z-index:80;display:flex;align-items:center;justify-content:center;padding:20px}
.modal .box{background:var(--panel);border-radius:14px;max-width:980px;width:100%;max-height:88vh;overflow:auto;padding:22px 26px;box-shadow:0 12px 40px rgba(0,0,0,.25)}
.modal .box .mhead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}
.modal .box .mhead h3{font-size:16px}
.modal .box .mbody{font-family:var(--serif);font-size:15px;line-height:1.55}
.modal .box .mbody p{margin:8px 0}
.modal .box .mbody ul{margin:8px 0 8px 22px}
.modal .box .mfacts{display:flex;gap:10px;flex-wrap:wrap;font-size:12.5px;color:var(--muted);margin-bottom:10px}
footer{color:var(--muted);font-size:12px;padding:26px 22px;text-align:center}

@media (max-width:1100px){
  .pres-layout,.dbg,.chatwrap{grid-template-columns:1fr}
  .sidecard,.inspector{position:static;max-height:none}
  .docpage{padding:22px 20px}
}
@media (max-width:760px){
  .cmp{grid-template-columns:1fr}
  .cmp .colhead.b{display:none}
  .topbar{padding:8px 12px;gap:8px}
  main{padding:14px 12px 30px}
}
</style>
</head>
<body>
<div class="topbar">
  <span class="brand">AMSC Chunking<small>Viewer v2</small><span class="tag">Chunking + RAG PoC</span></span>
  <select id="docsel" title="Doküman"></select>
  <div class="tabs" id="modetabs">
    <button data-mode="presentation">Sunum<small>ne yaptık, fark ne?</small></button>
    <button data-mode="query">Sorgu<small>kullanınca nasıl çalışıyor?</small></button>
    <button data-mode="debug">Debug<small>neden bu karar?</small></button>
    <button data-mode="benchmark">Benchmark<small>ölçümler ne diyor?</small></button>
  </div>
  <div class="seg" id="armseg"></div>
  <div class="bar-right">
    <span id="pagectl">Sayfa <select id="pagesel"></select></span>
    <span class="seg filterseg" id="filterseg">
      <button data-f="all">Tümü</button>
      <button data-f="diff">Yalnız farklar</button>
      <button data-f="deep">Deep ≠ Standard</button>
    </span>
    <span class="diffnav" id="diffnav">
      <button id="prevdiff">&#8592; Önceki fark</button>
      <button id="nextdiff">Sonraki fark &#8594;</button>
      <span class="diffcount" id="diffcount"></span>
    </span>
    <label class="conttoggle" id="conttoggle" title="Retrieval sonrası birlikte taşınabilecek devam chunk'larını görselleştirir; benchmark sonucunu değiştirmez">
      <input type="checkbox" id="contchk"> Devam zinciri (local expansion)
    </label>
  </div>
  <div class="modehint hidden" id="modehint"></div>
</div>
<main>
  <div id="view-presentation" data-mode="presentation">
    <div id="methods" class="methods"></div>
    <div id="results"></div>
    <div class="readerbar" id="readerbar"></div>
    <div class="pres-layout">
      <div id="prespage"></div>
      <aside class="sidecard" id="presdetail"></aside>
    </div>
  </div>
  <div id="view-query" class="hidden" data-mode="query">
    <div class="subtabs" id="qsubtabs">
      <button data-sub="chat">Dokümana Sor</button>
      <button data-sub="gold">Gold sorgular</button>
    </div>
    <div id="chatview">
      <div id="offline" class="offline hidden"></div>
      <div class="chatwrap">
        <div>
          <div class="chatbox">
            <div class="muted" style="font-size:13px;margin-bottom:6px">Seçili dokümana doğal dilde soru sorun. Cevap yalnız retrieve edilen chunk'lara dayanır; kaynaklar kart olarak gösterilir.</div>
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
      <div style="margin-bottom:14px">Gold sorgu: <select id="querysel" style="max-width:900px"></select></div>
      <div id="queryhead"></div>
      <div class="qcols" id="querycols"></div>
    </div>
  </div>
  <div id="view-debug" class="hidden" data-mode="debug">
    <div class="dbgbar" id="dbgbar"></div>
    <div class="dbg">
      <div id="dbglist"></div>
      <aside class="inspector" id="inspector"></aside>
    </div>
    <div class="secpanel" id="secpanel"></div>
  </div>
  <div id="view-benchmark" class="bench hidden" data-mode="benchmark"></div>
</main>
<footer id="foot"></footer>
<div id="modal" class="modal hidden"></div>
<script id="viewer-data" type="application/json">__VIEWER_DATA__</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("viewer-data").textContent);
const ARMS = DATA.armOrder;
const PRODUCT_ARMS = DATA.productArmOrder || ["markdown","hybrid","structure-only","agentic"];
const ARM_LABEL = DATA.armLabels;

const REASONS = {
  doc_start:   {label:"Doküman başlangıcı", sent:"Bu, dokümanın ilk chunk'ı."},
  new_section: {label:"Yeni bölüm başladı", sent:"Bir önceki chunk'ın bölümü kapandı; bu chunk yeni bir bölüm başlığıyla açılıyor."},
  label_split: {label:"Ara başlıkta bölündü", sent:"Aynı bölümün içinde, okuyucunun zaten duraksadığı bir ara başlıkta kesildi."},
  budget_split:{label:"Token bütçesi doldu", sent:"Bölüm hedef token bütçesini aştığı için bölündü; bölüm başlığı iki parçada da korunuyor."},
  md_size:     {label:"Boyut tabanlı kesim", sent:"Markdown yöntemi bölüm yapısına bakmaz; hedef boyuta ulaşıldığında keser."},
  md_overlap:  {label:"Boyut tabanlı kesim + örtüşme", sent:"Hedef boyuta ulaşıldı; önceki chunk'ın kuyruğu örtüşme (overlap) olarak bu chunk'a taşındı."},
  md_heading:  {label:"Başlık sınırında kesim", sent:"Kesim, markdown ayracının denk geldiği bir başlık sınırında gerçekleşti."}
};
// Continuation connector text, per boundary reason. Shown only when the
// boundary carries a TOKEN_BUDGET_CONTINUATION link (same section, adjacent).
const CONT_LABELS = {
  budget_split: "Önceki chunk'ın devamı — boyut sınırı nedeniyle ayrıldı",
  label_split:  "Önceki chunk'ın devamı — ara başlıkta bölündü",
  md_size:      "Önceki chunk'ın devamı — boyut sınırı nedeniyle ayrıldı",
  md_overlap:   "Önceki chunk'ın devamı — boyut sınırı (kuyruk örtüşme olarak taşındı)",
  md_heading:   "Önceki chunk'ın devamı — başlık sınırında kesildi"
};
const SMELL_TEXT = {
  orphan_label: "yetim başlık/etiket",
  lead_in_cut: "lead-in devamından ayrılmıştı",
  continuation_cut: "devam cümlesi/dipnot ayrılmıştı",
  run_split_when_fits: "sığan liste bölünmüştü",
  fragment_cut: "unit içi zorunlu kesim",
  table_split: "tablo içi zorunlu kesim",
  below_min: "min altı parça",
  above_soft_max: "soft-max üstü parça"
};
const SMELL_FIXED = {
  orphan_label: "yetim başlık önlendi",
  lead_in_cut: "lead-in devamıyla kaldı",
  continuation_cut: "devam cümlesi ayrılmadı",
  run_split_when_fits: "liste bütün kaldı",
  fragment_cut: "unit içi kesim azaldı",
  table_split: "tablo içi kesim azaldı"
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
  "structure-only": {top:"Standard", sub:"Structure-only · hızlı ve deterministic"},
  "hybrid":         {top:"Hybrid", sub:"embedding-assisted · araştırma kolu"},
  "markdown":       {top:"Markdown", sub:"baseline"},
  "agentic":        {top:"Agentic Chunker", sub:"Deep Analysis · yapı + kalite kuralları + LLM"}
};
const LEGACY_AGENTIC_SUB = "Structure + LLM · ayrı koşu";
const METHOD_DESC = {
  markdown: "Metni Markdown düzenine ve sabit token boyutuna göre böler (700 token hedef, 140 token örtüşme). Başlık/bölüm mantığına bakmaz; hızlı bir taban çizgisidir.",
  hybrid: "Bölüm yapısını takip eder; bütçeyi aşan bölümlerde kesim yerini embedding benzerliğiyle seçer (H1 arbitration). Araştırma koludur, ürün modu değildir; bir güven/belirsizlik dedektörü değildir.",
  "structure-only": "Başlık, bölüm ve etiket yapısını deterministic olarak takip eder: her bölüm kendi başlığı altında kalır, yalnız bütçeyi aşan bölümler bölünür. Hızlı, tekrarlanabilir, LLM'siz — ürünün Standard modu.",
  agentic: "Standard'ın üstüne bir kalite sözleşmesi koyar: yetim başlık, ayrılmış lead-in, bölünmüş liste gibi kötü sınırları deterministic kurallarla düzeltir; gerçekten belirsiz sınırlarda LLM'e danışır ve her öneriyi iki sırada doğrulatır. Hiçbir koku türünde Standard'dan kötü olamaz — ürünün Deep Analysis modu, ek gecikme ve maliyetle."
};
const MODE_HINTS = {
  "structure-only": "Standard — Structure-only: hızlı ve deterministic. Ürünün Deep Analysis modu (Agentic Chunker) " +
    "önemli dokümanlarda zor chunk sınırlarını backend'de LLM ile değerlendirir; yalnız ingest sırasında çalışır, " +
    "retrieval'a ve cevaba karışmaz.",
  "hybrid": "Hybrid — embedding-assisted araştırma kolu (ürün modu değildir): bütçeyi aşan bir bölümde kural birden fazla geçerli kesim adayı " +
    "bıraktığında, kesim yeri semantik benzerlikle seçilir (H1 arbitration). Bir güven/belirsizlik dedektörü değildir.",
  "markdown": null,
  "agentic": "Agentic Chunker — Deep Analysis: yapısal yürüyüş aynı; kalite kuralları kötü sınırları taşır, LLM yalnız gerçekten " +
    "belirsiz sınırlarda öneri verir, çift sıralı verifier her öneriyi doğrular; final bölümleme deterministik sözleşmeden geçer. " +
    "Model-bağımlı bir koşudur; kazanan ilan edilmez."
};
const LEGACY_HINT = "Agentic Chunker — Structure + LLM: yapısal kural aday sınırları belirler, generative model her adaya SPLIT/KEEP oyu verir; " +
  "son seçim, fallback ve token limitleri deterministic kuralda kalır. Ayrı ve model-bağımlı bir koşudur; frozen üç kolun benchmark " +
  "karşılaştırmasına dahil değildir, kazanan ilan edilmez.";

const DOC_ORDER = (DATA.docOrder || Object.keys(DATA.docs)).filter(id => DATA.docs[id]);
const state = {
  doc: DOC_ORDER[0],
  mode: "presentation",
  arm: null,
  armB: null,
  compare: false,
  page: null,
  filter: "all",
  diffIdx: -1,
  query: null,
  selChunk: null,
  selUnit: null,
  contShow: false,
  qsub: "chat",
  dbg: {type:"all", role:"all", text:"", onlyBig:false, onlyPf:false, secStatus:"changed"},
  chat: {online:null, health:null, turns:[], busy:false, arm:null}
};

const D = () => DATA.docs[state.doc];
const A = () => D().arms[state.arm];
const $ = id => document.getElementById(id);
const esc = s => String(s === null || s === undefined ? "" : s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const fmt = (v, d) => v === null || v === undefined || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(d === undefined ? 4 : d);
const pct = v => v === null || v === undefined ? "—" : (Number(v) * 100).toFixed(1) + "%";
const hasArm = a => Boolean(D().arms[a]);
const docArms = () => PRODUCT_ARMS.filter(hasArm);
const isDeepArm = a => a === "agentic" && D().arms.agentic && D().arms.agentic.kind === "deep_analysis";
const isLegacyAgentic = () => D().arms.agentic && D().arms.agentic.kind === "agentic_structure_llm";
const deepMeta = () => D().meta.deep || null;
const armLabel = a => ARM_LABEL[a] || (MODE_NAMES[a] && MODE_NAMES[a].top) || a;
const modeName = a => (MODE_NAMES[a] || {top: armLabel(a), sub: ""});

function unitById(id){ return D()._byId[id]; }
function indexDocs(){
  for (const doc of Object.values(DATA.docs)) {
    doc._byId = {};
    doc.units.forEach(u => { doc._byId[u.i] = u; });
    doc._diffKey = new Set(doc.diffs.map(d => d.a + "|" + d.b));
    for (const arm of Object.values(doc.arms)) {
      arm._idx = {};
      arm.chunks.forEach((c, i) => { arm._idx[c.id] = i; });
    }
  }
}
indexDocs();
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
  docsel.innerHTML = DOC_ORDER
    .map(id => `<option value="${id}">${esc(DATA.docs[id].label)}</option>`).join("");
  docsel.value = state.doc;
  docsel.onchange = () => { state.doc = docsel.value; state.page = null;
    state.query = null; state.selChunk = null; state.selUnit = null; state.diffIdx = -1;
    state.arm = defaultArm();
    state.armB = hasArm("structure-only") && state.arm !== "structure-only" ? "structure-only" : (docArms().find(a => a !== state.arm) || state.arm);
    state.chat.turns = []; state.chat.arm = null;
    if (state.filter === "diff" && !D().diffs.length) state.filter = "all";
    render(); };
  $("modetabs").querySelectorAll("button").forEach(b => {
    b.onclick = () => { state.mode = b.dataset.mode; render(); };
  });
  $("contchk").onchange = () => { state.contShow = $("contchk").checked; render(); };
  $("filterseg").querySelectorAll("button").forEach(b => {
    b.onclick = () => { state.filter = b.dataset.f; state.diffIdx = -1; syncPage(); render(); };
  });
  $("prevdiff").onclick = () => stepDiff(-1);
  $("nextdiff").onclick = () => stepDiff(1);
  $("qsubtabs").querySelectorAll("button").forEach(b => {
    b.onclick = () => { state.qsub = b.dataset.sub; render(); };
  });
  $("modal").onclick = e => { if (e.target === $("modal")) closeModal(); };
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });
}

function pageList(){
  if (state.filter === "diff" && D().diffPages.length) return D().diffPages;
  if (state.filter === "deep" && (D().deepDiffPages || []).length) return D().deepDiffPages;
  return D().pages;
}
function firstContentPage(){
  // Open on the first page that carries a content unit, not a cover heading.
  const unit = D().units.find(u => u.t !== "heading");
  return unit ? unit.p : D().pages[0];
}
function syncPage(){
  const pages = pageList();
  if (state.page === null && state.filter === "all") state.page = firstContentPage();
  if (!pages.includes(state.page)) state.page = pages[0];
}
function stepDiff(delta){
  const diffs = D().diffs;
  if (!diffs.length) return;
  state.diffIdx = (state.diffIdx + delta + diffs.length) % diffs.length;
  const point = diffs[state.diffIdx];
  state.filter = "diff";
  state.page = point.p;
  state.mode = "presentation";
  render();
  const el = document.querySelector(`[data-diff="${point.a}|${point.b}"]`);
  if (el) { el.scrollIntoView({block:"center"}); el.style.boxShadow = "0 0 0 3px #f2d9a4"; }
}

function renderArmSeg(){
  const seg = $("armseg");
  const arms = docArms();
  if (state.mode === "presentation") {
    seg.innerHTML = arms.map(a => {
      const naming = modeName(a);
      const sub = a === "agentic" && isLegacyAgentic() ? LEGACY_AGENTIC_SUB : naming.sub;
      return `<button data-arm="${a}" class="${isDeepArm(a) ? "deep" : ""}">${esc(naming.top)}<small>${esc(sub)}</small></button>`;
    }).join("");
  } else {
    seg.innerHTML = arms.map(a => `<button data-arm="${a}" class="${isDeepArm(a) ? "deep" : ""}">${esc(armLabel(a))}</button>`).join("");
  }
  seg.querySelectorAll("button").forEach(b => {
    b.onclick = () => { state.arm = b.dataset.arm; state.selChunk = null;
      if (state.armB === state.arm) state.armB = docArms().find(a => a !== state.arm) || state.arm; render(); };
  });
}

function syncBar(){
  $("modetabs").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.mode === state.mode));
  renderArmSeg();
  $("armseg").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.arm === state.arm));
  $("filterseg").querySelectorAll("button").forEach(b => {
    b.classList.toggle("on", b.dataset.f === state.filter);
    if (b.dataset.f === "diff") b.classList.toggle("hidden", !D().diffs.length);
    if (b.dataset.f === "deep") b.classList.toggle("hidden", !(D().deepDiffPages || []).length);
  });
  const inPage = state.mode === "presentation" || state.mode === "debug";
  $("pagectl").style.display = inPage ? "" : "none";
  $("armseg").style.display = (state.mode === "benchmark" || state.mode === "query") ? "none" : "";
  $("filterseg").style.display = state.mode === "presentation" ? "" : "none";
  $("diffnav").style.display = state.mode === "presentation" && D().diffs.length ? "" : "none";
  $("conttoggle").style.display = state.mode === "presentation" ? "" : "none";
  $("contchk").checked = state.contShow;
  let hint = state.mode === "presentation" ? MODE_HINTS[state.arm] : null;
  if (state.mode === "presentation" && state.arm === "agentic" && isLegacyAgentic()) hint = LEGACY_HINT;
  $("modehint").textContent = hint || "";
  $("modehint").classList.toggle("hidden", !hint);
  if (inPage) {
    syncPage();
    const sel = $("pagesel");
    sel.innerHTML = pageList().map(p => `<option value="${p}">${p}</option>`).join("");
    sel.value = state.page;
    sel.onchange = () => { state.page = Number(sel.value); render(); };
  }
  const diffs = D().diffs;
  $("diffcount").textContent = diffs.length
    ? (state.diffIdx >= 0 ? (state.diffIdx + 1) + " / " : "") + diffs.length + " fark noktası" : "fark yok";
  $("prevdiff").disabled = $("nextdiff").disabled = !diffs.length;
}

/* -------- Sunum: methods + results -------- */
function renderMethods(){
  const doc = D();
  $("methods").innerHTML = PRODUCT_ARMS.map(a => {
    const arm = doc.arms[a];
    const naming = modeName(a);
    const badge = a === "structure-only" ? `<span class="pill std">Standard</span>` :
      (a === "agentic" ? (isDeepArm(a) ? `<span class="pill deep">Deep Analysis</span>` : `<span class="pill grey">araştırma koşusu</span>`) :
      (a === "hybrid" ? `<span class="pill grey">araştırma kolu</span>` : `<span class="pill grey">baseline</span>`));
    const facts = arm ? [`${arm.chunks.length} chunk`, arm.sq && arm.sq.token_count ? `medyan ${fmt(arm.sq.token_count.median, 0)} token` : "",
      a === "agentic" && deepMeta() ? `${deepMeta().calls.total} LLM çağrısı` : (a === "structure-only" || a === "markdown" ? "LLM yok" : "")].filter(Boolean) : ["bu dokümanda yok"];
    const desc = a === "agentic" && isLegacyAgentic() ? "Yapısal adaylar section başına tek çağrıda oylanır; final seçim ve limitler deterministic kuralda kalır. " + LEGACY_AGENTIC_SUB + "." : METHOD_DESC[a];
    return `<div class="method ${arm ? "" : "absent"} ${state.arm === a ? "on" : ""} ${a === "agentic" ? "deepm" : ""}" data-arm="${a}">
      <div class="name">${esc(naming.top)} ${badge}</div>
      <div class="desc">${esc(desc)}</div>
      <div class="facts">${facts.map(f => `<span>${esc(f)}</span>`).join("")}</div>
    </div>`;
  }).join("");
  $("methods").querySelectorAll(".method:not(.absent)").forEach(el => {
    el.onclick = () => { state.arm = el.dataset.arm; state.selChunk = null;
      if (state.armB === state.arm) state.armB = docArms().find(a => a !== state.arm) || state.arm; render(); };
  });
}

function smellSum(t){ return ["orphan_label","lead_in_cut","continuation_cut","run_split_when_fits","fragment_cut","table_split"].reduce((s, k) => s + (t && t[k] || 0), 0); }

function renderResults(){
  const dm = deepMeta();
  const box = $("results");
  if (!dm) {
    if (isLegacyAgentic()) {
      const am = D().agenticMeta || {}, bd = am.diff || {}, s = am.summary || {};
      box.innerHTML = `<div class="results"><div class="title"><span class="pill grey">Agentic Chunker — ayrı koşu</span> <span class="muted" style="font-weight:400;font-size:13px">model: ${esc(am.model || "—")} · mod: ${esc(am.mode || "—")} · kazanan ilan edilmez</span></div>
        <div class="grid">
          <div class="item"><div class="v">${bd.decision_windows ?? s.decision_window_count ?? "—"}</div><div class="k">karar penceresi</div></div>
          <div class="item"><div class="v">${bd.final_boundary_moved ?? s.final_boundary_moved_count ?? "—"}</div><div class="k">final sınırı taşınan</div></div>
          <div class="item"><div class="v">${s.provider_call_count ?? "—"}</div><div class="k">provider çağrısı</div></div>
        </div></div>`;
    } else box.innerHTML = "";
    return;
  }
  const ts = dm.totals.standard || {}, td = dm.totals.deep || {};
  const sc = dm.storyCounts || {};
  const origin = sc.final_boundaries_by_origin || {};
  const secs = (dm.timing.llm_calls || 0) + (dm.timing.verifier_calls || 0) + (dm.timing.selection || 0) + (dm.timing.standard || 0);
  const smellKeys = ["orphan_label","lead_in_cut","continuation_cut","run_split_when_fits","table_split","fragment_cut"].filter(k => (ts[k] || 0) + (td[k] || 0) > 0);
  const maxS = Math.max(1, ...smellKeys.map(k => ts[k] || 0));
  const retr = dm.retrieval || {};
  let retrLine = "";
  if (retr.deep && retr.standard) {
    retrLine = `<div class="item"><div class="v">${fmt(retr.standard.hit_at_5, 3)}<span class="arrow">→</span><span class="to">${fmt(retr.deep.hit_at_5, 3)}</span></div><div class="k">Hit@5 (BM25, aynı gold set)</div></div>`;
  }
  box.innerHTML = `<div class="results">
    <div class="title"><span class="pill std">Standard</span><span class="muted" style="font-weight:400">→</span><span class="pill deep">Deep Analysis</span>
      <span class="muted" style="font-weight:400;font-size:13px">${esc(D().label)} · ${Math.max(...D().pages)} sayfa · ${D().meta.unitCount} canonical unit · model ${esc(dm.model || "—")}${dm.status && dm.status !== "ok" ? " · durum: " + esc(dm.status) : ""}</span></div>
    <div class="grid">
      <div class="item"><div class="v">${dm.chunkCount.standard}<span class="arrow">→</span><span class="to">${dm.chunkCount.deep}</span></div><div class="k">chunk sayısı</div></div>
      <div class="item"><div class="v">${dm.smellTotal.standard}<span class="arrow">→</span><span class="to">${dm.smellTotal.deep}</span></div><div class="k">yapısal kusur (koku) toplamı</div></div>
      <div class="item"><div class="v" style="color:var(--good)">${dm.regressions}</div><div class="k">Standard'a göre kötüleşen bölüm</div></div>
      <div class="item"><div class="v">${(origin.deterministic || 0)}<span class="muted" style="font-size:13px;font-weight:500"> kural</span> + <span class="to">${origin.llm || 0}</span><span class="muted" style="font-size:13px;font-weight:500"> LLM</span></div><div class="k">taşınan/eklenen final sınır</div></div>
      <div class="item"><div class="v">${dm.calls.total}</div><div class="k">LLM çağrısı (${dm.calls.proposer} öneri + ${dm.calls.verifier} doğrulama)</div></div>
      <div class="item"><div class="v">${secs ? secs.toFixed(0) + " s" : "—"}</div><div class="k">Deep süresi${dm.timing.standard ? " (Standard: " + fmt(dm.timing.standard, 2) + " s)" : " (ingest, tek sefer)"}</div></div>
      ${retrLine}
    </div>
    <div class="smellbars">${smellKeys.map(k => `<div class="smellbar"><span>${esc(SMELL_TEXT[k] || k)}</span><span class="bar"><i style="width:${Math.round((ts[k] || 0) / maxS * 100)}%"></i><b style="width:${Math.round((td[k] || 0) / maxS * 100)}%"></b></span><span class="n">${ts[k] || 0} → <span style="color:var(--deep);font-weight:600">${td[k] || 0}</span></span></div>`).join("")}</div>
    <div class="note" style="margin-top:8px">Koku = şekle bakan deterministik kusur sayacı (yetim başlık, ayrılmış lead-in, bölünmüş liste, unit içi zorunlu kesim). Deep, hiçbir koku türünde Standard'dan kötü olamaz; kalan kokuların tamamı tek bir unit'in içine zorunlu kesimler (temsil tavanı). ${retr.deep && retr.standard ? `Retrieval farkı ${D().meta.queryCount} gold soruda gürültü içindedir; kazanan ilan edilmez.` : "Bu doküman için gold sorgu seti yok; retrieval karşılaştırması yapılmadı, uydurulmadı."}</div>
  </div>`;
}

/* -------- Sunum: reader -------- */
function pageUnits(page){ return D().units.filter(u => u.p === page); }

function boundaryPositions(units, arm){
  // Boundary sits before the first unit of a new chunk; consecutive unmapped
  // units (headings the arm keeps out of unit_ids) attach to the chunk below.
  const m = D().arms[arm].m;
  const marks = new Array(units.length).fill(null);
  let previous;
  for (let k = 0; k < units.length; k++) {
    const at = m[units[k].i];
    if (at === undefined) continue;
    if (at !== previous) {
      let pos = k;
      while (pos > 0 && m[units[pos - 1].i] === undefined) pos--;
      marks[pos] = at;
      previous = at;
    }
  }
  return marks;
}

function decisionPill(chunk, arm){
  // Human-language status of a Deep boundary (or of a Standard boundary Deep changed).
  const d = chunk.dec;
  if (!d) return "";
  if (arm === "structure-only" && d.status === "std_changed") {
    const why = (d.removed_smells || []).map(s => SMELL_FIXED[s] || s).join(", ");
    return `<span class="decpill std" title="Deep Analysis bu kesimi kaldırdı ya da taşıdı">Deep ${d.origin === "llm" ? "(LLM)" : "(kural)"} bu kesimi ${why ? "değiştirdi: " + esc(why) : "değiştirdi"}</span>`;
  }
  if (arm !== "agentic") return "";
  if (d.status === "ceiling") return `<span class="decpill ceil">zorunlu kesim — tek unit hard cap'i aşıyor</span>`;
  if (d.status === "det_moved") {
    const why = (d.removed_smells || []).map(s => SMELL_FIXED[s] || s);
    if (!why.length && d.size_effect && d.size_effect.below_min && d.size_effect.below_min.final < d.size_effect.below_min.standard) why.push("küçük parça birleştirildi");
    return `<span class="decpill det">kalite kuralı sınırı taşıdı${why.length ? ": " + esc(why.join(", ")) : ""}</span>` +
      (d.llm_reverted ? `<span class="decpill rev">LLM farklı bir sınır önerdi; verifier reddetti</span>` : "");
  }
  if (d.status === "llm_accepted") return `<span class="decpill llm">LLM önerisi doğrulandı ve kabul edildi</span>`;
  if (d.status === "kept") return d.llm_reverted
    ? `<span class="decpill rev">LLM farklı sınır önerdi; verifier reddetti → yapısal sınır korundu</span>`
    : `<span class="decpill kept">yapısal sınır korundu</span>`;
  return "";
}
function mergePill(chunk, arm){
  if (arm !== "agentic" || !chunk.mg || !chunk.mg.length) return "";
  return chunk.mg.map(m => {
    const why = (m.removed_smells || []).map(s => SMELL_FIXED[s] || s);
    if (!why.length && m.size_effect && m.size_effect.below_min && m.size_effect.below_min.final < m.size_effect.below_min.standard) why.push("min altı parça birleştirildi");
    return `<span class="decpill ${m.status === "llm_merged" ? "llm" : "det"}">Standard'ın kesimi kaldırıldı${why.length ? ": " + esc(why.join(", ")) : ""}</span>`;
  }).join("");
}

function chunkLine(arm, idx, compact, unitId){
  const armData = D().arms[arm];
  const chunk = armData.chunks[idx];
  const isCont = chunk.cp !== null && chunk.cp !== undefined;
  const why = isCont ? (CONT_LABELS[chunk.rs] || "Önceki chunk'ın devamı") : (REASONS[chunk.rs] || {label: chunk.rs}).label;
  const kindText = isCont ? "· · · teknik sınır — içerik devam ediyor · · ·" : "yeni bölüm";
  let out = `<div class="chunkline ${isCont ? "tech" : "struct"}">` +
    (compact ? "" : `<span class="kind">${kindText}</span>`) +
    `<span class="chunkpill ${state.selChunk === idx && state.arm === arm ? "sel" : ""}" data-chunk="${idx}" data-arm="${arm}">` +
    `Chunk ${chunk.num} · ${chunk.n} token · <span class="why">${esc(why)}</span>` +
    (state.contShow && chunk.rt === "TOKEN_BUDGET_CONTINUATION" ? " ⟡" : "") + `</span>` +
    decisionPill(chunk, arm) + mergePill(chunk, arm) +
    (chunk.llm ? `<span class="decpill ${chunk.llm.m ? "llm" : "kept"}">${chunk.llm.m ? "sınır LLM oyu ile taşındı" : "pencere değerlendirildi; açgözlü kesim korundu"}</span>` : "") +
    `<span class="rule"></span>`;
  const d = D().diffs.length ? D().diffs.find(x => x.b === unitId) : null;
  if (!compact && state.filter === "diff" && d && D()._diffKey.has(d.a + "|" + d.b)) {
    const glyphs = ARMS.map(a => ARM_LABEL[a][0] + ":" + (d.s[a] ? "✂" : "—")).join(" ");
    out += `<span class="diffbadge" data-diff="${d.a}|${d.b}">FARK<span class="glyphs">${glyphs}</span></span>`;
  }
  return out + `</div>`;
}

function renderReaderBar(){
  const arms = docArms();
  const opts = a => arms.map(x => `<option value="${x}" ${x === a ? "selected" : ""}>${esc(modeName(x).top)}</option>`).join("");
  $("readerbar").innerHTML = `<span>Sayfa okuyucu —</span>
    <label><input type="checkbox" id="cmpchk" ${state.compare ? "checked" : ""}> Karşılaştır</label>
    ${state.compare ? `<span>sol: <select id="armA">${opts(state.arm)}</select></span><span>sağ: <select id="armB">${opts(state.armB)}</select></span>` : `<span>gösterilen: <b>${esc(modeName(state.arm).top)}</b></span>`}
    <span class="muted">· şeritler chunk sınırlarını, renk tonları chunk üyeliğini gösterir; bir şeride ya da metne tıklayın</span>`;
  $("cmpchk").onchange = () => { state.compare = $("cmpchk").checked; render(); };
  if (state.compare) {
    $("armA").onchange = () => { state.arm = $("armA").value; state.selChunk = null; render(); };
    $("armB").onchange = () => { state.armB = $("armB").value; render(); };
  }
}

function renderPresentation(){
  renderMethods();
  renderResults();
  renderReaderBar();
  const units = pageUnits(state.page);
  if (state.compare && state.armB && state.armB !== state.arm && hasArm(state.armB)) { renderCompare(units); return; }
  const arm = state.arm, armData = A();
  const marks = boundaryPositions(units, arm);
  const m = armData.m;
  const expansion = state.contShow && state.selChunk !== null ? simulateExpansion(armData, state.selChunk) : null;
  const expMembers = expansion ? new Set(expansion.members) : null;

  let htmlOut = `<div class="docpage"><div class="pagehead"><span>${esc(D().label)} — sayfa ${state.page}</span><span>${esc(modeName(arm).top)} · ${esc(armLabel(arm))}</span></div>`;
  for (let k = 0; k < units.length; k++) {
    const u = units[k];
    if (marks[k] !== null) htmlOut += chunkLine(arm, marks[k], false, u.i);
    const at = m[u.i];
    let cls = at === undefined ? "" : (at % 2 === 0 ? "tintA" : "tintB");
    if (at !== undefined && state.contShow) {
      const chunk = armData.chunks[at];
      if (expMembers && expMembers.has(at)) cls += " expmember";
      else if (chunk.g !== null && chunk.g !== undefined) cls += " contedge";
    }
    if (at !== undefined && state.selChunk === at) cls += " selchunk";
    htmlOut += `<div class="u ${cls}" data-uid="${u.i}"${at !== undefined ? ` data-uchunk="${at}"` : ""}>` + unitHtml(u) + `</div>`;
  }
  htmlOut += "</div>";
  $("prespage").innerHTML = htmlOut;
  bindReader($("prespage"));
  renderPresDetail();
}

function renderCompare(units){
  const a = state.arm, b = state.armB;
  const marksA = boundaryPositions(units, a), marksB = boundaryPositions(units, b);
  const mA = D().arms[a].m, mB = D().arms[b].m;
  let out = `<div class="cmp"><div class="colhead a">${esc(modeName(a).top)} <span class="muted" style="font-weight:400;font-size:12.5px">${esc(armLabel(a))} · ${D().arms[a].chunks.length} chunk</span></div><div class="colhead b">${esc(modeName(b).top)} <span class="muted" style="font-weight:400;font-size:12.5px">${esc(armLabel(b))} · ${D().arms[b].chunks.length} chunk</span></div>`;
  for (let k = 0; k < units.length; k++) {
    const u = units[k];
    const cell = (arm, marks, m) => {
      const at = m[u.i];
      let cls = at === undefined ? "" : (at % 2 === 0 ? "tintA" : "tintB");
      if (at !== undefined && state.arm === arm && state.selChunk === at) cls += " selchunk";
      return `<div class="cell">${marks[k] !== null ? chunkLine(arm, marks[k], true, u.i) : ""}<div class="u ${cls}" data-uid="${u.i}" data-arm="${arm}"${at !== undefined ? ` data-uchunk="${at}"` : ""}>${unitHtml(u)}</div></div>`;
    };
    out += cell(a, marksA, mA) + cell(b, marksB, mB);
  }
  $("prespage").innerHTML = out + "</div>";
  bindReader($("prespage"));
  renderPresDetail();
}

function bindReader(root){
  root.querySelectorAll(".chunkpill").forEach(el => {
    el.onclick = () => { state.arm = el.dataset.arm || state.arm; state.selChunk = Number(el.dataset.chunk); render(); };
  });
  root.querySelectorAll(".u[data-uchunk]").forEach(el => {
    el.onclick = () => { if (el.dataset.arm) state.arm = el.dataset.arm; state.selChunk = Number(el.dataset.uchunk); render(); };
  });
}

function expansionBudget(){ const budgets = D().meta.budgets || {}; return budgets.hard_max_tokens || 1126; }
// Mirror of amsc.chunk_relations.expand_context: nearest-first, previous
// before next, hard budget, stop at any missing link (a real section
// boundary). Visualization only -- retrieval ranks are untouched.
function simulateExpansion(armData, seedIdx, budget){
  budget = budget === undefined ? expansionBudget() : budget;
  const chunks = armData.chunks;
  if (!chunks[seedIdx]) return null;
  let total = chunks[seedIdx].n;
  const members = [seedIdx];
  let before = seedIdx, after = seedIdx, beforeOpen = true, afterOpen = true;
  while (beforeOpen || afterOpen) {
    let moved = false;
    if (beforeOpen) {
      const prev = chunks[before].rt === "TOKEN_BUDGET_CONTINUATION" ? chunks[before].cp : null;
      if (prev === null || prev === undefined) beforeOpen = false;
      else if (total + chunks[prev].n > budget) beforeOpen = false;
      else { members.push(prev); total += chunks[prev].n; before = prev; moved = true; }
    }
    if (afterOpen) {
      const nextRaw = chunks[after].cn;
      const next = (nextRaw !== null && nextRaw !== undefined && chunks[nextRaw].rt === "TOKEN_BUDGET_CONTINUATION") ? nextRaw : null;
      if (next === null) afterOpen = false;
      else if (total + chunks[next].n > budget) afterOpen = false;
      else { members.push(next); total += chunks[next].n; after = next; moved = true; }
    }
    if (!moved) break;
  }
  members.sort((x, y) => x - y);
  return {members, total, budget};
}

function jumpToChunk(idx, arm){
  if (arm) state.arm = arm;
  const chunk = D().arms[state.arm].chunks[idx];
  state.selChunk = idx;
  state.mode = "presentation";
  if (chunk.pg.length && chunk.pg[0] !== state.page) { state.filter = "all"; state.page = chunk.pg[0]; }
  render();
  const el = document.querySelector(`.chunkpill.sel`);
  if (el) el.scrollIntoView({block:"center"});
}

function sectionStory(si){
  const story = D().story;
  if (!story || si === null || si === undefined) return null;
  return story.sections.find(s => s.i === si) || null;
}

function armNoteFor(arm){
  const diag = D().meta.diag[arm] || {};
  if (arm === "hybrid") return `Hybrid kolu: büyük bölümlerin iç kesim noktaları semantik skorla seçilir. Bu koşuda ${diag.arbitrated_boundary_count ?? "?"} bölüm-içi kesimin ${diag.arbitration_changed_boundary_count ?? "?"} tanesi açgözlü kesimden farklı seçildi; ${diag.h1_fallback_section_count ?? "?"} bölümde uygun aday yoktu. Chunk başına hangi kesimin semantik seçim olduğu artifact'te kayıtlı değildir ve burada iddia edilmez.`;
  if (arm === "markdown") return `Markdown kolu bölüm yapısına bakmaz: ${diag.chunk_size_tokens ?? 700} token hedefi, ${diag.chunk_overlap_tokens ?? 140} token örtüşme.`;
  if (arm === "agentic" && isLegacyAgentic()) {
    const am = D().agenticMeta || {}, s = am.summary || {}, bd = am.diff || {};
    return `Agentic Chunker: yapısal adaylar section başına tek çağrıda oylanır; bu koşuda ${bd.decision_windows ?? s.decision_window_count ?? "?"} karar penceresinin ${bd.window_moved ?? s.window_moved_count ?? "?"} tanesinde LLM oyu greedy'den farklı kesim seçti; final chunk sınırı olarak kalan: ${bd.final_boundary_moved ?? s.final_boundary_moved_count ?? "?"} (rejoin ile geri birleşen: ${bd.rejoined_after_agentic_cut ?? s.rejoined_after_agentic_cut_count ?? 0})${am.model ? " (model: " + am.model + ")" : ""}. Ayrı, model-bağımlı bir koşudur; kazanan iddiası yoktur.`;
  }
  if (arm === "agentic") {
    const dm = deepMeta() || {}, sc = dm.storyCounts || {};
    return `Deep Analysis: ${sc.sections ?? "?"} bölümün ${sc.deterministic_improved ?? "?"} tanesinde kalite kuralı sınırı taşıdı, ${sc.llm_accepted ?? "?"} tanesinde LLM önerisi verifier'dan geçti, ${sc.llm_reverted ?? "?"} tanesinde reddedildi; ${sc.contract_reverted ?? 0} bölümde kalite kontrolü değişikliği geri aldı. LLM ${sc.llm_consulted_sections ?? "?"} bölüme danışıldı. Model: ${dm.model || "—"}.`;
  }
  return "Structure-only kolu her bölümü kendi başlığı altında tutar; yalnız hedef bütçeyi aşan bölümler bölünür.";
}

function renderPresDetail(){
  const box = $("presdetail");
  const armData = A();
  const armNote = armNoteFor(state.arm);
  if (state.selChunk === null || !armData.chunks[state.selChunk]) {
    box.innerHTML = `<h3>Chunk detayı</h3><div class="empty">Bir chunk şeridine ya da metnine tıklayın.</div><div class="arminfo">${esc(armNote)}</div>`;
    return;
  }
  const chunk = armData.chunks[state.selChunk];
  const reason = REASONS[chunk.rs] || {label: chunk.rs, sent: ""};
  const prev = chunk.cp, next = chunk.cn;
  const hasLink = (prev !== null && prev !== undefined) || (next !== null && next !== undefined);
  const link = idx => `<button data-jump="${idx}">Chunk ${armData.chunks[idx].num}</button>`;
  const inType = chunk.rt;
  const outType = (next !== null && next !== undefined) ? armData.chunks[next].rt : null;
  const budgetNeighbor = (inType === "TOKEN_BUDGET_CONTINUATION") || (outType === "TOKEN_BUDGET_CONTINUATION");
  const expansion = simulateExpansion(armData, state.selChunk);
  const expandable = expansion && expansion.members.length > 1;
  let expLine;
  if (expandable) expLine = `evet — ${expansion.members.map(i => "Chunk " + armData.chunks[i].num).join(" + ")} · ${expansion.total} token ≤ bütçe ${expansion.budget}`;
  else if (budgetNeighbor) expLine = `hayır — komşu devam chunk'ı bütçeye (${expansionBudget()}) sığmıyor`;
  else if (hasLink) expLine = `hayır — komşu sınır token-budget değil (${inType || outType})`;
  else expLine = "hayır — devam bağlantısı yok (bölüm sınırı)";

  let deepBlock = "";
  const d = chunk.dec;
  if (state.arm === "agentic" && isDeepArm("agentic")) {
    const st = sectionStory(chunk.si);
    let sent = "";
    if (d) {
      if (d.status === "kept") sent = d.llm_reverted ? `Bu sınır Standard'ın sınırıyla aynı. LLM burada farklı bir sınır önerdi, ancak çift sıralı doğrulama öneriyi <b>reddetti</b> (${esc(d.llm_reverted === "order_dependent" ? "sıraya bağlı cevap — pozisyon yanlılığı" : d.llm_reverted === "base_preferred" ? "model deterministik bölümlemeyi tercih etti" : d.llm_reverted)}); deterministik sınır korundu.` : "Bu sınır Standard'ın sınırıyla aynı: kalite kuralı ve LLM değişiklik gerektiren bir şey bulmadı.";
      else if (d.status === "det_moved") sent = `Kalite sözleşmesi bu sınırı taşıdı${(d.removed_smells || []).length ? ": Standard'ın kesimi <b>" + esc((d.removed_smells || []).map(s => SMELL_TEXT[s] || s).join(", ")) + "</b> üretiyordu; yeni kesim bu kusuru taşımıyor" : " (boyut dengesi: min altı parça azaldı)"}. LLM'siz, deterministik karar.` + (d.llm_reverted ? " LLM bu bölgede başka bir sınır önerdi; verifier reddetti." : "");
      else if (d.status === "llm_accepted") sent = "Bu sınırı LLM önerdi. Öneri, değişim grubu iki sunum sırasında da tercih edilince kabul edildi; sonra deterministik sözleşmeden yeniden geçti (hard cap, coverage, koku vektörü).";
      else if (d.status === "ceiling") sent = "Zorunlu kesim: bu chunk tek bir canonical unit'in (tablo/paragraf) içinden başlıyor, çünkü unit hard cap'ten büyük. Hiçbir bölümleme bu kesimi kaldıramaz — temsil tavanı (parser/canonical).";
    }
    deepBlock = `<div class="reason-sent deep"><b>Deep Analysis kararı.</b> ${sent || "Bu chunk bölüm başlangıcında; kesim kararı bölüm sınırının kendisi."}</div>` +
      (st ? `<details class="adv"><summary>Teknik detay — bölüm ${st.i}: ${esc(SECTION_STATUS[st.st] || st.st)}</summary><pre>${esc(JSON.stringify({
        section: st.h, status: st.st, llm_consulted: st.cons, reverted: st.rv, verdict_tiered: st.vt,
        standard_cuts_after: st.std, deterministic_cuts_after: st.det, final_cuts_after: st.fin,
        smells_standard: st.sm.standard, smells_deep: st.sm.deep,
        change_groups: st.gr, llm_proposals: st.pr, this_boundary: d || null
      }, null, 1))}</pre></details>`: "");
  } else if (state.arm === "structure-only" && d && d.status === "std_changed") {
    deepBlock = `<div class="reason-sent deep"><b>Deep Analysis bu kesimi değiştirdi.</b> ${(d.removed_smells || []).length ? "Standard'ın bu kesimi <b>" + esc((d.removed_smells || []).map(s => SMELL_TEXT[s] || s).join(", ")) + "</b> üretiyordu." : "Boyut dengesi için taşındı/birleştirildi."} Karar ${d.origin === "llm" ? "LLM önerisi + verifier onayıyla" : "deterministik kalite kuralıyla"} verildi. Agentic Chunker kolunda aynı sayfayı açarak yeni sınırı görebilirsiniz.</div>`;
  }

  box.innerHTML = `<h3>Chunk ${chunk.num} <span class="muted" style="font-weight:400;font-size:12.5px">· ${esc(modeName(state.arm).top)}</span></h3>
    <dl class="kv">
      <dt>Token</dt><dd>${chunk.n}</dd>
      <dt>Başlık</dt><dd>${chunk.hh ? chunk.hh : "<span class='empty'>—</span>"}</dd>
      <dt>Bölüm</dt><dd>${chunk.sd.length ? esc(chunk.sd.join(" › ")) : "<span class='empty'>—</span>"}</dd>
      <dt>Sayfalar</dt><dd>${chunk.pg.join(", ")}</dd>
      <dt>Önceki</dt><dd class="detail-links">${prev !== null && prev !== undefined ? link(prev) + " (devamı bu chunk)" : "<span class='empty'>—</span>"}</dd>
      <dt>Sonraki</dt><dd class="detail-links">${next !== null && next !== undefined ? link(next) + " (bu chunk'ın devamı)" : "<span class='empty'>—</span>"}</dd>
      <dt>İlişki</dt><dd>${inType ? esc(inType) : (outType ? esc(outType) + " (sonrakiyle)" : "<span class='empty'>—</span>")}</dd>
      <dt>Sınır nedeni</dt><dd>${esc(reason.label)}</dd>
      ${chunk.llm ? `<dt>LLM kararı</dt><dd>${chunk.llm.m ? "sınır LLM oyu ile taşındı" + (chunk.llm.rc ? " (" + esc(chunk.llm.rc) + ")" : "") : "pencere değerlendirildi; açgözlü kesim korundu"}</dd>` : ""}
      <dt>Expansion adayı</dt><dd>${esc(expLine)}</dd>
    </dl>
    <div class="reason-sent"><b>${esc(reason.label)}.</b> ${esc(reason.sent || "")}</div>
    ${deepBlock}
    <div class="detail-links" style="margin-top:10px"><button data-showchunk="1">Chunk metnini aç</button></div>
    <div class="arminfo">${esc(armNote)}</div>`;
  box.querySelectorAll("button[data-jump]").forEach(b => { b.onclick = () => jumpToChunk(Number(b.dataset.jump)); });
  const show = box.querySelector("button[data-showchunk]");
  if (show) show.onclick = () => openChunkModal(state.arm, state.selChunk);
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
  let out = `<div class="rchunk"><div class="rhead">Chunk ${chunk.num} · ${chunk.n} token · sayfa ${chunk.pg.join(", ")}</div>`;
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
  openModal(`Chunk ${chunk.num} · ${esc(modeName(arm).top)}`,
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
  $("chatside").innerHTML = `<h3>Bu sohbet nasıl çalışır</h3>
    <div class="muted" style="font-size:12.5px;line-height:1.5">PDF → seçilen chunking yöntemi → chunks → embedding → dense + BM25 (RRF) → aynı bölümün devam parçalarıyla bağlam → cevap modeli → kaynaklı cevap. Chunking ingest'te bitti; sohbet sırasında proposer/verifier çalışmaz.</div>
    <dl class="kv" style="margin-top:10px">
      <dt>Embedding</dt><dd>${h ? esc(h.embedding_model || "yok (BM25)") : "—"}</dd>
      <dt>Cevap modeli</dt><dd>${h ? esc(h.answer_model || "yok") : "—"}</dd>
      <dt>Retrieval</dt><dd>${h ? (h.dense ? "dense + BM25, RRF" : "BM25") + ` · top-k ${h.retrieval && h.retrieval.top_k}` : "—"}</dd>
      <dt>Bağlam</dt><dd>${h && h.context ? `${h.context.max_context_tokens} token bütçe · devam genişletme ${h.context.expansion_enabled ? "açık" : "kapalı"}` : "—"}</dd>
      <dt>Yöntem</dt><dd>${esc(modeName(state.chat.arm).top)}${state.chat.arm === "agentic" && dm ? ` · ${dm.chunkCount.deep} chunk` : ""}</dd>
    </dl>
    <div class="muted" style="font-size:12px;margin-top:10px">Aynı retrieval hattı bütün yöntemlerde kullanılır; karşılaştırma yalnız chunker'ı değiştirir. Cevap yalnız kaynaklara dayanır; kaynak yetersizse model bunu söyler.</div>`;
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
  $("offline").classList.toggle("hidden", online);
  if (!online) {
    $("offline").innerHTML = `<b>Canlı sohbet için sunucu gerekli.</b> Bu dosya tek başına Sunum, Debug, Benchmark ve gold sorgu görünümünü çalıştırır; "Dokümana Sor" için viewer'ı yerel sunucudan açın:<br>
      <code>py -3.11 -m amsc.viewer_server --viewer artifacts/viewer-v2/index.html --config configs/rag-poc.yaml</code> → <code>http://127.0.0.1:8765/</code><br>
      <span class="muted">Sunucu embedding ve cevap modelini yapılandırmadan okur; anahtar tarayıcıya hiç gelmez.</span>`;
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
    <div class="facts"><span>sayfa ${(s.pages || []).join(", ") || "—"}</span><span>${s.token_count} token</span><span>${esc(s.arm_label || armLabel(s.arm))}</span></div>
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
    <div class="qmeta">${g.id} · kanıt türü: ${esc(g.ty || "—")} · zorluk: ${esc(g.df || "—")} · kanıt sayfaları: ${g.pg.join(", ")}</div>
    <div class="evbox"><div class="evlabel">Gold kanıt (${g.ev.length} unit)</div>${evHtml}</div></div>`;
  $("querycols").innerHTML = qArms.map(arm => {
    const qres = D().arms[arm].q[g.id];
    if (!qres) return `<div class="qcol"><div class="armname">${esc(armLabel(arm))}</div><div class="covline">sonuç yok</div></div>`;
    const st = statusOf(qres.f);
    const relevant = qres.res.find(r => r.r === qres.f && r.m.length);
    const body = (relevant && relevant.c !== null) ? renderedChunk(relevant.c, arm, g.ev) : `<div class="rchunk"><div class="rhead">Top-5 içinde gold kanıt taşıyan chunk yok.</div></div>`;
    const rows = qres.res.map(r => {
      const chunk = r.c === null ? null : D().arms[arm].chunks[r.c];
      return `<div class="row"><span class="rk">#${r.r}</span><span>${chunk ? "Chunk " + chunk.num : "—"}</span><span>s.${r.pg.join(",")}</span><span>${r.tk} tok</span>${r.m.length ? `<span class="mt">✓ ${r.m.length} kanıt unit</span>` : ""}</div>`;
    }).join("");
    return `<div class="qcol"><div class="armname">${esc(armLabel(arm))} <span class="pill ${st.cls}">${st.glyph} ${st.text}</span></div>
      <div class="covline">kanıt kapsaması: ${qres.cov === null || qres.cov === undefined ? "—" : (qres.cov * 100).toFixed(0) + "%"}</div>${body}
      <details class="top5"><summary>Top-5 listesi</summary>${rows}</details>
      <div class="qlink"><button data-goto="${arm}">Bu kolun chunk sınırlarını sayfada gör →</button></div></div>`;
  }).join("");
  $("querycols").querySelectorAll("button[data-goto]").forEach(b => {
    b.onclick = () => {
      state.mode = "presentation"; state.arm = b.dataset.goto; state.filter = "all"; state.compare = false;
      state.page = g.pg[0] || D().pages[0];
      render();
      g.ev.forEach(id => { const el = document.querySelector(`.u[data-uid="${id}"]`); if (el) el.classList.add("evflash"); });
      const first = document.querySelector(".u.evflash");
      if (first) first.scrollIntoView({block:"center"});
    };
  });
}

/* -------- Debug -------- */
function renderDebugBar(){
  const f = state.dbg;
  const roles = ["all","section","group","item","display"];
  $("dbgbar").innerHTML = `<span>Filtre:</span>
    <select id="dbgtype"><option value="all">tüm tipler</option>${["heading","paragraph","list","table"].map(t => `<option value="${t}" ${f.type === t ? "selected" : ""}>${t}</option>`).join("")}</select>
    <select id="dbgrole">${roles.map(r => `<option value="${r}" ${f.role === r ? "selected" : ""}>${r === "all" ? "tüm roller" : "rol: " + r}</option>`).join("")}</select>
    <input type="text" id="dbgtext" placeholder="metin / unit id ara (bu sayfa)" value="${esc(f.text)}">
    <label><input type="checkbox" id="dbgbig" ${f.onlyBig ? "checked" : ""}> yalnız hard cap üstü unit</label>
    <label><input type="checkbox" id="dbgpf" ${f.onlyPf ? "checked" : ""}> yalnız parser bulgusu olan</label>
    <span class="muted">· sayfa ${state.page} · ${D().parser.count} parser bulgusu (doküman)</span>`;
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
      u.big ? `<span class="chip big">${u.big} token &gt; hard cap — temsil tavanı</span>` : "",
      ...(u.pf || []).map(r => `<span class="chip pf">parser: ${esc(r)}</span>`)
    ].join("");
    const rows = arms.map(arm => {
      const armData = D().arms[arm];
      const segs = armData.seg[u.i] || [];
      if (!segs.length) return `<tr><td>${esc(armLabel(arm))}</td><td colspan="3">unmapped</td></tr>`;
      return segs.map(s => {
        const chunk = armData.chunks[s[0]];
        const frag = chunk.u.find(x => x.split("#")[0] === u.i && x.includes("#"));
        return `<tr><td>${esc(armLabel(arm))}</td><td>${chunk.id}${frag ? " · " + frag.split("#")[1] : ""}</td><td>${s[1]}–${s[2]}</td><td>${s[3]}</td></tr>`;
      }).join("");
    }).join("");
    return `<div class="dbgunit${state.selUnit === u.i ? " sel" : ""}" data-uid="${u.i}">
      <div class="head">${chips}</div><div class="path">${esc(JSON.stringify(u.s))}</div><div class="txt">${esc(u.x)}</div>
      <table class="dbgtable"><tr><th>arm</th><th>chunk · fragment</th><th>offset</th><th>method</th></tr>${rows}</table></div>`;
  }).join("") : `<div class="card muted">Bu sayfada filtreye uyan unit yok.</div>`;
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
  return `<div class="grp"><b>${g.or === "llm" ? "LLM önerisi" : "Kalite kuralı"}</b> — Standard kesimleri: <span class="mono">${esc((g.sc || []).join(", ") || "—")}</span> → final: <span class="mono">${esc((g.fc || []).join(", ") || "— (birleştirildi)")}</span>
    <div>${fixed ? "kaldırılan koku: " + esc(fixed) : "koku değişimi yok"}${intro ? " · eklenen: " + esc(intro) : ""}${esc(se)}</div>
    <div class="ids">grup: ${esc((g.u || []).join(" "))}</div></div>`;
}
function renderInspector(){
  const box = $("inspector");
  const u = state.selUnit && unitById(state.selUnit);
  if (!u) { box.innerHTML = "<b>Unit inspector</b><div class='muted' style='margin-top:8px'>Bir unit'e tıklayın. Seçili unit'in canonical alanları, parser bulguları ve (varsa) bölümünün Deep Analysis karar izi burada görünür.</div>"; return; }
  const fields = {unit_id: u.i, type: u.t, page: u.p, semantic_role: u.r, opens_section: u.o, heading_level: u.l, block: u.b, section_path: u.s};
  let out = `<b>Unit inspector — ${esc(u.i)}</b><pre>${esc(JSON.stringify(fields, null, 1))}</pre>`;
  if (u.big) out += `<div class="guard" style="margin:8px 0">Temsil tavanı: bu unit ${u.big} token — hard cap (${expansionBudget()}) üstünde. Her chunker onu parçalamak zorunda; parçalama sınırı canonical'ı değiştirmeden düzeltilemez.</div>`;
  const pf = D().parser.findings.filter(f => f.t === u.i);
  if (pf.length) out += `<div class="trail"><b>Parser bulguları</b>${pf.map(f => `<div class="row"><dt>${esc(f.r)} · ${esc(f.c)}</dt><dd>${esc(f.why)}${f.ev ? " — <i>" + esc(f.ev) + "</i>" : ""}</dd></div>`).join("")}</div>`;
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
        <div class="row"><dt>LLM danışıldı</dt><dd>${st.cons ? "evet" : "hayır — bölümde deterministik olarak temiz aday yoktu ya da bölüm zaten sığıyor"}</dd></div>
        <div class="row"><dt>Geri alma</dt><dd>${esc(st.rv || "—")}${st.sz ? " · boyut takası" : ""}</dd></div>
        <div class="row"><dt>Koku (S→D)</dt><dd>${st.sm && st.sm.standard ? esc(Object.keys(st.sm.standard).filter(k => st.sm.standard[k] || st.sm.deep[k]).map(k => `${k} ${st.sm.standard[k]}→${st.sm.deep[k]}`).join(", ") || "0") : "—"}</dd></div>
        ${st.gr.map(g => groupHtml(g, st.i)).join("")}
        ${st.pr.length ? `<div style="margin-top:8px"><b>LLM önerileri (verifier)</b>${st.pr.map(p => `<div class="grp"><span class="stpill ${p.a ? "llm_accepted" : "llm_reverted"}">${p.a ? "kabul" : "ret"}</span> ${esc(p.r)} <div class="ids">${esc(p.u.join(" "))}</div></div>`).join("")}</div>` : ""}
      </div>`;
    }
  }
  out += `<div style="margin-top:8px;font-weight:600">Ham metin</div><pre>${esc(u.x)}</pre>`;
  box.innerHTML = out;
}
function renderSectionPanel(){
  const story = D().story;
  const box = $("secpanel");
  if (!story) { box.innerHTML = ""; return; }
  const f = state.dbg.secStatus;
  const all = story.sections;
  const shown = all.filter(s => f === "all" || (f === "changed" ? s.st !== "standard_kept" : s.st === f));
  const counts = story.counts || {};
  box.innerHTML = `<h2 class="sec">Bölüm kararları — Deep Analysis</h2>
    <div class="dbgbar"><span>Durum:</span><select id="secstatus">
      <option value="changed" ${f === "changed" ? "selected" : ""}>değişen bölümler (${all.filter(s => s.st !== "standard_kept").length})</option>
      <option value="all" ${f === "all" ? "selected" : ""}>tümü (${all.length})</option>
      ${Object.keys(SECTION_STATUS).map(k => `<option value="${k}" ${f === k ? "selected" : ""}>${esc(SECTION_STATUS[k])} (${counts[k] ?? 0})</option>`).join("")}
    </select><span class="muted">· LLM danışılan bölüm: ${counts.llm_consulted_sections ?? "—"} · final sınır kökeni: ${esc(JSON.stringify(counts.final_boundaries_by_origin || {}))} · temsil tavanı kesimi: ${counts.ceiling_boundaries ?? "—"}</span></div>
    <div class="scrollx"><table class="sectable"><tr><th>#</th><th>Bölüm</th><th>Sayfa</th><th>Durum</th><th>LLM</th><th>Standard → Final kesimler</th><th>Değişim grupları</th></tr>
    ${shown.map(s => `<tr class="clk" data-si="${s.i}"><td>${s.i}</td><td>${esc(s.h || "—")}</td><td>${s.pg.slice(0, 3).join(", ")}${s.pg.length > 3 ? "…" : ""}</td><td><span class="stpill ${s.st}">${esc(SECTION_STATUS[s.st] || s.st)}</span>${s.rv ? `<div class="muted" style="font-size:11.5px">${esc(s.rv)}</div>` : ""}</td><td>${s.cons ? (s.pr.length ? `${s.pr.filter(p => p.a).length}/${s.pr.length} kabul` : "danışıldı") : "—"}</td><td class="mono" style="font-size:11.5px">${esc(s.std.join(", ") || "—")} → ${esc(s.fin.join(", ") || "—")}</td><td style="font-size:12px">${s.gr.map(g => (g.or === "llm" ? "LLM" : "kural") + (g.rm.length ? ": " + g.rm.map(x => SMELL_FIXED[x] || x).join(", ") : (g.fc.length ? ": taşındı" : ": birleştirildi"))).join("<br>") || "—"}</td></tr>`).join("")}
    </table></div>`;
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
  let out = `<h2>${esc(title)}</h2><div class="scrollx"><table class="t"><tr><th>Yöntem</th>` + columns.map(c => `<th>${esc(c.t)}</th>`).join("") + "</tr>";
  for (const row of rows) {
    out += `<tr><td>${esc(row.arm)}</td>` + columns.map(c => {
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
    frozen.map(a => `<div class="card stat"><div class="v">${arms[a].ret.chunk_count}</div><div class="k">${esc(ARM_LABEL[a])} chunk</div></div>`).join("") +
    `<div class="card stat"><div class="v">${meta.parserFindings ?? "—"}</div><div class="k">parser taban bulgusu (kola ait değil)</div></div></div>`;
  out += benchTable("Retrieval — birincil gold set (BM25)", frozen.map(a => ({arm: ARM_LABEL[a], values: arms[a].ret})), RET_COLS);
  out += `<div class="legend">● = en iyi gözlenen değer (bu koşuda). Tek bir yöntem her metrikte önde değildir; sonuçlar PoC parametreleriyle alınmıştır.</div>`;
  const et = meta.etypes, etKeys = Object.keys(et).sort();
  if (etKeys.length) {
    out += `<h2>Kanıt türüne göre Hit@5</h2><div class="scrollx"><table class="t"><tr><th>Tür</th><th>Sorgu</th>` + frozen.map(a => `<th>${esc(ARM_LABEL[a])}</th>`).join("") + "</tr>" +
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
  out += benchTable("Yapısal kalite (chunk türevli)", frozen.map(a => ({arm: ARM_LABEL[a], values: sqValues(arms[a].sq)})), SQ_COLS, undefined);
  out += `<div class="legend">Bu tabloda "en iyi" işareti yoktur: metriklerin bir kısmı yöntem tanımının sonucudur (örn. markdown örtüşmesi tekrarlanan kütleyi yapısal olarak yükseltir).</div>`;
  const timing = meta.timing || {};
  out += benchTable("Zamanlama", frozen.map(a => { const t = timing[a] || arms[a].tim || {}; return {arm: ARM_LABEL[a], values: {chunk: t.chunk_ms_median, index: t.index_build_ms, p50: t.search_p50_ms, p90: t.search_p90_ms, cold: t.cold ? t.cold.chunk_ms_cold : null}}; }),
    [{k:"chunk", t:"Chunking medyan (ms)", d:1}, {k:"index", t:"İndeks (ms)", d:1}, {k:"p50", t:"Arama p50 (ms)", d:2}, {k:"p90", t:"Arama p90 (ms)", d:2}, {k:"cold", t:"Cold embedding (ms)", d:0}], false);
  out += `<div class="legend">Cold sütunu yalnız Hybrid için anlamlıdır (boundary-embedding önbelleği boşken). Markdown ve Structure-only model yüklemez; cold ≡ warm.</div>`;
  const sec = meta.secondary;
  if (sec && sec.metrics) {
    out += `<details class="secgold"><summary>İkincil gold set (${esc((sec.gold_queries || "").split("/").pop() || "v1")})</summary>`;
    out += benchTable("Retrieval — ikincil set", frozen.map(a => ({arm: ARM_LABEL[a], values: sec.metrics[a] || {}})), RET_COLS) + "</details>";
  }
  return out;
}

function interpretDeep(dm){
  const parts = [];
  const smellDrop = dm.smellTotal.standard - dm.smellTotal.deep;
  parts.push(`<b>Yapısal kalite:</b> koku toplamı ${dm.smellTotal.standard} → ${dm.smellTotal.deep} (${smellDrop > 0 ? "−" + smellDrop : "değişmedi"}); hiçbir bölüm hiçbir koku türünde kötüleşmedi (tiered regresyon ${dm.regressions}).`);
  const r = dm.retrieval || {};
  if (r.deep && r.standard) {
    const d5 = r.deep.hit_at_5 - r.standard.hit_at_5, d1 = r.deep.hit_at_1 - r.standard.hit_at_1, dm_ = r.deep.mrr - r.standard.mrr;
    const noise = Math.abs(d5) < 0.03 && Math.abs(dm_) < 0.03;
    parts.push(`<b>Retrieval:</b> Hit@5 ${fmt(r.standard.hit_at_5, 3)} → ${fmt(r.deep.hit_at_5, 3)}, Hit@1 ${fmt(r.standard.hit_at_1, 3)} → ${fmt(r.deep.hit_at_1, 3)}, MRR ${fmt(r.standard.mrr, 3)} → ${fmt(r.deep.mrr, 3)} — ${r.deep.query_count} gold soruda ${noise ? "fark gürültü içinde; Deep en azından Standard kadar iyi (non-inferior), daha iyi olduğu iddia edilmiyor" : "fark küçük örneklemde ölçüldü, tek başına bir kazanan ilan etmez"}.`);
  } else parts.push(`<b>Retrieval:</b> bu doküman için gold sorgu seti yok; uydurulmadı. Retrieval sonucu olmaması holdout'u başarısız saymaz.`);
  const sc = dm.storyCounts || {};
  parts.push(`<b>LLM'in rolü:</b> ${sc.llm_consulted_sections ?? "—"} bölüme danışıldı, ${dm.verifier ? dm.verifier.accepted : 0} öneri iki sırada da kazanıp kabul edildi, ${dm.verifier ? dm.verifier.reverted : 0} geri alındı${dm.verifier && dm.verifier.reasons ? " (" + Object.entries(dm.verifier.reasons).map(([k, v]) => k + " " + v).join(", ") + ")" : ""}. Ölçülebilir kazanımın büyük kısmı ücretsiz deterministik katmandan gelir; LLM katmanı doğrulanmış küçük bir ek sağlar ve seed olmadığından koşudan koşuya değişir.`);
  parts.push(`<b>Maliyet:</b> ${dm.calls.total} çağrı, ≈ ${(dm.estTokens.prompt / 1000).toFixed(0)}k prompt + ${(dm.estTokens.completion / 1000).toFixed(0)}k completion token (karakter/2,45 tahmini), liste fiyatıyla ≈ $${dm.estCostUsd.toFixed(3)}; duvar saati ≈ ${((dm.timing.llm_calls || 0) + (dm.timing.verifier_calls || 0) + (dm.timing.selection || 0)).toFixed(0)} s, ingest'te tek sefer${dm.timing.standard ? " (Standard " + fmt(dm.timing.standard, 2) + " s)" : ""}.`);
  return `<div class="interp">${parts.join("<br>")}</div>`;
}

function renderDeepPanel(doc){
  const dm = doc.meta.deep;
  if (!dm) return "";
  const arms = doc.arms;
  const std = arms["structure-only"], deep = arms.agentic;
  const sc = dm.storyCounts || {};
  const origin = sc.final_boundaries_by_origin || {};
  const ts = dm.totals.standard || {}, td = dm.totals.deep || {};
  let out = `<h2 class="sec">Deep Analysis paneli — Standard vs Agentic Chunker (ayrı koşu, aynı canonical)</h2>`;
  out += `<div class="guard deep">Bu panel frozen üçlü benchmark'ın dışındadır: Deep Analysis model-bağımlı ve yalnız replay-deterministik bir koşudur (model: ${esc(dm.model || "—")}${dm.verifierModel && dm.verifierModel !== dm.model ? ", verifier: " + esc(dm.verifierModel) : ""}; prompt ${esc(dm.promptVersion || "—")}; mod ${esc(dm.mode || "—")}${dm.status && dm.status !== "ok" ? "; durum " + esc(dm.status) : ""}). Retrieval sayıları frozen kolun kendi BM25 ayarları ve gold setiyle, frozen ağaca dokunmadan hesaplandı. Kazanan ilan edilmez; eşikler poc_initial_not_optimized.</div>`;
  out += `<div class="cards" style="margin-top:12px">
    <div class="card stat"><div class="v">${dm.chunkCount.standard}<small>→ ${dm.chunkCount.deep}</small></div><div class="k">chunk</div></div>
    <div class="card stat deep"><div class="v">${dm.smellTotal.standard}<small>→ ${dm.smellTotal.deep}</small></div><div class="k">koku toplamı</div></div>
    <div class="card stat good"><div class="v">${dm.regressions}</div><div class="k">yapısal regresyon (tiered)</div></div>
    <div class="card stat"><div class="v">${dm.strictRegressions}</div><div class="k">boyut takası (koku ↓, soft-max ↑)</div></div>
    <div class="card stat"><div class="v">${dm.changeGroups}</div><div class="k">değişim grubu</div></div>
    <div class="card stat"><div class="v">${sc.ceiling_boundaries ?? "—"}</div><div class="k">temsil tavanı kesimi</div></div>
    <div class="card stat"><div class="v">${dm.calls.total}</div><div class="k">LLM çağrısı</div></div>
    <div class="card stat"><div class="v">${dm.verifier ? dm.verifier.accepted : 0}<small>/ ${dm.verifier ? dm.verifier.group_count : 0}</small></div><div class="k">verifier kabul / öneri</div></div>
  </div>`;
  const smellRows = ["orphan_label","lead_in_cut","continuation_cut","run_split_when_fits","table_split","fragment_cut","below_min","above_soft_max"];
  out += `<h2>Sınır kalitesi (boundary_quality, bölüm bazında sözleşme)</h2><div class="scrollx"><table class="t"><tr><th>Koku / sayaç</th><th>Standard</th><th>Deep</th><th>Δ</th></tr>` +
    smellRows.map(k => `<tr><td>${esc(SMELL_TEXT[k] || k)} <span class="mono muted">${k}</span></td><td>${ts[k] ?? 0}</td><td class="deepcol">${td[k] ?? 0}</td><td>${(td[k] ?? 0) - (ts[k] ?? 0)}</td></tr>`).join("") +
    `<tr><td><b>koku toplamı</b></td><td><b>${dm.smellTotal.standard}</b></td><td class="deepcol"><b>${dm.smellTotal.deep}</b></td><td><b>${dm.smellTotal.deep - dm.smellTotal.standard}</b></td></tr></table></div>
    <div class="legend">Sözleşme: her koku türü için count_D ≤ count_S bölüm başına; boyut sayaçları yalnız koku toplamı kesin azalırken büyüyebilir (tier 2). Kalan table_split/fragment_cut tek bir unit'in içine zorunlu kesimlerdir — hiçbir bölümleme ulaşamaz (temsil tavanı). Bölüm verdict'leri: ${esc(JSON.stringify(dm.verdictsTiered))}.</div>`;
  const deepSet = new Set(["Agentic Chunker (Deep)"]);
  if (std && std.sq && deep && deep.sq) {
    out += benchTable("Yapısal kalite (chunk_quality, parser tabanı çıkarılmış)", [
      {arm: "Standard (Structure-only)", values: sqValues(std.sq)}, {arm: "Agentic Chunker (Deep)", values: sqValues(deep.sq)}
    ], SQ_COLS, undefined, deepSet);
  }
  const r = dm.retrieval || {};
  if (r.deep && r.standard) {
    out += benchTable("Retrieval — aynı gold set, aynı BM25 (frozen değerler kopya, Deep yeniden skorlandı)", [
      {arm: "Standard (Structure-only)", values: r.standard}, {arm: "Agentic Chunker (Deep)", values: r.deep}
    ], RET_COLS, undefined, deepSet);
  }
  out += `<h2>Sınır kökeni ve LLM kullanımı</h2><div class="scrollx"><table class="t"><tr><th>Ölçüm</th><th>Değer</th></tr>
    <tr><td>Bölüm sayısı</td><td>${sc.sections ?? "—"}</td></tr>
    <tr><td>Yapısal sınır korunan bölüm</td><td>${sc.standard_kept ?? "—"}</td></tr>
    <tr><td>Kalite kuralının iyileştirdiği bölüm</td><td>${sc.deterministic_improved ?? "—"}</td></tr>
    <tr><td>LLM önerisi kabul edilen bölüm</td><td>${sc.llm_accepted ?? "—"}</td></tr>
    <tr><td>LLM önerisi reddedilen bölüm</td><td>${sc.llm_reverted ?? "—"}</td></tr>
    <tr><td>Kalite kontrolünün geri aldığı bölüm</td><td>${sc.contract_reverted ?? "—"}</td></tr>
    <tr><td>Final sınır kökeni (Standard / kural / LLM)</td><td>${origin.standard ?? "—"} / ${origin.deterministic ?? "—"} / ${origin.llm ?? "—"}</td></tr>
    <tr><td>LLM danışılan bölüm</td><td>${sc.llm_consulted_sections ?? "—"}</td></tr>
    <tr><td>Proposer çağrısı (durum)</td><td>${dm.calls.proposer} ${dm.proposer && dm.proposer.call_status ? esc(JSON.stringify(dm.proposer.call_status)) : ""}</td></tr>
    <tr><td>İşaretlenen / yasaklanan sınır oyu</td><td>${dm.proposer ? dm.proposer.boundary_count : "—"} / ${dm.proposer ? dm.proposer.forbidden_boundary_count : "—"}</td></tr>
    <tr><td>Verifier çağrısı (grup × 2 sıra)</td><td>${dm.calls.verifier}</td></tr>
    <tr><td>Verifier kararları</td><td>${dm.verifier ? esc(JSON.stringify(dm.verifier.reasons || {})) : "—"}</td></tr>
    <tr><td>Fallback / geri alma nedenleri</td><td>${esc(JSON.stringify(dm.selection.revert_reasons || {}))}</td></tr>
    <tr><td>Süre (s): öneri / doğrulama / seçim${dm.timing.standard ? " (Standard " + fmt(dm.timing.standard, 2) + ")" : ""}</td><td>${fmt(dm.timing.llm_calls, 1)} / ${fmt(dm.timing.verifier_calls, 1)} / ${fmt(dm.timing.selection, 1)}</td></tr>
    <tr><td>Token tahmini (prompt / completion)</td><td>≈ ${dm.estTokens.prompt.toLocaleString("tr-TR")} / ${dm.estTokens.completion.toLocaleString("tr-TR")} <span class="muted">(karakter ÷ 2,45)</span></td></tr>
    <tr><td>Yaklaşık maliyet</td><td>≈ $${dm.estCostUsd.toFixed(4)} <span class="muted">(${esc(DATA.price.note)}; $${DATA.price.prompt}/M prompt, $${DATA.price.completion}/M completion)</span></td></tr>
  </table></div>`;
  out += interpretDeep(dm);
  return out;
}

function renderCrossDoc(){
  const docs = DOC_ORDER.map(id => [id, DATA.docs[id]]).filter(([, d]) => d.meta.deep);
  if (docs.length < 2) return "";
  let out = `<h2 class="sec">Dokümanlar arası — Deep Analysis kalite sözleşmesi</h2><div class="scrollx"><table class="t"><tr><th>Doküman</th><th>Sayfa</th><th>Unit</th><th>Chunk S→D</th><th>Koku S→D</th><th>Regresyon</th><th>Kural / LLM sınır</th><th>LLM çağrısı</th><th>Verifier kabul</th><th>Süre (s)</th><th>Hit@5 S→D</th></tr>`;
  for (const [id, d] of docs) {
    const dm = d.meta.deep, sc = dm.storyCounts || {}, o = sc.final_boundaries_by_origin || {}, r = dm.retrieval || {};
    out += `<tr><td>${esc(d.label)}${id === "arcelik-2024" ? ' <span class="pill grey">holdout — tuning görmedi</span>' : ""}</td><td>${d.meta.pageCount}</td><td>${d.meta.unitCount}</td><td>${dm.chunkCount.standard} → ${dm.chunkCount.deep}</td><td>${dm.smellTotal.standard} → <b>${dm.smellTotal.deep}</b></td><td>${dm.regressions}</td><td>${o.deterministic ?? "—"} / ${o.llm ?? "—"}</td><td>${dm.calls.total}</td><td>${dm.verifier ? dm.verifier.accepted + "/" + dm.verifier.group_count : "—"}</td><td>${((dm.timing.llm_calls || 0) + (dm.timing.verifier_calls || 0) + (dm.timing.selection || 0)).toFixed(0)}</td><td>${r.deep && r.standard ? fmt(r.standard.hit_at_5, 3) + " → " + fmt(r.deep.hit_at_5, 3) : "gold yok"}</td></tr>`;
  }
  return out + `</table></div><div class="legend">KKB 2024 geliştirme/tuning verisi, KKB 2022 holdout, Arçelik 2024 hiç tuning görmemiş ikinci holdout. Kalan koku toplamlarının tamamı temsil tavanı (unit içi zorunlu kesim) ya da parser kaynaklıdır.</div>`;
}

function renderBenchmark(){
  const doc = D();
  let out = renderFrozenBenchmark(doc);
  if (!out) out = `<div class="guard">Bu doküman için frozen üçlü benchmark yok (gold sorgu seti yok). Aşağıdaki panel Standard ile Deep Analysis'i aynı canonical üzerinde yapısal olarak karşılaştırır.</div>`;
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
      out += benchTable("Retrieval — Agentic (ayrı koşu, aynı gold + BM25 ayarları)", [{arm: armLabel("agentic"), values: ag.ret}], RET_COLS);
      out += `<div class="legend">Bu tablo tek satırdır ve frozen üçlü tablodaki "en iyi" işaretlerine katılmaz; yan yana okuma yaparken model bağımlılığı ve tek koşu olduğu unutulmamalıdır.</div>`;
    } else out += `<div class="legend">Bu ağaçta agentic retrieval değerlendirmesi yok — amsc.agentic_benchmark henüz koşulmamış.</div>`;
  }
  out += renderDeepPanel(doc);
  out += renderCrossDoc();
  $("view-benchmark").innerHTML = out;
  $("view-benchmark").querySelectorAll(".qidchip[data-q]").forEach(el => {
    el.onclick = () => { state.mode = "query"; state.qsub = "gold"; state.query = el.dataset.q; render(); };
  });
}

/* -------- shell -------- */
function render(){
  syncBar();
  for (const mode of ["presentation","query","debug","benchmark"]) $("view-" + mode).classList.toggle("hidden", state.mode !== mode);
  if (state.mode === "presentation") renderPresentation();
  else if (state.mode === "query") renderQuery();
  else if (state.mode === "debug") renderDebug();
  else renderBenchmark();
  $("foot").textContent = D().label + " · canonical " + (D().meta.canonicalSha || "").slice(0, 16) + "… · " + (D().meta.status || "") +
    (D().diffs.length ? " · fark tanımı: ardışık iki içerik unit'i arasında chunk sınırı olup olmadığında üç yöntemin uyuşmadığı noktalar" : "") +
    " · " + DATA.generator;
}
initBar();
render();
</script>
</body>
</html>
"""
