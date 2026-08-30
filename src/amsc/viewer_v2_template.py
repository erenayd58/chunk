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
  --barh:64px;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-padding-top:calc(var(--barh) + 14px)}
html,body{background:var(--paper);color:var(--ink);font:16px/1.6 var(--font)}
button{font:inherit;color:inherit;background:none;border:none;cursor:pointer}
button:focus-visible,select:focus-visible,textarea:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
select,textarea,input[type=text]{font:inherit;color:inherit;padding:6px 10px;border:1px solid var(--line-strong);border-radius:7px;background:#fff}
a{color:var(--accent)}
.hidden{display:none!important}
.muted{color:var(--muted)}
.mono{font-family:var(--mono);font-size:13px}
.nowrap{white-space:nowrap}

/* ---- top bar ---- */
.topbar{position:sticky;top:0;z-index:40;background:var(--panel);border-bottom:1px solid var(--line);
  padding:10px 22px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.brand{font-weight:650;letter-spacing:.2px;display:flex;align-items:baseline;gap:8px}
.brand small{color:var(--muted);font-weight:400}
.brand .tag{font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;
  color:var(--accent);background:var(--accent-soft);border-radius:999px;padding:2px 8px}
.tabs{display:flex;gap:3px;background:#efeee8;border-radius:10px;padding:3px}
.tabs button{padding:7px 20px;border-radius:8px;color:var(--muted);font-weight:550}
.tabs button.on{background:#fff;color:var(--ink);box-shadow:0 1px 2px rgba(0,0,0,.08)}
.seg{display:flex;gap:3px;background:#efeee8;border-radius:10px;padding:3px;flex-wrap:wrap}
.seg button{padding:5px 12px;border-radius:8px;color:var(--muted)}
.seg button.on{background:var(--accent);color:#fff}
.seg button.on.deep{background:var(--deep)}
.seg button small{display:block;font-size:11.5px;font-weight:400;line-height:1.1;opacity:.8}
.bar-right{margin-left:auto;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.conttoggle{display:flex;align-items:center;gap:6px;font-size:13.5px;color:var(--muted);cursor:pointer}
main{max-width:1760px;margin:0 auto;padding:20px 22px 40px}

/* ---- shared cards ---- */
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 18px}
.cards{display:flex;gap:12px;flex-wrap:wrap}
.stat{min-width:140px}
.stat .v{font-size:26px;font-weight:650;font-variant-numeric:tabular-nums;line-height:1.15}
.stat .v small{font-size:14px;font-weight:500;color:var(--muted);margin-left:4px}
.stat .k{color:var(--muted);font-size:13.5px;margin-top:4px;line-height:1.35}
.stat.deep .v{color:var(--deep)}
.stat.good .v{color:var(--good)}
.pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:3px 11px;font-size:13px;font-weight:600;white-space:nowrap}
.pill.ok{background:var(--good-soft);color:var(--good)}
.pill.mid{background:var(--warn-soft);color:var(--warn)}
.pill.miss{background:var(--bad-soft);color:var(--bad)}
.pill.deep{background:var(--deep-soft);color:var(--deep)}
.pill.std{background:var(--accent-soft);color:var(--accent)}
.pill.grey{background:#efeee8;color:#4b5259}
.chip{font:12.5px/1.5 var(--mono);background:#f0efe9;border-radius:5px;padding:1px 7px}
.chip.role{background:#e8e2f6}
.chip.opens{background:#dcefe2}
.chip.noopen{background:#f6e3e0}
.chip.big{background:var(--bad-soft);color:var(--bad)}
.chip.pf{background:var(--warn-soft);color:var(--warn)}
.note{color:var(--muted);font-size:14px;line-height:1.55;max-width:1040px}
.guard{border-left:3px solid var(--accent);background:var(--accent-soft);padding:10px 16px;
  border-radius:0 8px 8px 0;font-size:14.5px;line-height:1.55;margin:12px 0 4px;max-width:1040px}
.guard.deep{border-left-color:var(--deep);background:var(--deep-soft)}
h2.sec{margin:30px 0 10px;font-size:20px;font-weight:650;letter-spacing:-.1px}
h3.sub{margin:18px 0 8px;font-size:16.5px;font-weight:650}
details.adv{margin-top:10px}
details.adv summary{cursor:pointer;color:var(--accent);font-size:14px}
details.adv pre{white-space:pre-wrap;font:12px var(--mono);background:#f6f5f0;border-radius:8px;padding:10px;margin-top:8px;max-height:320px;overflow:auto}
table.t{border-collapse:collapse;background:var(--panel);font-variant-numeric:tabular-nums;font-size:14.5px}
table.t th,table.t td{border:1px solid var(--line);padding:9px 14px;text-align:right}
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
.btn.small{padding:4px 11px;font-size:13px}
.linkbtn{color:var(--accent);text-decoration:underline;padding:0}

/* ---- Sunum: methods + results ---- */
.methods{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin-bottom:6px;
  max-width:1480px}
.method{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:12px 15px 13px;cursor:pointer;
  position:relative;transition:box-shadow .12s,border-color .12s;border-top:3px solid var(--line-strong)}
.method:hover{box-shadow:0 2px 10px rgba(0,0,0,.06)}
.method.on{border-color:var(--accent);border-top-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}
.method.on.deepm{border-color:var(--deep);border-top-color:var(--deep);box-shadow:0 0 0 2px var(--deep-soft)}
.method .name{font-weight:650;font-size:15.5px;display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.method .desc{color:#4a525b;font-size:13.5px;margin-top:6px;line-height:1.45;min-height:39px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.method .facts{color:var(--muted);font-size:12.5px;margin-top:8px;display:flex;gap:9px;flex-wrap:wrap}
/* The baselines are context, not choices: legible, but not competing with
   the two modes a reader actually picks between. */
.method.aside{background:#fbfaf7}
.method.aside .name{font-size:14.5px;font-weight:600}
.method.aside .desc{color:var(--muted);font-size:13px}
.results{background:linear-gradient(135deg,#f4f0ff 0%,#fff 60%);border:1px solid #e3dcf5;border-radius:12px;padding:14px 18px;margin-bottom:16px}
.results .title{font-weight:650;display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.results .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.results .item .v{font-size:23px;font-weight:650;font-variant-numeric:tabular-nums}
.results .item .v .arrow{color:var(--muted);font-weight:400;margin:0 5px}
.results .item .v .to{color:var(--deep)}
.results .item .k{font-size:13px;color:var(--muted);line-height:1.35}

/* ---- Sunum: reader ---- */
.pres-layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:20px}
.readerbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px;font-size:14px;color:var(--muted)}
.readerbar select{padding:3px 8px}
.docpage{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:30px 38px;
  font-family:var(--serif);font-size:16.5px}
.docpage .pagehead{font-family:var(--font);color:var(--muted);font-size:13.5px;margin-bottom:16px;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
.chunkline{display:flex;align-items:center;gap:10px;margin:18px 0 10px;font-family:var(--font);flex-wrap:wrap;
  scroll-margin-top:calc(var(--barh) + 14px)}
.chunkline .rule{flex:1;border-top:3px solid var(--accent);opacity:.5;min-width:30px}
.chunkline.tech .rule{border-top:2px dashed #c9a24b;opacity:.75}
.chunkline .kind{font-size:12px;font-weight:700;letter-spacing:.6px;color:var(--accent);text-transform:uppercase;white-space:nowrap}
.chunkline.tech .kind{color:#8a5a09}
.chunkpill{background:var(--accent-soft);color:var(--accent);border:1px solid #c8d8f2;border-radius:999px;
  padding:3px 13px;font-size:13.5px;font-weight:600;cursor:pointer;white-space:nowrap}
.chunkline.tech .chunkpill{background:#fdf6e7;color:#8a5a09;border-color:#ecd9ab}
.chunkpill .why{font-weight:400;color:#41537a}
.chunkline.tech .chunkpill .why{color:#8a6a2f}
.chunkpill.sel{box-shadow:0 0 0 3px #f2d9a4}
.decpill{border-radius:999px;padding:2px 10px;font-size:12.5px;font-weight:600;white-space:nowrap;border:1px solid transparent}
.decpill.kept{background:#eef1f5;color:#4b5259;border-color:#dfe3e8}
.decpill.det{background:var(--good-soft);color:var(--good);border-color:#c6e6cf}
.decpill.llm{background:var(--deep-soft);color:var(--deep);border-color:#d8cbf3}
.decpill.rev{background:var(--warn-soft);color:var(--warn);border-color:#f2d9a4}
.decpill.ceil{background:var(--bad-soft);color:var(--bad);border-color:#f2c8c2}
.decpill.std{background:#fdf6e7;color:#8a5a09;border-color:#ecd9ab}
.u{padding:2px 10px;border-left:3px solid transparent;border-radius:4px;scroll-margin-top:calc(var(--barh) + 14px)}
.u.tintA{background:var(--tintA)}
.u.tintB{background:var(--tintB)}
.u.contedge{border-left:3px solid #e4c988}
.u.expmember{border-left:3px solid #c9861b;background:#fdf6e7}
.u.evflash,.lanes .cell.evflash{outline:3px solid var(--warn);outline-offset:-3px}
.u.selchunk{outline:2px solid var(--accent);outline-offset:-2px}
.u h1,.u h2,.u h3,.u h4,.u h5,.u h6{font-family:var(--font);line-height:1.3;margin:14px 0 6px}
.u h1{font-size:24px}.u h2{font-size:21px}.u h3{font-size:18px}
.u h4{font-size:17px}.u h5{font-size:16px}.u h6{font-size:15px;color:#3c4046}
.u p{margin:7px 0}
.u ul{margin:7px 0 7px 22px}
.u li{margin:3px 0}
.tblwrap{overflow-x:auto;margin:10px 0}
.tblwrap table{border-collapse:collapse;font-size:14px;font-family:var(--font)}
.tblwrap th,.tblwrap td{border:1px solid var(--line);padding:4px 9px;text-align:left}
.tblwrap th{background:#f4f3ee}
.diffbadge{background:#fdecc8;color:var(--warn);border:1px solid #f2d9a4;border-radius:999px;padding:3px 10px;font-size:12.5px;font-weight:600;white-space:nowrap}
.diffbadge .glyphs{font-weight:400;margin-left:6px}
/* compare grid */
.cmp{display:grid;grid-template-columns:1fr 1fr;gap:0 18px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:24px 28px;font-family:var(--serif);font-size:16px}
.cmp .colhead{font-family:var(--font);font-weight:650;padding-bottom:8px;border-bottom:1px solid var(--line);margin-bottom:6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.cmp .cell{min-width:0;padding:2px 0}
.cmp .cell .chunkline{margin:12px 0 6px}
.cmp .cell .chunkpill{font-size:12.5px;padding:2px 10px}
.sidecard{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;
  position:sticky;top:calc(var(--barh) + 10px);max-height:calc(100vh - var(--barh) - 32px);overflow:auto}
.sidecard h3{font-size:16px;margin-bottom:10px}
.sidecard .kv{display:grid;grid-template-columns:106px 1fr;gap:6px 10px;font-size:14px}
.sidecard .kv dt{color:var(--muted)}
.sidecard .empty{color:var(--muted);font-size:14px}
.reason-sent{margin-top:12px;padding:10px 12px;background:#f6f5f0;border-radius:8px;font-size:14px}
.reason-sent.deep{background:var(--deep-soft)}
.arminfo{margin-top:14px;border-top:1px solid var(--line);padding-top:12px;font-size:13px;color:var(--muted)}
.detail-links button{color:var(--accent);text-decoration:underline;padding:0;font-size:13.5px}

/* ---- Sorgu ---- */
.subtabs{display:flex;gap:4px;margin-bottom:14px}
.subtabs button{padding:6px 14px;border-radius:8px;border:1px solid var(--line-strong);background:#fff;color:var(--muted)}
.subtabs button.on{background:#3d3f43;border-color:#3d3f43;color:#fff}
.chatwrap{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:20px}
.chatbox{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px}
.chatbox textarea{width:100%;min-height:82px;resize:vertical;font-size:15.5px}
.chatctl{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px}
.chatctl label{font-size:13.5px;color:var(--muted);display:flex;align-items:center;gap:6px}
.offline{border:1px dashed var(--line-strong);border-radius:12px;padding:14px 18px;color:var(--muted);font-size:14px;background:#fcfbf8;margin-bottom:14px}
.offline code{font-family:var(--mono);font-size:13px;background:#f0efe9;padding:1px 6px;border-radius:4px}
.suggest{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.suggest button{border:1px solid var(--line);border-radius:999px;padding:4px 12px;font-size:13.5px;background:#fff;color:#3f4750;text-align:left}
.turn{margin-top:18px}
.turn .q{font-weight:650;font-size:17px;margin-bottom:8px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.turn .q .who{font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--muted)}
.answer{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.answer .txt{font-size:16px;line-height:1.65;white-space:pre-wrap}
.answer .meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px;font-size:13px;color:var(--muted)}
.cite{display:inline-block;background:var(--accent-soft);color:var(--accent);border-radius:6px;padding:0 6px;font-size:12px;font-weight:700;margin:0 1px;vertical-align:baseline;font-family:var(--font)}
.cite:hover{background:var(--accent);color:#fff}
.sources{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px;margin-top:12px}
.src{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:11px 13px;cursor:pointer;font-size:13.5px;position:relative}
.src:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}
.src.used{border-color:#9db7e6;background:#fbfcff}
.src.hl{outline:2px solid var(--warn)}
.src .lab{font-weight:700;color:var(--accent);font-size:12px;margin-right:6px}
.src .hd{font-weight:600;margin:3px 0}
.src .path{color:var(--muted);font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.src .facts{color:var(--muted);font-size:12.5px;margin-top:5px;display:flex;gap:8px;flex-wrap:wrap}
.src .usedmark{position:absolute;right:10px;top:8px;color:var(--good);font-weight:700;font-size:12px}
.cmpcols{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-top:14px}
.cmpcol{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;min-width:0}
.cmpcol .armname{font-weight:650;display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap}
.cmpcol .txt{font-size:14.5px;line-height:1.6;white-space:pre-wrap;max-height:260px;overflow:auto;border-left:3px solid var(--line);padding-left:10px}
.cmpcol .srcs{margin-top:10px;font-size:13px}
.cmpcol .srcs div{padding:4px 0;border-bottom:1px solid var(--line);display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;cursor:pointer}
.chatside h3{font-size:15px;margin-bottom:8px}
.chatside .kv{display:grid;grid-template-columns:112px 1fr;gap:5px 8px;font-size:13px}
.chatside .kv dt{color:var(--muted)}
.qhead{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 22px;margin-bottom:16px}
.qhead .qq{font-size:19px;font-weight:600;margin-bottom:6px}
.qhead .qa{color:#374151;margin-bottom:10px}
.qhead .qmeta{color:var(--muted);font-size:13.5px;margin-bottom:10px}
.evbox{border-left:3px solid var(--warn);background:#fdf9ef;padding:10px 14px;border-radius:0 8px 8px 0;font-family:var(--serif);font-size:15px;max-height:230px;overflow:auto}
.evbox .evlabel{font-family:var(--font);font-size:12.5px;color:var(--warn);font-weight:600;letter-spacing:.4px;text-transform:uppercase;margin-bottom:6px}
.qcols{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.qcol{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;min-width:0}
.qcol .armname{font-weight:600;margin-bottom:8px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.qcol .covline{color:var(--muted);font-size:13px;margin-bottom:10px}
.rchunk{border:1px solid var(--line);border-radius:9px;padding:13px;font-family:var(--serif);font-size:14.5px;max-height:330px;overflow:auto}
.rchunk mark{background:var(--mark);padding:0 2px;border-radius:2px}
.rchunk .rhead{font-family:var(--font);font-size:13px;color:var(--muted);margin-bottom:8px}
.rchunk .piece{margin:6px 0}
.top5{margin-top:12px}
.top5 summary{cursor:pointer;color:var(--accent);font-size:14px}
.top5 .row{display:flex;gap:8px;align-items:baseline;padding:6px 4px;border-bottom:1px solid var(--line);font-size:13.5px;flex-wrap:wrap}
.top5 .row .rk{font-weight:600;min-width:44px}
.top5 .row .mt{color:var(--good)}
.qlink{margin-top:10px;font-size:13.5px}
.qlink button{color:var(--accent);text-decoration:underline;padding:0}

/* ---- Debug ---- */
.dbg{display:grid;grid-template-columns:minmax(0,1fr) 420px;gap:20px}
.dbgbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px;font-size:13.5px}
.dbgbar input[type=text]{min-width:220px}
.dbgunit{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:10px;cursor:pointer;
  scroll-margin-top:calc(var(--barh) + 14px)}
.dbgunit.sel{outline:2px solid var(--accent)}
.dbgunit .head{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:6px}
.dbgunit .path{font-size:12.5px;color:var(--muted);margin-bottom:6px;font-family:var(--mono);word-break:break-all}
.dbgunit .txt{font-size:13.5px;color:#374151;white-space:pre-wrap;max-height:80px;overflow:hidden}
.dbgtable{width:100%;border-collapse:collapse;font:12.5px var(--mono);margin-top:8px}
.dbgtable th,.dbgtable td{border:1px solid var(--line);padding:2px 7px;text-align:left}
.dbgtable th{background:#f4f3ee;font-family:var(--font)}
.inspector{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;
  position:sticky;top:calc(var(--barh) + 10px);max-height:calc(100vh - var(--barh) - 32px);overflow:auto;font-size:13.5px}
.inspector pre{white-space:pre-wrap;font:12.5px var(--mono);background:#f6f5f0;border-radius:8px;padding:10px;margin-top:8px;max-height:260px;overflow:auto}
.trail{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}
.trail .row{display:grid;grid-template-columns:112px 1fr;gap:5px 8px;font-size:13px;margin-bottom:5px}
.trail .row dt{color:var(--muted)}
.trail .grp{background:#f8f7f3;border-radius:8px;padding:8px 10px;margin-top:8px;font-size:13px}
.trail .grp .ids{font-family:var(--mono);font-size:11.5px;color:var(--muted);word-break:break-all}
.secpanel{margin-top:22px}
.sectable{width:100%;border-collapse:collapse;font-size:13.5px;background:var(--panel)}
.sectable th,.sectable td{border:1px solid var(--line);padding:7px 11px;text-align:left;vertical-align:top}
.sectable th{background:#f4f3ee;position:sticky;top:var(--barh);z-index:1}
.sectable tr.clk{cursor:pointer;scroll-margin-top:calc(var(--barh) + 52px)}
.sectable tr.clk:hover{background:#fbfaf6}
.stpill{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12.5px;font-weight:600}
.stpill.standard_kept{background:#eef1f5;color:#4b5259}
.stpill.deterministic_improved{background:var(--good-soft);color:var(--good)}
.stpill.llm_accepted{background:var(--deep-soft);color:var(--deep)}
.stpill.llm_reverted{background:var(--warn-soft);color:var(--warn)}
.stpill.contract_reverted{background:var(--bad-soft);color:var(--bad)}

/* ---- Benchmark ---- */
.bench h2{margin:28px 0 10px;font-size:19px;font-weight:650}
.legend{color:var(--muted);font-size:13.5px;line-height:1.55;margin-top:8px;max-width:1040px}
.pairlists{display:flex;gap:16px;flex-wrap:wrap;margin-top:8px}
.pairlists .pl{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 16px;font-size:13.5px;line-height:1.7}
.pairlists .pl b{font-weight:600}
.qidchip{font-family:var(--mono);background:#f0efe9;border-radius:4px;padding:1px 7px;font-size:12.5px;cursor:pointer}
details.secgold{margin-top:14px}
details.secgold summary{cursor:pointer;color:var(--accent)}
.interp{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 20px;font-size:15px;line-height:1.6;max-width:1040px;margin-top:12px}
.interp b{font-weight:650}

/* ---- Sunum: the product story, in the order a first-time reader needs it ---- */
#results,#methodhead,#readerhead,#methodnote,#queryhead2,#dbghead{max-width:1480px}
#methodnote .help{margin-top:2px}
.guard.warn{border-left-color:var(--warn);background:var(--warn-soft)}

/* ---- the result band: the one thing on this screen that is loud ---- */
.hero{background:linear-gradient(135deg,#2c2450 0%,#43356f 46%,#5b3ea6 100%);color:#f3f0fb;
  border-radius:14px;padding:16px 24px 17px;max-width:1480px;box-shadow:0 8px 26px rgba(58,42,108,.20)}
.hero.flat{background:linear-gradient(135deg,#2b3140 0%,#3d4557 55%,#4c5568 100%);box-shadow:0 8px 26px rgba(43,49,64,.18)}
.hero-head{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:13px}
.hero-doc{font-size:19px;font-weight:650;letter-spacing:-.2px}
.hero-facts{font-size:13px;color:#c3bbdf;display:flex;gap:9px;flex-wrap:wrap}
.hero.flat .hero-facts{color:#b8bfcd}
.hero-badge{margin-left:auto;display:flex;gap:7px;flex-wrap:wrap}
.hero-badge .pill{background:rgba(255,255,255,.16);color:#fff}
.hero-nums{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px 30px}
.hero-nums .n{min-width:0}
.hero-nums .v{font-size:34px;font-weight:650;line-height:1.05;font-variant-numeric:tabular-nums;
  display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
.hero-nums .v .from{color:#a99ccb;font-size:26px;font-weight:600}
.hero-nums .v .arrow{color:#a99ccb;font-size:23px;font-weight:400}
.hero-nums .v .to{color:#fff}
.hero.flat .v .from,.hero.flat .v .arrow{color:#98a2b5}
.hero-nums .k{font-size:13.5px;color:#cfc7e6;margin-top:5px;display:flex;align-items:center;gap:2px;flex-wrap:wrap}
.hero.flat .hero-nums .k{color:#c2c9d6}
.hero-nums .k .info{border-color:rgba(255,255,255,.4);color:#e7e2f6}
.hero-nums .k .info:hover{background:rgba(255,255,255,.16);border-color:#fff;color:#fff}
.hero-nums .sub{font-size:12.5px;color:#b4a9d4;margin-top:3px}
.hero.flat .hero-nums .sub{color:#aab2c1}
.hero-nums .gain{display:inline-block;margin-top:6px;border-radius:999px;padding:2px 10px;font-size:12.5px;
  font-weight:650;background:rgba(126,231,159,.18);color:#8ff0b4}
.hero-line{margin-top:14px;padding-top:11px;border-top:1px solid rgba(255,255,255,.16);
  font-size:14.5px;line-height:1.5;color:#ddd7ee}
.hero.flat .hero-line{color:#d3d8e2}
.hero-line b{color:#fff;font-weight:650}
.guards{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-top:12px}
.guards .g{border-left:3px solid var(--line-strong);padding:2px 0 2px 14px;font-size:14px;line-height:1.5;color:#3f4750}
.guards .g b{color:var(--ink);font-weight:650;display:block;margin-bottom:2px}
.guards .g.llm{border-left-color:var(--deep)}
.guards .g.rule{border-left-color:var(--good)}
/* "When is it worth it": advice, so it reads as a note rather than as a
   result competing with the band above it. */
.when{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px 26px;margin-top:12px;
  border-left:3px solid var(--line-strong);padding:2px 0 2px 16px;max-width:1480px}
.when .w{font-size:13.5px;line-height:1.5;color:var(--muted)}
.when .w b{display:block;color:#3f4750;font-weight:650;font-size:13px;margin-bottom:2px}
/* ---- the comparison workbench ---- */
.workbench{display:flex;flex-direction:column;gap:10px;margin-bottom:14px;max-width:1480px}
.wb-lanes{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.wb-lanes .lab{font-size:13.5px;color:var(--muted);margin-right:2px}
.lanechip{border:1px solid var(--line-strong);border-radius:999px;padding:5px 14px;background:#fff;
  font-size:14px;font-weight:550;color:#3f4750;display:inline-flex;align-items:center;gap:7px}
.lanechip:hover{border-color:var(--accent)}
.lanechip .dot{width:9px;height:9px;border-radius:3px;background:var(--line-strong);flex:0 0 auto}
.lanechip.on{border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}
.lanechip.on.deepm{border-color:var(--deep);background:var(--deep-soft);color:var(--deep)}
.lanechip.off{opacity:.5;cursor:not-allowed;border-style:dashed}
.wb-nav{display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:14px;color:var(--muted)}
.wb-nav select{max-width:520px}
.wb-nav .stepnav{display:inline-flex;gap:4px;align-items:center}
.wb-nav .stepnav button{border:1px solid var(--line-strong);border-radius:7px;padding:4px 11px;background:#fff}
.wb-nav .stepnav button:disabled{opacity:.4;cursor:default}
.wb-nav .grow{margin-left:auto;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.wb-nav .conttoggle{cursor:pointer}

/* Aligned lanes: one row per canonical unit, one column per method, so a
   boundary that exists in one lane and not another is visible without
   reading a word. */
.lanes{background:var(--panel);border:1px solid var(--line);border-radius:12px}
.lanes .head{display:grid;position:sticky;top:var(--barh);z-index:5;background:#f4f3ee;
  border-bottom:1px solid var(--line-strong);border-radius:11px 11px 0 0}
.lanes .head > div{padding:10px 16px;font-weight:650;font-size:14.5px;display:flex;align-items:center;
  gap:8px;flex-wrap:wrap;border-left:1px solid var(--line)}
.lanes .head > div:first-child{border-left:none}
.lanes .head .n{font-weight:400;color:var(--muted);font-size:13px}
.lanes .row{display:grid;border-bottom:1px solid #f0efe9}
.lanes .row:last-child{border-bottom:none}
.lanes .row.split{border-bottom-color:var(--line)}
.lanes .cell{padding:0 16px;border-left:1px solid var(--line);min-width:0;position:relative}
.lanes .cell:first-child{border-left:none}
.lanes .cell .body{font-family:var(--serif);font-size:15.5px;padding:6px 0}
.lanes .cell.tintA{background:var(--tintA)}
.lanes .cell.tintB{background:var(--tintB)}
.lanes .cell.sel{box-shadow:inset 0 0 0 2px var(--accent)}
.lanes .cut{display:flex;align-items:center;gap:9px;margin:0 -16px;padding:7px 16px;position:relative;z-index:1;
  background:linear-gradient(90deg,rgba(31,79,156,.10),rgba(31,79,156,0));border-top:2px solid var(--accent);
  scroll-margin-top:calc(var(--barh) + 70px)}
.lanes .cut.deepcut{background:linear-gradient(90deg,rgba(91,62,166,.12),rgba(91,62,166,0));border-top-color:var(--deep)}
.lanes .cut.techcut{border-top-style:dashed;border-top-color:#c9a24b;
  background:linear-gradient(90deg,rgba(201,162,75,.14),rgba(201,162,75,0))}
.lanes .cut button{font-size:13px;font-weight:650;color:var(--accent);white-space:nowrap}
.lanes .cut.deepcut button{color:var(--deep)}
.lanes .cut.techcut button{color:#8a5a09}
.lanes .cut .why{font-weight:400;color:var(--muted);font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lanes .rowmark{grid-column:1/-1;display:flex;align-items:center;gap:10px;padding:6px 16px;position:relative;z-index:2;
  background:#fdf6e7;border-top:1px solid #ecd9ab;border-bottom:1px solid #ecd9ab;
  font:12.5px/1.4 var(--font);color:#8a5a09;scroll-margin-top:calc(var(--barh) + 70px)}
.lanes .rowmark b{font-weight:650}
.lanes .rowmark.here{box-shadow:0 0 0 2px var(--warn)}
.toolstash{display:none}

/* ---- explainer layer: the plain-language skin over the technical numbers ---- */
.sechead{margin:26px 0 9px;max-width:1040px}
.sechead:first-child{margin-top:0}
.sechead h2{font-size:20px;font-weight:650;letter-spacing:-.1px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.sechead .lead{color:var(--muted);font-size:14px;line-height:1.55;margin-top:5px}
.sechead .step{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:999px;
  background:var(--accent-soft);color:var(--accent);font-size:12.5px;font-weight:700;flex:0 0 auto}
.help{color:var(--muted);font-size:13.5px;line-height:1.5;margin-top:5px}
.info{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:999px;
  border:1px solid var(--line-strong);color:var(--muted);font-size:11px;font-weight:700;cursor:pointer;
  vertical-align:1px;margin-left:5px;font-family:var(--font);user-select:none;padding:0;flex:0 0 auto}
.info:hover,.info.on{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}
.tip{position:fixed;z-index:90;background:#26292e;color:#f4f3ef;border-radius:9px;padding:10px 13px;
  font:13.5px/1.5 var(--font);box-shadow:0 6px 24px rgba(0,0,0,.28);pointer-events:none;max-width:340px}
.techname{font-family:var(--mono);font-size:12px;color:var(--muted)}

/* KPI row: the top layer of every summary */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(212px,1fr));gap:12px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:15px 17px;min-width:0}
.kpi .lab{font-size:13.5px;font-weight:600;color:#3f4750;display:flex;align-items:center;gap:2px;flex-wrap:wrap}
.kpi .v{font-size:27px;font-weight:650;font-variant-numeric:tabular-nums;line-height:1.2;margin-top:7px;
  display:flex;align-items:baseline;gap:7px;flex-wrap:wrap}
.kpi .v .from{color:var(--muted);font-weight:600}
.kpi .v .arrow{color:var(--muted);font-size:18px;font-weight:400}
.kpi .v .to{color:var(--deep)}
.kpi .v .unit{font-size:14px;font-weight:500;color:var(--muted)}
.kpi .sub{font-size:13px;color:var(--muted);margin-top:6px;line-height:1.4}
.kpi .delta{display:inline-block;border-radius:999px;padding:1px 9px;font-size:12.5px;font-weight:650;margin-top:8px}
.kpi .delta.good{background:var(--good-soft);color:var(--good)}
.kpi .delta.flat{background:#eef1f5;color:#4b5259}
.kpi .delta.warn{background:var(--warn-soft);color:var(--warn)}
.kpi.hero{background:linear-gradient(150deg,var(--deep-soft) 0%,var(--panel) 62%);border-color:#ded4f4}

/* ---- what improved: one row per defect, two bars on one scale ----
   Standard on top, Deep below it. A shorter lower bar is the whole
   message, and it reads without a legend. */
.fixlist{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:4px 20px 10px;margin-top:8px}
.fixrow{display:grid;grid-template-columns:minmax(190px,300px) minmax(140px,1fr) 118px;gap:20px;align-items:center;
  padding:7px 0;border-bottom:1px solid #f1efe9}
.fixrow:last-child{border-bottom:none}
.fixrow.flat{opacity:.72}
.fixrow .name{font-size:14px;font-weight:600;min-width:0}
.fixrow .bars{display:flex;flex-direction:column;gap:3px;min-width:0}
.fixrow .b{height:8px;border-radius:4px;background:#f0eef8;position:relative}
.fixrow .b i{position:absolute;left:0;top:0;bottom:0;border-radius:4px}
.fixrow .b.std i{background:#bcaee6}
.fixrow .b.deep i{background:var(--deep)}
.fixrow.gone .b.deep i{background:var(--good)}
.fixrow .n{text-align:right;font-variant-numeric:tabular-nums;font-size:14.5px;white-space:nowrap;font-weight:600}
.fixrow .n .to{color:var(--deep)}
.fixrow.gone .n .to{color:var(--good)}
.fixrow .n .kept{color:var(--muted);font-weight:500}
.fixrow .n small{display:block;font-size:11.5px;font-weight:500;color:var(--muted);margin-top:2px}
.fixhead{display:grid;grid-template-columns:minmax(190px,300px) minmax(140px,1fr) 118px;gap:20px;
  padding:9px 0 7px;font-size:12px;letter-spacing:.3px;text-transform:uppercase;color:var(--muted);
  border-bottom:1px solid var(--line)}
.fixhead .legend2{display:flex;gap:16px;text-transform:none;letter-spacing:0;font-size:12.5px}
.fixhead .legend2 span{display:flex;align-items:center;gap:6px}
.fixhead .swatch{width:16px;height:8px;border-radius:4px;display:inline-block}

/* glossary */
.gloss{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:4px 18px 12px;margin-top:10px}
.gloss dl{display:grid;grid-template-columns:minmax(190px,270px) 1fr;gap:0 20px}
.gloss dt{font-size:14px;font-weight:600;padding:10px 0 0;border-top:1px solid var(--line)}
.gloss dt:first-of-type,.gloss dd:first-of-type{border-top:none}
.gloss dd{font-size:13.5px;color:#3f4750;line-height:1.5;padding:10px 0;border-top:1px solid var(--line)}
.gloss dt .techname{display:block;font-weight:400;margin-top:2px}
details.deep-detail{margin-top:14px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:0 18px}
details.deep-detail>summary{cursor:pointer;color:var(--accent);font-size:14px;font-weight:600;padding:13px 0;list-style-position:outside}
details.deep-detail[open]>summary{border-bottom:1px solid var(--line);margin-bottom:6px}
details.deep-detail .inner{padding-bottom:16px}
details.deep-detail .inner>h2:first-child,details.deep-detail .inner>.sechead:first-child{margin-top:14px}

/* ---- workspace: an auxiliary panel, never the page's content ----
   The console link is a navigation aid, so it lives as one button in the top
   bar and opens on demand; the documents it lists reach the reader through
   the document picker, which is where a reader already looks. */
#wsopen{display:inline-flex;align-items:center;gap:7px}
#wsopen .dot{width:8px;height:8px;border-radius:999px;background:var(--muted);flex:0 0 auto}
#wsopen.live .dot{background:var(--good)}
#wsopen.down .dot{background:var(--bad)}
.wskb{border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:#fcfbf8;min-width:0;margin-top:10px}
.wskb .kbname{font-weight:650;font-size:15px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.wskb .kbmeta{color:var(--muted);font-size:13px;margin-top:4px;display:flex;gap:12px;flex-wrap:wrap}
.wskb .docs{margin-top:8px;display:flex;flex-direction:column}
.wskb details>summary{cursor:pointer;color:var(--accent);font-size:13.5px;margin-top:8px}
.wsdoc{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;font-size:13.5px;padding:8px 0;border-top:1px solid var(--line)}
.wsdoc .dname{font-weight:600;overflow-wrap:anywhere}
.wsdoc .dmeta{color:var(--muted);font-size:12.5px;margin-left:auto;white-space:nowrap}
.wskb .none{color:var(--muted);font-size:13.5px;margin-top:8px}

/* ---- modal ---- */
.modal{position:fixed;inset:0;background:rgba(20,22,26,.45);z-index:80;display:flex;align-items:center;justify-content:center;padding:20px}
.modal .box{background:var(--panel);border-radius:14px;max-width:980px;width:100%;max-height:88vh;overflow:auto;padding:22px 26px;box-shadow:0 12px 40px rgba(0,0,0,.25)}
.modal .box .mhead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}
.modal .box .mhead h3{font-size:17px}
.modal .box .mbody{font-family:var(--serif);font-size:16px;line-height:1.6}
.modal .box .mbody p{margin:8px 0}
.modal .box .mbody ul{margin:8px 0 8px 22px}
.modal .box .mfacts{display:flex;gap:10px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin-bottom:10px}
footer{color:var(--muted);font-size:12.5px;padding:26px 22px;text-align:center}

@media (max-width:1100px){
  .pres-layout,.dbg,.chatwrap{grid-template-columns:1fr}
  .sidecard,.inspector{position:static;max-height:none}
  .docpage{padding:22px 20px}
  .fixrow{grid-template-columns:1fr;gap:6px}
  .fixrow .n{text-align:left}
  .gloss dl{grid-template-columns:1fr}
  .gloss dd{border-top:none;padding-top:2px}
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
    <button data-mode="presentation">Sunum</button>
    <button data-mode="query">Sorgu</button>
    <button data-mode="debug">Debug</button>
    <button data-mode="benchmark">Benchmark</button>
  </div>
  <div class="seg" id="armseg"></div>
  <div class="bar-right">
    <button class="btn small" id="wsopen" title="RAG Console'daki bilgi tabanları ve dokümanlar"><span class="dot" id="wsdot"></span> <span id="wslabel">RAG Console</span></button>
  </div>
  <!-- The reader's page control, parked here while Debug is not showing. -->
  <div class="toolstash" id="toolstash">
    <span id="pagectl">Sayfa <select id="pagesel"></select></span>
  </div>
</div>
<main>
  <div id="view-presentation" data-mode="presentation">
    <div class="sechead" id="methodhead"></div>
    <div id="methods" class="methods"></div>
    <div id="methodnote"></div>
    <div id="results"></div>
    <div class="sechead" id="readerhead"></div>
    <div class="workbench">
      <div class="wb-lanes" id="lanepicker"></div>
      <div class="wb-nav" id="navbar"></div>
    </div>
    <div class="pres-layout">
      <div id="prespage"></div>
      <aside class="sidecard" id="presdetail"></aside>
    </div>
  </div>
  <div id="view-query" class="hidden" data-mode="query">
    <div class="sechead" id="queryhead2"></div>
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
      <div style="margin-bottom:14px">Gold sorgu: <select id="querysel" style="max-width:900px"></select></div>
      <div id="queryhead"></div>
      <div class="qcols" id="querycols"></div>
    </div>
  </div>
  <div id="view-debug" class="hidden" data-mode="debug">
    <div class="sechead" id="dbghead"></div>
    <div class="readertools" id="dbgtools"></div>
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
<div id="tip" class="tip hidden" role="tooltip"></div>
<div id="modal" class="modal hidden"></div>
<script id="viewer-data" type="application/json">__VIEWER_DATA__</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("viewer-data").textContent);
const ARMS = DATA.armOrder;
const PRODUCT_ARMS = DATA.productArmOrder || ["markdown","hybrid","structure-only","agentic"];
const ARM_LABEL = DATA.armLabels;

const LANE_COLOR = {markdown: "#8a5a09", hybrid: "#0f766e", "structure-only": "#1f4f9c", agentic: "#5b3ea6"};

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
  smell:        {label:"Yapısal kalite problemi", tech:"boundary smell", help:"Chunk sınırının yanlış yerden geçtiği durumların sayısı: kopmuş başlık, bölünmüş liste, ortadan ikiye ayrılmış tablo. Deterministik olarak sayılır, tahmin değildir. Ne kadar düşükse o kadar iyi."},
  regression:   {label:"Kötüleşen bölüm", tech:"tiered regression", help:"Deep Analysis'ten sonra herhangi bir problem türünde Standard'dan daha kötü hale gelen bölüm sayısı. Sözleşme gereği 0 olmak zorundadır."},
  sizetrade:    {label:"Boyut takası", tech:"strict regression", help:"Kalite problemi kesin azalırken parça boyutunun hedefin dışına taştığı bölüm sayısı. Bilinçli bir takastır, hata değildir."},
  ceiling:      {label:"Kaçınılmaz kesim", tech:"temsil tavanı / ceiling boundary", help:"Tek bir tablonun ya da paragrafın kendisi bütçeden büyük olduğu için hiçbir bölümleme yönteminin kaçınamayacağı kesim. Kalan problemlerin bu kısmı düzeltilebilir değildir."},
  hit:          {label:"Doğru parçayı bulma oranı", tech:"Hit@1 / Hit@3 / Hit@5", help:"Gold soruların yüzde kaçında doğru cevabı içeren chunk ilk 1 / 3 / 5 sonuç arasında geldi. 1'e ne kadar yakınsa o kadar iyi."},
  mrr:          {label:"Sıralama kalitesi", tech:"MRR", help:"Doğru chunk'ın sonuç listesindeki sırasının tersinin ortalaması. Doğru sonuç ne kadar üste çıkarsa o kadar yüksektir."},
  coverage:     {label:"Kanıt kapsama", tech:"evidence coverage", help:"Cevabın dayandığı kanıt metninin, getirilen chunk'lar tarafından ne kadarının kapsandığı."},
  goldset:      {label:"Gold sorgu seti", tech:"gold set", help:"Cevabı ve kanıt metni elle doğrulanmış soru listesi. Ölçüm bunun üzerinden yapılır; sorusu olmayan doküman için retrieval sayısı uydurulmaz."},
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
  query: null,
  selChunk: null,
  selArm: null,
  selUnit: null,
  contShow: false,
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
    b.onclick = () => { state.mode = b.dataset.mode; render(); };
  });
  $("qsubtabs").querySelectorAll("button").forEach(b => {
    b.onclick = () => { state.qsub = b.dataset.sub; render(); };
  });
  $("wsopen").onclick = openWorkspaceModal;
  $("modal").onclick = e => { if (e.target === $("modal")) closeModal(); };
  document.addEventListener("keydown", e => { if (e.key === "Escape") { hideTip(); closeModal(); } });
  initTips();
  // Coming back to this tab after creating a knowledge base in the console is
  // the demo's natural gesture: re-read the console then, throttled so a busy
  // alt-tab does not turn into a request per switch.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && Date.now() - workspace.at > 10000) loadWorkspace();
  });
  measureBar();
  window.addEventListener("resize", measureBar);
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

// Which methods the reader is comparing. Defaults to the two that answer the
// product's question -- the base method and the premium one -- when both are
// there, otherwise to everything the document has.
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
  state.lanes = lanes.slice();
  if (!lanes.includes(state.arm)) state.arm = lanes[0];
  if (!lanes.includes(selArm())) { state.selArm = lanes[0]; state.selChunk = null; }
}

// Where the compared methods disagree: between two consecutive content units,
// at least one lane cuts and at least one does not. Computed over the lanes on
// screen, so the count always matches what the reader is looking at.
function laneDiffs(){
  const lanes = laneList();
  if (lanes.length < 2) return [];
  const content = D().units.filter(u => u.t !== "heading");
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
  return points;
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

// Only Debug shows this; Sunum's method cards are its own selector.
function renderArmSeg(){
  const seg = $("armseg");
  seg.innerHTML = docArms().map(a =>
    `<button data-arm="${a}" class="${isDeepArm(a) ? "deep" : ""}">${esc(armLabel(a))}${
      armTech(a) !== armLabel(a) ? `<small>${esc(armTech(a))}</small>` : ""}</button>`).join("");
  seg.querySelectorAll("button").forEach(b => {
    b.onclick = () => { state.arm = b.dataset.arm; state.selArm = b.dataset.arm; state.selChunk = null;
      if (state.armB === state.arm) state.armB = docArms().find(a => a !== state.arm) || state.arm; render(); };
  });
}

function syncBar(){
  $("modetabs").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.mode === state.mode));
  renderArmSeg();
  $("armseg").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.arm === state.arm));
  // Only Debug still reads by page; the comparison reads by section.
  const el = $("pagectl");
  if (state.mode === "debug") { $("dbgtools").appendChild(el); el.style.display = ""; }
  else { $("toolstash").appendChild(el); el.style.display = "none"; }
  $("armseg").style.display = state.mode === "debug" ? "" : "none";
  if (state.mode === "debug") {
    syncPage();
    const sel = $("pagesel");
    sel.innerHTML = pageList().map(p => `<option value="${p}">${p}</option>`).join("");
    sel.value = state.page;
    sel.onchange = () => { state.page = Number(sel.value); render(); };
  }
}

/* -------- Sunum: methods + results -------- */
function renderMethods(){
  const doc = D();
  const an = analysisState();
  const present = PRODUCT_ARMS.filter(a => doc.arms[a]);
  const missing = PRODUCT_ARMS.filter(a => !doc.arms[a]);
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
    return `<div class="method ${aside ? "aside" : ""} ${state.arm === a ? "on" : ""} ${a === "agentic" ? "deepm" : ""}" data-arm="${a}">
      <div class="name">${esc(naming.top)} ${badge}${info(desc)}</div>
      <div class="desc">${esc(impact)}</div>
      <div class="facts">${facts.map(f => `<span>${esc(f)}</span>`).join("")}</div>
    </div>`;
  }).join("");
  // An absent method is explained once, in a line -- never faked, never a card.
  $("methodnote").innerHTML = missing.length
    ? `<div class="help">${missing.map(a => esc(absentReason(a))).join(" ")}</div>`
    : "";
  $("methods").querySelectorAll(".method").forEach(el => {
    el.onclick = () => { state.arm = el.dataset.arm; state.selArm = el.dataset.arm; state.selChunk = null;
      if (state.armB === state.arm) state.armB = docArms().find(a => a !== state.arm) || state.arm; render(); };
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
        `<div class="results"><div class="title"><span class="pill grey">Agentic Chunker — ayrı koşu</span> <span class="muted" style="font-weight:400;font-size:13px">model: ${esc(am.model || "—")} · mod: ${esc(am.mode || "—")} · kazanan ilan edilmez</span></div>
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
  const facts = [`${doc.meta.unitCount.toLocaleString("tr-TR")} birim`,
                 `${Math.max(...doc.pages)} sayfa`,
                 llm && dm.model ? esc(dm.model) : null].filter(Boolean);
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
        <div class="hero-doc">${esc(doc.label)}</div>
        <div class="hero-facts">${facts.map(f => `<span>${f}</span>`).join("")}</div>
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

  return `<div class="results" style="background:none;border:none;padding:0;margin:0">
    ${sectionHead(opts && opts.step, "Standard → Deep Analysis", null)}
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
          <span><i class="swatch" style="background:#bcaee6"></i>Standard</span>
          <span><i class="swatch" style="background:var(--deep)"></i>Deep Analysis</span>
        </span>
        <span style="text-align:right">Adet</span></div>
      ${rows}
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
  if (d.status === "ceiling") return `<span class="decpill ceil">zorunlu kesim — bu blok tek başına bütçeden büyük</span>`;
  if (d.status === "det_moved") {
    const why = (d.removed_smells || []).map(s => SMELL_FIXED[s] || s);
    if (!why.length && d.size_effect && d.size_effect.below_min && d.size_effect.below_min.final < d.size_effect.below_min.standard) why.push("küçük parça birleştirildi");
    return `<span class="decpill det">kalite kuralı sınırı taşıdı${why.length ? ": " + esc(why.join(", ")) : ""}</span>` +
      (d.llm_reverted ? `<span class="decpill rev">model başka bir sınır önerdi, doğrulamadan geçmedi</span>` : "");
  }
  if (d.status === "llm_accepted") return `<span class="decpill llm">model önerisi doğrulandı ve kabul edildi</span>`;
  if (d.status === "kept") return d.llm_reverted
    ? `<span class="decpill rev">model başka bir sınır önerdi, doğrulamadan geçmedi — yapısal sınır korundu</span>`
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


// The lane picker: which methods are on screen. Every method the document
// actually has is offered; nothing else is, and nothing is faked.
function renderLanePicker(){
  const lanes = laneList();
  const have = docArms();
  if (!lanes.includes(state.arm)) { state.arm = lanes[0]; state.selArm = lanes[0]; state.selChunk = null; }
  const absent = PRODUCT_ARMS.filter(a => !have.includes(a));
  const chips = have.map(a => {
    const on = lanes.includes(a);
    const naming = modeName(a);
    return `<button class="lanechip ${on ? "on" : ""} ${a === "agentic" ? "deepm" : ""}" data-lane="${a}"
      aria-pressed="${on}"><span class="dot" style="background:${LANE_COLOR[a] || "#9aa3ad"}"></span>${esc(naming.top)}
      <span class="muted" style="font-weight:400;font-size:12.5px">${D().arms[a].chunks.length}</span></button>`;
  }).join("");
  const off = absent.map(a =>
    `<button class="lanechip off" disabled title="${esc(absentReason(a))}">${esc(modeName(a).top)}</button>`).join("");
  $("lanepicker").innerHTML = `<span class="lab">Karşılaştır:</span>${chips}${off}` +
    (lanes.length < 2 ? `<span class="muted" style="font-size:13px">— ikinci bir yöntem seçin</span>` : "");
  $("lanepicker").querySelectorAll("button[data-lane]").forEach(el => {
    el.onclick = () => {
      const arm = el.dataset.lane;
      const next = lanes.includes(arm) ? lanes.filter(a => a !== arm) : lanes.concat([arm]);
      if (!next.length) return;  // one lane always stays on screen
      setLanes(docArms().filter(a => next.includes(a)));
      state.diffIdx = -1;
      render();
    };
  });
}

// The navigator: sections first, differences second, pages last. A page is
// where something was printed; a section is what it is about, and a difference
// is what this screen is for.
// Pages first: a reader following a printed document knows where they are by
// its page number. The section this page belongs to rides along as the
// secondary fact, because it is what tells you what you are reading.
function renderNavigator(){
  const pages = D().pages;
  const diffs = laneDiffs();
  if (state.page === null || !pages.includes(state.page)) state.page = firstContentPage();
  const at = pages.indexOf(state.page);
  const options = pages.map(p =>
    `<option value="${p}" ${p === state.page ? "selected" : ""}>${p}</option>`).join("");
  // Which section(s) this page falls in -- named, so the page number is not
  // the only thing telling the reader where they are.
  const here = docSections().filter(s => s.pages.includes(state.page)).map(s => s.title);
  $("navbar").innerHTML = `
    <span>Sayfa</span><select id="pagenav">${options}</select>
    <span class="stepnav"><button id="prevpage" ${at <= 0 ? "disabled" : ""}>&#8592;</button>
      <button id="nextpage" ${at >= pages.length - 1 ? "disabled" : ""}>&#8594;</button></span>
    <span class="muted">${at + 1} / ${pages.length}</span>
    ${diffs.length ? `<span class="stepnav" style="margin-left:8px">
      <button id="prevdiff2">&#8592;</button><button id="nextdiff2">&#8594;</button></span>
      <span>${diffs.length} ayrışma noktası${state.diffIdx >= 0 ? ` · ${state.diffIdx + 1}.` : ""}</span>`
      : (laneList().length > 1 ? `<span>bu yöntemler her yerde aynı kesiyor</span>` : "")}
    <span class="grow">
      <label class="conttoggle"><input type="checkbox" id="contchk2" ${state.contShow ? "checked" : ""}> Devam zinciri
        ${info("Bir parça aramada bulunduğunda aynı bölümün devamı olan komşu parçalar da cevaba taşınabilir. Bu kutu o zinciri gösterir; ölçümleri değiştirmez.")}</label>
      ${here.length ? `<span class="muted" style="font-size:13px;max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
        title="${esc(here.join(" · "))}">${esc(here.join(" · "))}</span>` : ""}
    </span>`;
  $("pagenav").onchange = e => { state.page = Number(e.target.value); state.diffIdx = -1; render(); };
  $("prevpage").onclick = () => { state.page = pages[Math.max(0, at - 1)]; state.diffIdx = -1; render(); };
  $("nextpage").onclick = () => { state.page = pages[Math.min(pages.length - 1, at + 1)]; state.diffIdx = -1; render(); };
  $("contchk2").onchange = e => { state.contShow = e.target.checked; render(); };
  if (diffs.length) {
    $("prevdiff2").onclick = () => stepLaneDiff(-1);
    $("nextdiff2").onclick = () => stepLaneDiff(1);
  }
}

// Move to the next place the compared methods disagree, wherever it is: the
// section follows the difference, not the other way round.
// Move to the next place the compared methods disagree, wherever it is: the
// page follows the difference, not the other way round.
function stepLaneDiff(delta){
  const diffs = laneDiffs();
  if (!diffs.length) return;
  state.diffIdx = (state.diffIdx + delta + diffs.length) % diffs.length;
  const point = diffs[state.diffIdx];
  const unit = unitById(point.before);
  if (unit) state.page = unit.p;
  render();
  const el = document.querySelector(`.rowmark[data-diff="${point.before}"]`);
  if (el) { el.scrollIntoView({block: "center"}); el.classList.add("here"); }
}

const NUMS = ["", "bir", "iki", "üç", "dört"];
function renderPresentation(){
  let step = 0;
  const hasStory = Boolean(deepMeta()) || isLegacyAgentic();
  $("methodhead").innerHTML = inner(sectionHead(++step, "Yöntemler",
    `Bu doküman ${NUMS[docArms().length] || docArms().length} yöntemle parçalandı.`));
  renderMethods();
  renderResults({step: hasStory ? ++step : null});
  $("readerhead").innerHTML = inner(sectionHead(++step, "Parçaları karşılaştır",
    "Aynı sayfa, seçtiğiniz yöntemlerin kesimleriyle yan yana. Renkli çizgi bir parçanın başladığı yerdir; sarı şerit, yöntemlerin farklı karar verdiği noktayı gösterir."));
  renderLanePicker();
  renderNavigator();
  renderLanes();
  renderPresDetail();
}

// The comparison itself: one row per canonical unit, one column per method.
// A row carries the boundary marks of every lane at the same height, so a cut
// that exists in one method and not another needs no explanation.
function renderLanes(){
  const lanes = laneList();
  const units = pageUnits(state.page);
  const cols = `grid-template-columns:repeat(${lanes.length},minmax(0,1fr))`;
  const marks = {};
  for (const arm of lanes) marks[arm] = boundaryPositions(units, arm);
  const diffs = laneDiffs();
  const diffBefore = new Map(diffs.map(d => [d.before, d]));
  const expansion = state.contShow && state.selChunk !== null ? simulateExpansion(SA(), state.selChunk) : null;
  const expMembers = expansion ? new Set(expansion.members) : null;

  let out = `<div class="lanes"><div class="head" style="${cols}">` + lanes.map(arm => {
    const data = D().arms[arm];
    return `<div><span class="dot" style="width:9px;height:9px;border-radius:3px;background:${LANE_COLOR[arm] || "#9aa3ad"}"></span>
      ${esc(modeName(arm).top)}<span class="n">${data.chunks.length} parça${data.sq && data.sq.token_count ? " · medyan " + fmt(data.sq.token_count.median, 0) + " tok" : ""}</span></div>`;
  }).join("") + `</div>`;

  for (let k = 0; k < units.length; k++) {
    const unit = units[k];
    const point = diffBefore.get(unit.i);
    if (point) {
      out += `<div class="rowmark" data-diff="${esc(unit.i)}"><b>Yöntemler ayrışıyor</b>` +
        `<span>${esc(point.cut.map(a => modeName(a).top).join(", "))} burada yeni parça açıyor;` +
        ` ${esc(point.kept.map(a => modeName(a).top).join(", "))} aynı parçada devam ediyor.</span></div>`;
    }
    out += `<div class="row" style="${cols}">` + lanes.map(arm => {
      const data = D().arms[arm];
      const at = data.m[unit.i];
      let cls = at === undefined ? "" : (at % 2 === 0 ? "tintA" : "tintB");
      if (at !== undefined && selArm() === arm && state.selChunk === at) cls += " sel";
      if (at !== undefined && state.contShow && expMembers && selArm() === arm && expMembers.has(at)) cls += " sel";
      const mark = marks[arm][k];
      let cut = "";
      if (mark !== null) {
        const chunk = data.chunks[mark];
        const isCont = chunk.cp !== null && chunk.cp !== undefined;
        const why = isCont ? (CONT_LABELS[chunk.rs] || "önceki parçanın devamı") : (REASONS[chunk.rs] || {label: chunk.rs}).label;
        cut = `<div class="cut ${arm === "agentic" ? "deepcut" : ""} ${isCont ? "techcut" : ""}">
          <button data-chunk="${mark}" data-arm="${arm}">Parça ${chunk.num}</button>
          <span class="why">${chunk.n} tok · ${esc(why)}</span></div>`;
      }
      return `<div class="cell ${cls}" data-uid="${esc(unit.i)}" data-arm="${arm}"${at !== undefined ? ` data-uchunk="${at}"` : ""}>${cut}<div class="body">${unitHtml(unit)}</div></div>`;
    }).join("") + `</div>`;
  }
  $("prespage").innerHTML = out + `</div>`;
  bindReader($("prespage"));
}


// A selection belongs to the column it was made in. In the side-by-side view
// that is not always the left one, and moving state.arm to follow the click
// used to collapse the comparison the reader had just opened.
// A selection belongs to the lane it was made in, so clicking the right-hand
// method inspects that method rather than switching the whole screen to it.
function bindReader(root){
  const pick = (arm, idx) => { state.selArm = arm || state.arm; state.selChunk = idx; renderPresDetail();
    root.querySelectorAll(".cell").forEach(c => c.classList.toggle("sel",
      c.dataset.arm === state.selArm && Number(c.dataset.uchunk) === state.selChunk)); };
  root.querySelectorAll(".cut button[data-chunk]").forEach(el => {
    el.onclick = e => { e.stopPropagation(); pick(el.dataset.arm, Number(el.dataset.chunk)); };
  });
  root.querySelectorAll(".cell[data-uchunk]").forEach(el => {
    el.onclick = () => pick(el.dataset.arm, Number(el.dataset.uchunk));
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
  if (!laneList().includes(state.arm)) setLanes(laneList().concat([state.arm]));
  const chunk = D().arms[state.arm].chunks[idx];
  state.selArm = state.arm;
  state.selChunk = idx;
  state.mode = "presentation";
  if (chunk.pg.length) state.page = chunk.pg[0];
  render();
  const el = document.querySelector(`.cell.sel`);
  if (el) el.scrollIntoView({block:"center"});
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
  const box = $("presdetail");
  const arm = selArm();
  const armData = SA();
  const armNote = armNoteFor(arm);
  if (state.selChunk === null || !armData.chunks[state.selChunk]) {
    box.innerHTML = `<h3>Parça detayı</h3><div class="empty">Bir parça şeridine ya da metne tıklayın: o sınırın neden orada olduğunu burada anlatırız.</div><div class="arminfo">${esc(armNote)}</div>`;
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
  if (expandable) expLine = `Evet — ${expansion.members.map(i => "Parça " + armData.chunks[i].num).join(" + ")} birlikte gelir (${expansion.total} token, bütçe ${expansion.budget}).`;
  else if (budgetNeighbor) expLine = `Hayır — komşu devam parçası bağlam bütçesine (${expansionBudget()} token) sığmıyor.`;
  else if (hasLink) expLine = "Hayır — komşu sınır bir bölüm sınırı, boyut kesimi değil.";
  else expLine = "Hayır — bu parça kendi bölümünün sonunda; devam bağlantısı yok.";

  let deepBlock = "";
  const d = chunk.dec;
  if (arm === "agentic" && isDeepArm("agentic")) {
    const st = sectionStory(chunk.si);
    let sent = "";
    if (d) {
      if (d.status === "kept") sent = d.llm_reverted ? `Bu sınır Standard'ın sınırıyla aynı. Model burada farklı bir sınır önerdi, ancak öneri iki ayrı sırada denenince <b>tutmadı</b> (${esc(d.llm_reverted === "order_dependent" ? "cevap sunum sırasına göre değişti" : d.llm_reverted === "base_preferred" ? "model kural sınırını tercih etti" : d.llm_reverted)}); kural sınırı korundu.` : "Bu sınır Standard'ın sınırıyla aynı: ne kalite kuralı ne model değişiklik gerektiren bir şey buldu.";
      else if (d.status === "det_moved") sent = `Kalite kuralı bu sınırı taşıdı${(d.removed_smells || []).length ? ": Standard'ın kesimi <b>" + esc((d.removed_smells || []).map(s => SMELL_TEXT[s] || s).join(", ")) + "</b> üretiyordu; yeni kesim bu kusuru taşımıyor" : " (çok kısa parçalar birleşti)"}. Modelsiz, tekrarlanabilir karar.` + (d.llm_reverted ? " Model bu bölgede başka bir sınır önerdi, doğrulamadan geçmedi." : "");
      else if (d.status === "llm_accepted") sent = "Bu sınırı model önerdi. Öneri iki ayrı sunum sırasında da tercih edildiği için kabul edildi, ardından kalite kurallarından yeniden geçti — boyut, kapsama ve yapısal problem sayaçlarının tamamı yeniden kontrol edildi.";
      else if (d.status === "ceiling") sent = "Zorunlu kesim: bu parça tek bir tablonun ya da paragrafın ortasından başlıyor, çünkü o blok tek başına bütçeden büyük. Hiçbir bölümleme yöntemi bu kesimden kaçınamaz.";
    }
    deepBlock = `<div class="reason-sent deep"><b>Deep Analysis kararı.</b> ${sent || "Bu chunk bölüm başlangıcında; kesim kararı bölüm sınırının kendisi."}</div>` +
      (st ? `<details class="adv"><summary>Teknik detay — bölüm ${st.i}: ${esc(SECTION_STATUS[st.st] || st.st)}</summary><pre>${esc(JSON.stringify({
        section: st.h, status: st.st, llm_consulted: st.cons, reverted: st.rv, verdict_tiered: st.vt,
        standard_cuts_after: st.std, deterministic_cuts_after: st.det, final_cuts_after: st.fin,
        smells_standard: st.sm.standard, smells_deep: st.sm.deep,
        change_groups: st.gr, llm_proposals: st.pr, this_boundary: d || null
      }, null, 1))}</pre></details>`: "");
  } else if (arm === "structure-only" && d && d.status === "std_changed") {
    deepBlock = `<div class="reason-sent deep"><b>Deep Analysis bu kesimi değiştirdi.</b> ${(d.removed_smells || []).length ? "Standard'ın bu kesimi <b>" + esc((d.removed_smells || []).map(s => SMELL_TEXT[s] || s).join(", ")) + "</b> üretiyordu." : "Boyut dengesi için taşındı/birleştirildi."} Karar ${d.origin === "llm" ? "model önerisi ve iki sıralı doğrulamayla" : "deterministik kalite kuralıyla"} verildi. Deep Analysis'i seçip aynı sayfayı açarak yeni sınırı görebilirsiniz.</div>`;
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
    ${state.contShow ? `<div class="reason-sent"><b>Devam zinciri.</b> ${esc(expLine)}</div>` : ""}
    ${deepBlock}
    <div class="detail-links" style="margin-top:10px"><button data-showchunk="1">Parça metnini aç</button></div>
    <details class="adv"><summary>Teknik alanlar</summary><dl class="kv" style="margin-top:8px">
      <dt>Devam zinciri</dt><dd>${esc(expLine)}</dd>
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
      <dt>Yöntem</dt><dd>${esc(modeName(state.chat.arm).top)}${state.chat.arm === "agentic" && dm ? ` · ${dm.chunkCount.deep} chunk` : ""}</dd>
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
  $("queryhead2").innerHTML = inner(sectionHead(null, "Sorgu",
    (D().gold || []).length
      ? "Kendi sorunuzu sorun ya da ölçüm sorularında yöntemlerin doğru parçayı kaçıncı sırada getirdiğini görün."
      : "Bu dokümana bir soru sorun; cevabın hangi parçalardan geldiği altında listelenir."));
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
      setLanes([b.dataset.goto]);
      const evidence = g.ev.length ? unitById(g.ev[0]) : null;
      state.page = (evidence && evidence.p) || g.pg[0] || D().pages[0];
      render();
      g.ev.forEach(id => { const el = document.querySelector(`.cell[data-uid="${id}"]`); if (el) el.classList.add("evflash"); });
      const first = document.querySelector(".evflash");
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
    <label><input type="checkbox" id="dbgbig" ${f.onlyBig ? "checked" : ""}> tek başına bütçeden büyük birimler${info("Bu birimin kendisi hard cap'ten büyük: hangi yöntem kullanılırsa kullanılsın ortasından kesilmek zorunda. Kalan yapısal problemlerin bir kısmı buradan gelir.")}</label>
    <label><input type="checkbox" id="dbgpf" ${f.onlyPf ? "checked" : ""}> ayrıştırıcı notu olan birimler${info("PDF'ten metin çıkarılırken kaydedilen gözlem: birleşmiş satır, kopmuş tablo başlığı gibi. Bölümleme yönteminin değil, kaynağın özelliğidir.")}</label>
    <span class="muted">· sayfa ${state.page} · dokümanda ${D().parser.count} ayrıştırıcı notu</span>`;
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
  $("dbghead").innerHTML = inner(sectionHead(null, "Debug",
    "Her kart bir <b>birim</b>: ayrıştırıcının çıkardığı tek bir başlık, paragraf ya da tablo. Altındaki satırlar o birimin her yöntemde hangi parçaya düştüğünü gösterir; karta tıklayın, sağdaki panel açılsın."));
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
  state.selArm = state.arm; state.lanes = null; state.page = null;
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
  openModal("RAG Console", facts, body, actions);
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
function render(){
  syncBar();
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
