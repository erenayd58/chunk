"""The Viewer v3 page: markup, styles and behaviour, as one template string.

Kept apart from :mod:`amsc.viewer_v3` so the loader reads like Python and the
page reads like a page. ``__VIEWER_DATA__`` is replaced with the JSON payload
at build time; nothing else is templated. The page consumes the
``viewer_v2.load_corpus`` document shape unchanged -- embedded documents at
build time, live documents at runtime through the existing server relays --
and renders one thing above all: where chunks start and end, on the document
itself.
"""

TEMPLATE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chunk Viewer v3</title>
<style>
:root{
  --bg:#f1f2f5; --paper:#ffffff; --field:#e9ebef;
  --ink:#161e2b; --ink2:#3a4556; --mut:#6c7788; --faint:#98a1b0;
  --line:#dcdfe6; --line2:#c3c9d4; --markc:#a8b1c0;
  --accent:#3f608f; --accent-ink:#32517c; --accent-soft:#e1e9f4;
  --deep:#6d34c9; --deep-soft:#efe7fb;
  --warn:#a16207; --bad:#b3261e; --ok:#1d9a5b;
  --k0:#e9f0fa; --k0h:#dde8f7; --k0s:#ccddf3;
  --k1:#eaf4ee; --k1h:#dcede3; --k1s:#cbe3d6;
  --k2:#f7f1e4; --k2h:#f1e8d2; --k2s:#e9dcbd;
  --sans:"Bahnschrift","Segoe UI Variable Text","Segoe UI",Inter,system-ui,sans-serif;
  --serif:Georgia,"Iowan Old Style",Cambria,"Times New Roman",serif;
  --r:2px; --barh:58px;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--bg);color:var(--ink);font:14px/1.5 var(--sans)}
button{font:inherit;color:inherit;background:none;border:none;cursor:pointer;text-align:left}
button:disabled{cursor:default}
button:focus-visible,select:focus-visible,textarea:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
select{font:inherit;color:inherit;border:1px solid var(--line2);border-radius:var(--r);background:var(--field);padding:7px 9px}
[hidden]{display:none!important}

/* ---- corner registration marks ------------------------------------------ */
.cm{position:absolute;width:13px;height:13px;pointer-events:none;z-index:2;
  background:linear-gradient(var(--markc) 0 0) center/13px 1px no-repeat,
             linear-gradient(var(--markc) 0 0) center/1px 13px no-repeat}
.cm.tl{top:-7px;left:-7px}.cm.tr{top:-7px;right:-7px}
.cm.bl{bottom:-7px;left:-7px}.cm.br{bottom:-7px;right:-7px}

/* ---- top bar ------------------------------------------------------------ */
#bar{position:sticky;top:0;z-index:40;height:var(--barh);display:flex;align-items:center;gap:14px;
  padding:0 20px;background:var(--paper);border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:8px;font-weight:700;font-size:14px;letter-spacing:.14em;
  white-space:nowrap;text-transform:uppercase}
.brand em{font-style:normal;font-weight:600;font-size:10px;letter-spacing:.08em;color:var(--mut);
  border:1px solid var(--line2);padding:2px 6px;border-radius:var(--r)}
.path{display:flex;align-items:center;gap:4px;min-width:0;padding-left:14px;border-left:1px solid var(--line)}
.pick{display:flex;flex-direction:column;gap:2px;padding:4px 10px;border-radius:var(--r);min-width:0}
.pick:hover:not(:disabled){background:var(--field)}
.pick .k{font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint)}
.pick .v{font-size:13px;font-weight:600;color:var(--ink2);white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;max-width:230px}
.pick.unset .v{color:var(--accent)}
.pick:disabled .v{color:var(--faint);font-weight:500}
.sep{color:var(--line2);font-size:14px}
#chips{display:flex;align-items:center;gap:6px;margin-left:8px;flex-wrap:nowrap}
.chip{display:flex;align-items:baseline;gap:6px;padding:6px 12px;border:1px solid var(--line2);border-radius:var(--r);
  font-size:12px;font-weight:600;color:var(--ink2);white-space:nowrap;background:var(--paper)}
.chip:hover{background:var(--field)}
.chip.on{background:var(--accent-soft);border-color:var(--accent);color:var(--accent-ink)}
.chip .ord{font-size:10px;font-weight:700;color:#fff;background:var(--accent);border-radius:var(--r);
  width:14px;height:14px;line-height:14px;text-align:center;align-self:center}
.chip .note{font-size:10px;font-weight:500;color:var(--mut);font-style:italic}
#bar .right{margin-left:auto;display:flex;align-items:center;gap:12px}
#nav{display:flex;align-items:center;gap:6px;white-space:nowrap}
#nav .grp{display:flex;align-items:center;gap:4px}
#nav button{padding:6px 10px;border:1px solid var(--line2);border-radius:var(--r);color:var(--ink2);
  font-size:12px;background:var(--paper)}
#nav button:hover:not(:disabled){background:var(--field)}
#nav button:disabled{color:var(--faint);border-color:var(--line)}
#nav .lbl{font-size:10px;color:var(--mut);letter-spacing:.12em;text-transform:uppercase}
#nav .vr{width:1px;height:22px;background:var(--line);margin:0 6px}
#dPos{font-size:12px;color:var(--mut);min-width:44px;text-align:center;font-variant-numeric:tabular-nums}
#tabs{display:flex;margin-left:12px;border:1px solid var(--line2);border-radius:var(--r);overflow:hidden}
#tabs button{padding:7px 16px;font-size:12.5px;font-weight:600;color:var(--ink2);background:var(--paper)}
#tabs button + button{border-left:1px solid var(--line2)}
#tabs button.on{background:var(--accent);color:#fff}
#tabs button:hover:not(.on){background:var(--field)}
#pill{display:flex;align-items:center;gap:8px;padding:7px 12px;border:1px solid var(--line2);border-radius:var(--r);
  font-size:10.5px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--ink2);
  white-space:nowrap;background:var(--paper)}
#pill:hover{background:var(--field)}
#pill .dot{width:7px;height:7px;background:var(--faint)}
#pill.on .dot{background:var(--ok)}

/* ---- menus -------------------------------------------------------------- */
#layer{position:fixed;inset:0;z-index:60}
#menu{position:fixed;min-width:290px;max-width:420px;max-height:calc(100vh - 90px);overflow:auto;
  background:var(--paper);border:1px solid var(--line2);border-radius:var(--r);
  box-shadow:0 10px 30px rgba(22,30,43,.12);padding:4px}
#menu .sect{padding:10px 12px 5px;font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint)}
#menu .it{display:block;width:100%;padding:9px 12px;border-radius:var(--r)}
#menu .it:hover:not(:disabled){background:var(--field)}
#menu .it:disabled{opacity:.55}
#menu .it .n{font-size:13px;font-weight:600;color:var(--ink);display:flex;align-items:center;gap:8px}
#menu .it.cur .n::after{content:"✓";color:var(--accent);font-size:12px}
#menu .it .m{font-size:11.5px;color:var(--mut);margin-top:1px}
#menu .it .m.err{color:var(--bad)}
#menu .quiet{padding:9px 12px;font-size:12px;color:var(--mut)}

/* ---- stage / heroes ----------------------------------------------------- */
#stage{min-height:calc(100vh - var(--barh))}
.kicker{font-size:11px;font-weight:700;letter-spacing:.22em;text-transform:uppercase;color:var(--accent)}
.hero{max-width:640px;margin:0 auto;padding:12vh 24px 60px;text-align:center}
.hero h1{margin-top:10px;font-size:34px;line-height:1.15;font-weight:700;letter-spacing:-.01em;color:var(--ink)}
.hero>p{margin-top:12px;font-size:14.5px;line-height:1.6;color:var(--mut)}
.steps{display:flex;justify-content:center;gap:26px;margin-top:34px}
.steps .st{display:flex;align-items:center;gap:8px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--mut)}
.steps .st b{display:inline-flex;width:20px;height:20px;border:1px solid var(--line2);border-radius:var(--r);
  align-items:center;justify-content:center;font-size:11px;font-weight:700;color:var(--ink2)}
.steps .st.done b{background:var(--accent);border-color:var(--accent);color:#fff}
.steps .st.now b{border-color:var(--accent);color:var(--accent)}
.steps .st.now{color:var(--ink2)}
.primary{display:inline-block;margin-top:34px;padding:11px 28px;border-radius:var(--r);background:var(--accent);
  color:#fff;font-weight:600;font-size:13px;letter-spacing:.04em}
.primary:hover{background:var(--accent-ink)}
.herolist{max-width:560px;margin:28px auto 0;text-align:left;background:var(--paper);border:1px solid var(--line2)}
.herolist .it{display:block;width:100%;padding:12px 16px}
.herolist .it + .it{border-top:1px solid var(--line)}
.herolist .it:hover:not(:disabled){background:var(--field)}
.herolist .it:disabled{opacity:.55}
.herolist .n{font-size:13.5px;font-weight:600}
.herolist .m{font-size:11.5px;color:var(--mut);margin-top:1px}
.herolist .m.err{color:var(--bad)}
.mcards{max-width:600px;margin:28px auto 0;text-align:left;display:flex;flex-direction:column;gap:10px}
.mcard{background:var(--paper);border:1px solid var(--line2);border-radius:var(--r);padding:14px 18px}
.mcard:hover{border-color:var(--accent)}
.mcard .n{font-size:14px;font-weight:700;display:flex;align-items:baseline;gap:8px}
.mcard .n .note{font-size:10.5px;font-weight:500;font-style:italic;color:var(--mut)}
.mcard .s{font-size:12.5px;color:var(--mut);margin-top:3px;line-height:1.5}
.spin{display:inline-block;width:12px;height:12px;border:2px solid var(--line2);border-top-color:var(--accent);
  border-radius:50%;animation:spin .8s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}

/* ---- the sheet (İncele) ------------------------------------------------- */
#wrap{overflow-x:auto;padding:0 24px}
.sheet{position:relative;background:var(--paper);border:1px solid var(--line2);border-radius:var(--r);
  margin:28px auto 90px;padding:40px 54px 64px}
.sheet.c1{max-width:820px}
.sheet.c2{max-width:1280px;min-width:900px}
.sheet.c3{max-width:1700px;min-width:1280px}
.shead{display:flex;justify-content:space-between;align-items:baseline;padding-bottom:12px;margin-bottom:8px;
  border-bottom:1px solid var(--line)}
.shead .dl{font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--mut);font-weight:700;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.shead .pl{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);white-space:nowrap;
  font-variant-numeric:tabular-nums}
.board{display:grid;column-gap:46px;row-gap:0}
.grow{display:contents}
.gut{position:relative}
.chead{position:sticky;top:var(--barh);z-index:5;background:var(--paper);padding:12px 0 9px;margin-bottom:6px;
  border-bottom:1px solid var(--line);font-size:10px;font-weight:700;letter-spacing:.18em;
  text-transform:uppercase;color:var(--mut)}
.chead .note{margin-left:8px;font-weight:500;font-style:italic;text-transform:none;letter-spacing:0;color:var(--faint)}
.cont{font-size:11px;color:var(--faint);font-style:italic;padding:10px 0 2px}
.cell{position:relative;padding:3px 10px;min-width:0}
.cell .tx{font-family:var(--serif);font-size:14.5px;line-height:1.68;color:var(--ink)}
.c1 .cell .tx{font-size:16px;line-height:1.76}
.cell .tx.pre{white-space:pre-line}
.cell .tx table{border-collapse:collapse;font:12.5px/1.5 var(--sans);margin:4px 0;max-width:100%}
.cell .tx td,.cell .tx th{border:1px solid var(--line);padding:3px 8px;text-align:left}
.cell .tx ul,.cell .tx ol{padding-left:20px}
.cell .hx{font-family:var(--sans);font-weight:700;color:var(--ink);line-height:1.35}
.cell .hx.l1{font-size:19px;margin-top:2px}
.cell .hx.l2{font-size:16.5px}
.cell .hx.l3,.cell .hx.l4{font-size:14.5px}
.c1 .cell .hx.l1{font-size:21px}
.c1 .cell .hx.l2{font-size:18px}
.cell.ghost>div{opacity:.32}
.cell.cb{margin-top:20px;border-top:1px solid var(--line2);padding-top:17px}
.cell.cb .bl{position:absolute;top:-8px;right:0;background:var(--paper);padding:0 0 0 8px;
  font:10.5px/16px var(--sans);letter-spacing:.04em;color:var(--mut);white-space:nowrap;max-width:100%;
  overflow:hidden;text-overflow:ellipsis}
.cell.cb .bl b{font-weight:700;color:var(--ink2);font-variant-numeric:tabular-nums}
.cell.cb .bl.deep::before{content:"";display:inline-block;width:6px;height:6px;background:var(--deep);
  margin-right:6px;vertical-align:1px}
.cell.k0{background:var(--k0)} .cell.k1{background:var(--k1)} .cell.k2{background:var(--k2)}
.cell.k0.hov{background:var(--k0h)} .cell.k1.hov{background:var(--k1h)} .cell.k2.hov{background:var(--k2h)}
.cell.k0.sel{background:var(--k0s)} .cell.k1.sel{background:var(--k1s)} .cell.k2.sel{background:var(--k2s)}
.cell.sel{box-shadow:inset 3px 0 0 var(--accent)}
.cell.ghost{background:transparent}
.gut .d{position:absolute;top:24px;left:50%;width:7px;height:7px;transform:translateX(-50%) rotate(45deg);
  background:var(--paper);border:1.5px solid var(--accent)}
.gut .d.fl{animation:flash 1.1s ease 2}
@keyframes flash{0%,100%{box-shadow:0 0 0 0 rgba(63,96,143,0)}45%{box-shadow:0 0 0 6px rgba(63,96,143,.25)}}
.emptypg{padding:60px 0;text-align:center;color:var(--faint);font-size:13px}

/* ---- sorgu -------------------------------------------------------------- */
.qwrap{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:32px;align-items:start;
  max-width:1500px;margin:34px auto 90px;padding:0 28px}
.qmaincol{min-width:0}
.ql1{margin-top:8px;font-size:36px;line-height:1.1;font-weight:700;letter-spacing:-.01em}
.qsub{margin-top:10px;font-size:13.5px;line-height:1.6;color:var(--mut);max-width:600px}
.qpanel{position:relative;border:1px solid var(--line2);background:var(--paper);padding:22px 24px 20px;margin-top:26px}
.qlab{display:block;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--mut);margin-bottom:7px}
#qIn{width:100%;resize:vertical;font:14.5px/1.55 var(--sans);color:var(--ink);padding:12px 14px;
  border:1px solid var(--line2);border-radius:var(--r);background:var(--field);min-height:96px}
#qIn:focus{outline:2px solid var(--accent);outline-offset:0;background:#fff}
.qctl{display:flex;align-items:flex-end;gap:20px;margin-top:16px;flex-wrap:wrap}
.qf{display:flex;flex-direction:column;gap:6px;min-width:0}
.qf span{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--mut)}
.qf select{min-width:170px;max-width:340px}
.qbottom{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-top:18px;
  padding-top:16px;border-top:1px solid var(--line)}
.qmths{min-width:0}
.qmchips{display:flex;flex-wrap:wrap;gap:6px}
.mchip{padding:7px 14px;border:1px solid var(--line2);border-radius:var(--r);font-size:12px;font-weight:600;
  color:var(--ink2);background:var(--paper)}
.mchip:hover{background:var(--field)}
.mchip.on{background:var(--accent-soft);border-color:var(--accent);color:var(--accent-ink)}
.qmnote{font-size:11px;color:var(--faint)}
.qgo{margin:0;padding:10px 36px}
.qgo:disabled{background:var(--line2)}
.qsect2{margin-top:32px;font-size:10.5px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:var(--ink2)}
.qsug{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px;margin-top:12px}
.qsug button{border:1px solid var(--line2);background:var(--paper);padding:13px 16px;font-size:13px;font-weight:600;
  color:var(--ink);border-radius:var(--r);line-height:1.4}
.qsug button:hover{border-color:var(--accent)}
#qOut{margin-top:26px}
.qnote{font-size:13px;color:var(--mut);line-height:1.6;padding:14px 16px;background:var(--paper);
  border:1px solid var(--line);border-radius:var(--r)}
.qnote.warn{background:#fbf4e4;border-color:#eadfc0;color:#7c5a11}
.qnote.err{background:#fbeeed;border-color:#f0d4d2;color:var(--bad)}
.qans{font:15px/1.7 var(--serif);color:var(--ink);padding:4px 2px 0}
.qans.sm{font-size:13.5px;line-height:1.62}
.qsect{font-size:10.5px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--mut);
  margin:22px 0 6px;display:flex;align-items:baseline;gap:10px}
.qsect .ov{font-weight:500;letter-spacing:0;text-transform:none;font-size:11.5px;color:var(--faint)}
.qsrc{border-top:1px solid var(--line)}
.qsrc:last-of-type{border-bottom:1px solid var(--line)}
.qsrc.used .qsrchead{box-shadow:inset 3px 0 0 var(--accent)}
.qsrchead{display:flex;align-items:baseline;gap:12px;padding:11px 10px;cursor:pointer}
.qsrchead:hover{background:var(--field)}
.slab{font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--accent-ink);border:1px solid var(--accent);
  border-radius:var(--r);padding:1px 6px}
.sinfo{font-size:12.5px;font-weight:600;color:var(--ink2);white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;min-width:0;flex:1}
.smeta{font-size:11px;color:var(--faint);white-space:nowrap}
.qsrcbody{padding:4px 12px 14px;border-top:1px solid var(--line);background:var(--paper)}
.qtxt{font:13px/1.62 var(--serif);color:var(--ink2);max-height:240px;overflow:auto;padding-top:9px;white-space:pre-line}
.qjump{margin-top:10px;font-size:12px;color:var(--accent-ink);font-weight:600}
.qjump:hover{text-decoration:underline}
.qcmpcol{padding:16px 0 20px;border-bottom:1px solid var(--line)}
.qcmpcol:last-child{border-bottom:0}
.qmini{margin-top:10px;display:flex;flex-direction:column;gap:2px}
.qminisrc{font-size:12px;color:var(--mut)}
button.qminisrc{cursor:pointer;padding:5px 8px;margin:0 -8px;border-radius:var(--r);width:calc(100% + 16px)}
button.qminisrc:hover{background:var(--field);color:var(--ink)}
.qhist{margin-top:12px}
.qhrow{display:flex;align-items:baseline;gap:16px;width:100%;padding:10px 8px;border-top:1px solid var(--line);font-size:13px}
.qhrow:last-child{border-bottom:1px solid var(--line)}
.qhrow:hover{background:var(--field)}
.qhrow .hq{flex:1;min-width:0;font-weight:600;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.qhrow .hm{color:var(--ink2);white-space:nowrap;width:150px}
.qhrow .hn{color:var(--mut);white-space:nowrap;width:70px;font-variant-numeric:tabular-nums}
.qhrow .ht{color:var(--faint);white-space:nowrap;font-size:12px}
.qgold{margin-top:32px}
.qgold summary{cursor:pointer;font-size:10.5px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;
  color:var(--ink2);list-style:none;user-select:none}
.qgold summary::before{content:"▸ ";color:var(--faint)}
.qgold[open] summary::before{content:"▾ ";color:var(--faint)}
.qhint2{font-weight:500;color:var(--faint);font-size:11px;margin-left:10px;letter-spacing:.02em;text-transform:none}
.qgoldwrap{overflow-x:auto;margin-top:10px}
.qgold table{border-collapse:collapse;width:100%;font-size:12px}
.qgold th{font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);text-align:left;
  padding:6px 10px;border-bottom:1px solid var(--line2);white-space:nowrap}
.qgold td{padding:7px 10px;border-bottom:1px solid var(--line);color:var(--ink2);vertical-align:top;
  font-variant-numeric:tabular-nums}
.qgold td.q{cursor:pointer;max-width:520px}
.qgold td.q:hover{color:var(--accent-ink)}
.qgold td.pg{white-space:nowrap;color:var(--faint)}
.qgold td.hit{color:var(--ok);font-weight:700}
.qgold td.miss{color:var(--faint)}
.qside{position:sticky;top:calc(var(--barh) + 34px)}
.qcard{position:relative;border:1px solid var(--line2);padding:18px 20px 20px}
.qcard h3{font-size:11px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:var(--ink)}
.livechip{position:absolute;top:12px;right:12px;font-size:10px;font-weight:600;color:var(--accent-ink);
  background:var(--accent-soft);border:1px solid var(--accent);border-radius:var(--r);padding:2px 8px}
.livechip.off{color:var(--mut);background:var(--field);border-color:var(--line2)}
.qcf{margin-top:14px}
.qcf select{width:100%;max-width:none}
.qkv{margin-top:4px}
.qkv dt{font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);margin-top:12px;
  padding-top:12px;border-top:1px solid var(--line)}
.qkv dd{font-size:12.5px;color:var(--ink2);overflow-wrap:anywhere;margin-top:2px;line-height:1.5}
.qoff{margin-top:12px;font-size:11.5px;color:var(--faint);font-style:italic}
@media (max-width:1020px){.qwrap{grid-template-columns:1fr}.qside{position:static}}

/* ---- home / overview ---------------------------------------------------- */
.home{max-width:1500px;margin:34px auto 90px;padding:0 28px}
.hsub{margin-top:10px;font-size:13.5px;color:var(--mut);max-width:660px;line-height:1.6}
.statrow{position:relative;display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line2);
  background:var(--paper);margin-top:26px}
.stat{padding:16px 20px 14px}
.stat + .stat{border-left:1px solid var(--line)}
.stat .k{font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint)}
.stat .v{font-size:27px;font-weight:700;line-height:1.2;margin-top:4px;font-variant-numeric:tabular-nums}
.stat .s{font-size:11px;color:var(--mut);margin-top:2px}
.hpanels{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:30px;align-items:start}
.hpanel{position:relative;border:1px solid var(--line2);background:var(--paper);padding:16px 18px 8px}
.hphead{display:flex;align-items:baseline;justify-content:space-between;gap:10px;padding-bottom:10px;
  border-bottom:1px solid var(--line)}
.hphead .t{font-size:10.5px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:var(--ink2)}
.hphead .r{font-size:11px;color:var(--faint)}
.hphead button{font-size:11px;color:var(--accent-ink);font-weight:600}
.hphead button:hover{text-decoration:underline}
.hrow{display:flex;align-items:baseline;gap:14px;width:100%;padding:11px 4px;border-top:1px solid var(--line);font-size:13px}
.hrow:first-of-type{border-top:0}
.hrow:hover{background:var(--field)}
.hrow .n{flex:1;min-width:0;font-weight:600;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hrow .m{font-size:11.5px;color:var(--mut);white-space:nowrap}
.schip{font-size:10px;font-weight:600;border-radius:var(--r);padding:2px 8px;white-space:nowrap}
.schip.ok{color:var(--accent-ink);background:var(--accent-soft);border:1px solid var(--accent)}
.schip.run{color:var(--ink2);background:var(--paper);border:1px solid var(--line2)}
.schip.wait{color:var(--mut);background:var(--field);border:1px solid var(--line2)}
.schip.err{color:var(--bad);background:#fbeeed;border:1px solid #f0d4d2}
.hquiet{padding:12px 4px;font-size:12px;color:var(--mut)}
@media (max-width:1020px){.hpanels{grid-template-columns:1fr}.statrow{grid-template-columns:1fr 1fr}}

/* ---- benchmark ---------------------------------------------------------- */
.bench{max-width:1500px;margin:34px auto 90px;padding:0 28px}
.bhead{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap}
.bchips{display:flex;gap:8px;flex-wrap:wrap;padding-bottom:6px}
.bchip{font-size:11px;font-weight:600;color:var(--ink2);border:1px solid var(--line2);border-radius:var(--r);
  padding:4px 10px;background:var(--paper);white-space:nowrap}
.bsec{display:flex;align-items:baseline;gap:12px;margin-top:46px}
.bsec .no,.bdetails .no{font-size:11px;font-weight:700;color:var(--faint);letter-spacing:.1em}
.bsec h2,.bdetails h2{font-size:20px;font-weight:700;letter-spacing:-.01em;display:inline}
.bsec .bn{font-size:11.5px;color:var(--faint)}
.statrow.b{margin-top:18px}
.bgrid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:28px;margin-top:22px;align-items:start}
@media (max-width:1020px){.bgrid{grid-template-columns:1fr}}
.btable{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:2px}
.btable th{font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);text-align:right;
  padding:8px 10px;border-bottom:1px solid var(--line2);white-space:nowrap}
.btable th:first-child{text-align:left}
.btable td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:right;
  font-variant-numeric:tabular-nums;color:var(--ink2);white-space:nowrap}
.btable td:first-child{text-align:left;color:var(--ink);font-weight:600;white-space:normal}
.btable tr:last-child td{border-bottom:0}
.btable .tech{font-family:Consolas,Menlo,monospace;font-size:10.5px;color:var(--faint);font-weight:400;margin-left:8px}
.btable td.best::after{content:" ●";color:var(--accent);font-size:9px}
.btable tr.total td{border-top:1px solid var(--line2);font-weight:700;color:var(--ink)}
.btable td.good{color:var(--ok);font-weight:600}
.btable td.badv{color:var(--bad);font-weight:600}
.bkrow{display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:11px 4px;
  border-top:1px solid var(--line);font-size:13px}
.bkrow:first-of-type{border-top:0}
.bkrow .v{font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.claim{margin-top:24px;background:#1c2534;color:#c9d2e0;padding:18px 20px;border-radius:var(--r)}
.claim .t{font-size:10.5px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:#8b98ad;margin-bottom:8px}
.claim p{font-size:12.5px;line-height:1.62}
.bnote{margin-top:12px;font-size:12px;color:var(--mut);line-height:1.6;max-width:760px}
.bdetails{margin-top:46px}
.bdetails summary{list-style:none;cursor:pointer;display:flex;align-items:baseline;gap:12px;user-select:none}
.bdetails summary::-webkit-details-marker{display:none}
.bdetails .tog{font-size:11px;font-weight:600;color:var(--accent-ink)}

/* ---- debug -------------------------------------------------------------- */
.pipe{position:relative;display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--line2);
  background:var(--paper);margin-top:18px}
.pstep{padding:14px 16px 16px;position:relative}
.pstep + .pstep{border-left:1px solid var(--line)}
.pstep .pn{font-size:10px;font-weight:700;color:var(--faint);letter-spacing:.1em}
.pstep .pt{position:absolute;top:14px;right:16px;font-size:11px;color:var(--mut);font-variant-numeric:tabular-nums}
.pstep .nm{font-size:15px;font-weight:700;margin-top:10px}
.pstep .ds{font-size:11.5px;color:var(--mut);margin-top:3px;line-height:1.45}
.pstep.dim .nm{color:var(--mut)}
.pstep.dim .ds{color:var(--faint);font-style:italic}
@media (max-width:1020px){.pipe{grid-template-columns:1fr 1fr}}
.dfilters{display:flex;border:1px solid var(--line2);border-radius:var(--r);overflow:hidden;margin-left:auto}
.dfilters button{padding:6px 14px;font-size:12px;font-weight:600;color:var(--ink2);background:var(--paper)}
.dfilters button + button{border-left:1px solid var(--line2)}
.dfilters button.on{background:var(--accent);color:#fff}
.srcchip{font-size:10.5px;font-weight:600;border-radius:var(--r);padding:2px 9px;border:1px solid var(--line2);
  color:var(--ink2);background:var(--field);white-space:nowrap}
.srcchip.model{background:var(--paper);border-color:var(--accent);color:var(--accent-ink)}
.srcchip.rule{background:var(--accent-soft);border-color:#b9c9e6;color:var(--accent-ink)}
.srcchip.qc{background:var(--deep-soft);border-color:var(--deep);color:#4c2591}
.btable td.l{text-align:left;font-weight:400;color:var(--ink2);white-space:normal}
.res.ok{color:var(--ok);font-weight:600}
.res.no{color:var(--bad);font-weight:600}
.res.rv{color:var(--deep);font-weight:600}
.drow{cursor:pointer}
.drow:hover td{background:var(--field)}
.drow.openrow td{background:var(--field)}
.ddetail td{background:#f7f8fa;padding:12px 14px}
.ddetail .dg{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px 24px;text-align:left}
.ddetail .dg .k{font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);display:block;margin-bottom:2px}
.ddetail .dg .v2{font-size:12.5px;color:var(--ink2);font-weight:600;font-variant-numeric:tabular-nums;white-space:normal}
.ddetail .qjump{margin-top:0}
.dlog{background:#1c2534;color:#c9d2e0;padding:14px 16px;border-radius:var(--r);
  font:11.5px/1.85 Consolas,Menlo,monospace;overflow-x:auto}
.dlog .u{color:#8fb4e8}
.dlog .more{color:#8b98ad}

/* ---- popover ------------------------------------------------------------ */
#pop{position:fixed;z-index:70;width:312px;background:var(--paper);border:1px solid var(--line2);
  border-radius:var(--r);box-shadow:0 12px 32px rgba(22,30,43,.14);padding:14px 16px 12px}
#pop .t{font-size:13.5px;font-weight:700;display:flex;align-items:baseline;gap:7px}
#pop .t .mth{font-size:10px;font-weight:700;color:var(--mut);letter-spacing:.12em;text-transform:uppercase}
#pop .meta{margin-top:5px;font-size:12px;color:var(--mut)}
#pop .row{margin-top:9px;font-size:12.5px;line-height:1.5;color:var(--ink2)}
#pop .row .k{font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);display:block;margin-bottom:1px}
#pop .deepbx{margin-top:11px;padding:9px 11px;border:1px solid var(--deep);border-radius:var(--r);
  background:var(--deep-soft);font-size:12.5px;line-height:1.5;color:#4c2591}
#pop .deepbx b{font-weight:700}
#pop details{margin-top:11px;border-top:1px solid var(--line);padding-top:8px}
#pop summary{font-size:11px;color:var(--mut);cursor:pointer;list-style:none;user-select:none}
#pop summary::before{content:"▸ "}
#pop details[open] summary::before{content:"▾ "}
#pop dl{margin-top:6px;font-size:11.5px;color:var(--ink2);display:grid;grid-template-columns:auto 1fr;gap:2px 10px}
#pop dt{color:var(--faint)}
#pop dd{font-family:Consolas,Menlo,monospace;font-size:11px;overflow-wrap:anywhere}
#pop .ptxt{margin-top:10px;border-top:1px solid var(--line);padding-top:9px;
  font:12.5px/1.62 var(--serif);color:var(--ink2);max-height:min(46vh,300px);overflow:auto;white-space:pre-line}
#pop .pfoot{margin-top:10px;border-top:1px solid var(--line);padding-top:8px}
#pop .pfoot .qjump{margin-top:0}
</style>
</head>
<body>

<header id="bar">
  <div class="brand">Chunk Viewer<em>v3</em></div>
  <nav class="path">
    <button class="pick unset" id="kbBtn"><span class="k">Bilgi tabanı</span><span class="v">Seç</span></button>
    <span class="sep">/</span>
    <button class="pick" id="docBtn" disabled><span class="k">Doküman</span><span class="v">—</span></button>
    <div id="chips" hidden></div>
  </nav>
  <div id="tabs" hidden>
    <button data-t="home">Genel</button>
    <button data-t="incele">İncele</button>
    <button data-t="sorgu">Sorgu</button>
    <button data-t="debug">Debug</button>
    <button data-t="bench">Benchmark</button>
  </div>
  <div class="right">
  <button id="pill" hidden><span class="dot"></span><span id="pillTxt"></span></button>
  <div id="nav" hidden>
    <div class="grp" id="dGrp" hidden>
      <button id="dPrev" title="Önceki ayrışma">‹ Fark</button><span id="dPos"></span>
      <button id="dNext" title="Sonraki ayrışma">Fark ›</button>
      <span class="vr"></span>
    </div>
    <div class="grp">
      <button id="pPrev" title="Önceki sayfa">‹</button>
      <span class="lbl">Sayfa</span> <select id="pSel"></select> <span class="lbl" id="pTot"></span>
      <button id="pNext" title="Sonraki sayfa">›</button>
    </div>
  </div>
  </div>
</header>

<main id="stage"></main>
<div id="layer" hidden><div id="menu" role="menu"></div></div>
<div id="pop" hidden></div>

<script id="viewer-data" type="application/json">__VIEWER_DATA__</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("viewer-data").textContent);
const SERVED = /^https?:$/.test(location.protocol);
const $ = (id) => document.getElementById(id);
//: corner registration marks a framed panel wears (the design's signature)
const MARKS = '<i class="cm tl"></i><i class="cm tr"></i><i class="cm bl"></i><i class="cm br"></i>';

/* ---------------- registry: embedded docs + live docs -------------------- */
const REG = {};
(DATA.docOrder || []).forEach((id) => { REG["b:" + id] = DATA.docs[id]; });

const S = {
  kb: null,        // {kind:'builtin'|'live', id, name, raw?}
  docKey: null, doc: null,
  sel: [],         // arm keys, in pick order
  page: null,
  rowsAll: [], diffs: [], diffIdx: -1,
  open: null,      // {a, c} selected chunk
  prep: null,      // live doc being prepared: {id, name, status, error}
  mode: "home",    // 'home' | 'incele' | 'sorgu' | 'debug' | 'bench'
  dbg: { filter: "all", open: null },
  q: { text: "", arms: [], topk: null, busy: false,
       res: null, cmp: null, err: null, health: null, showGold: false },
};
let WS = null, wsAt = 0, pollTimer = null;

/* ---------------- small helpers ----------------------------------------- */
const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const mLabel = (a) => (DATA.methodLabels || {})[a] || a;
const mSummary = (a) => (DATA.methodSummaries || {})[a] || "";
/* What a method *is*, from the build-time registry: the page keys Deep
   Analysis behaviour on the deep flag and the baseline on its declared
   baseline, so a newly registered partition method needs no edit here. */
const mMeta = (a) => (DATA.methodMeta || {})[a] || {};
const isDeep = (a) => !!mMeta(a).deep;
const DEEP = (DATA.methodOrder || []).find(isDeep) || "agentic";
const BASE = mMeta(DEEP).baseline || "structure-only";
const fmtPages = (pg) => !pg || !pg.length ? "" : (pg.length === 1 ? "Sayfa " + pg[0] : "Sayfa " + pg[0] + "–" + pg[pg.length - 1]);
const secOf = (c) => (c.sd && c.sd.length ? c.sd.join(" › ") : (c.hh || null));

const REASON_SHORT = {
  doc_start: "Doküman başlangıcı", new_section: "Yeni bölüm", label_split: "Ara başlık",
  budget_split: "Boyut sınırı", md_size: "Boyut penceresi", md_heading: "Başlıkta kesildi",
  md_overlap: "Boyut penceresi",
};
const REASON_LONG = {
  doc_start: "Dokümanın ilk parçası.",
  new_section: "Yeni bir bölüm başladığı için burada yeni parça açıldı.",
  label_split: "Bölüm içindeki bir ara başlıkta yeni parça açıldı.",
  budget_split: "Bölüm token bütçesini aştığı için burada bölündü.",
  md_size: "Sabit boyut penceresi dolduğu için burada bölündü.",
  md_heading: "Boyut penceresi bir başlığa denk geldiği için burada bölündü.",
  md_overlap: "Sabit boyut penceresi doldu; parça, bağlam için önceki parçanın sonunu da taşır.",
};
const SMELLS = {
  orphan_label: "yalnız kalan başlık", lead_in_cut: "giriş cümlesinden sonra kesim",
  fragment_cut: "birim ortasında kesim", table_split: "bölünmüş tablo",
  run_split_when_fits: "sığdığı hâlde bölünen liste", continuation_cut: "devam cümlesinde kesim",
  below_min: "çok küçük parça", above_soft_max: "bütçe üstü parça",
};
const smellNames = (list) => (list || []).map((s) => SMELLS[s] || s).join(", ");

const DEC_TEXT = {
  llm_accepted: "Deep Analysis bu sınırı model onayıyla yerleştirdi.",
  llm_merged: "Deep Analysis burada iki parçayı birleştirdi.",
  det_moved: "Deep Analysis bu sınırı kural katmanıyla taşıdı.",
  deterministic_improved: "Deep Analysis bu sınırı kural katmanıyla iyileştirdi.",
  std_changed: "Deep Analysis, Standard'ın buradaki kesimini kaldırdı ya da taşıdı.",
  ceiling: "Tek birim sert token tavanını aştığı için birimin içinde kesildi.",
};
const DEC_MARK = new Set(["llm_accepted", "llm_merged", "det_moved", "deterministic_improved", "std_changed"]);

function deepNote(doc) {
  const d = doc && doc.meta && doc.meta.deep;
  if (!d) return null;
  const calls = (d.calls && d.calls.total) || 0;
  if (d.status === "ok") return calls > 0 ? null : "modele gerek olmadı";
  if (d.status === "deterministic") return "kural tabanlı";
  if (d.status === "degraded") return "kısmi model";
  if (d.status === "fallback_no_provider") return "modelsiz tamamlandı";
  if (d.status === "fallback_provider_error") return "model yanıt vermedi";
  return null;
}

function methodsOf(doc) {
  const live = doc.live && doc.live.methods;
  return (DATA.methodOrder || []).filter((a) => {
    if (!doc.arms || !doc.arms[a]) return false;
    if (live && live[a] && live[a].status && live[a].status !== "ready") return false;
    return true;
  });
}

/* ---------------- row building: the one alignment rule ------------------- */
/* The same canonical unit is printed into the same grid row in every column;
   a unit one method cuts inside is sliced at the union of every column's
   offsets. Ownership comes from the mapping segments (seg), never from the
   first-chunk membership alone. */
function buildRows() {
  const doc = S.doc, arms = S.sel;
  const rows = [], diffs = [];
  if (!doc || !arms.length) { S.rowsAll = rows; S.diffs = diffs; return; }
  const last = {}; arms.forEach((a) => { last[a] = null; });
  for (const u of doc.units) {
    const len = u.x.length;
    const cuts = new Set([0, len]);
    const covers = {};
    for (const a of arms) {
      const segs = ((doc.arms[a].seg || {})[u.i] || []).slice().sort((p, q) => p[1] - q[1] || p[0] - q[0]);
      covers[a] = segs;
      for (const r of segs) {
        if (r[1] > 0 && r[1] < len) cuts.add(r[1]);
        if (r[2] > 0 && r[2] < len) cuts.add(r[2]);
      }
    }
    const offs = [...cuts].sort((x, y) => x - y);
    for (let k = 0; k + 1 < offs.length; k++) {
      const s = offs[k], e = offs[k + 1];
      const row = { u, s, e, own: {}, start: {}, over: {}, diff: false, idx: rows.length };
      let anyStart = false, anyRun = false, covered = 0;
      for (const a of arms) {
        const cov = covers[a].filter((r) => r[1] <= s && r[2] >= e);
        if (!cov.length) { row.own[a] = null; continue; }
        covered++;
        // Ownership follows the reading flow: among the chunks whose segments
        // cover this slice, take the nearest one at or ahead of the flow -- a
        // heading repeated into several chunks' provenance, or a chunk that
        // resumes after an isolated table, must not fake a new boundary. A
        // boundary is drawn only when the flow moves FORWARD into a chunk it
        // has not visited, so every chunk opens at most once.
        const idxs = cov.map((r) => r[0]);
        let idx;
        if (last[a] === null) idx = Math.min.apply(null, idxs);
        else {
          const ahead = idxs.filter((i) => i >= last[a]);
          idx = ahead.length ? Math.min.apply(null, ahead) : Math.max.apply(null, idxs);
        }
        row.own[a] = idx;
        row.over[a] = cov.length > 1;
        row.start[a] = last[a] === null || idx > last[a];
        if (last[a] !== null) { if (row.start[a]) anyStart = true; else anyRun = true; }
        last[a] = last[a] === null ? idx : Math.max(last[a], idx);
      }
      if (arms.length > 1 && covered > 1 && anyStart && anyRun) { row.diff = true; diffs.push(row.idx); }
      rows.push(row);
    }
  }
  S.rowsAll = rows; S.diffs = diffs;
  if (S.diffIdx >= diffs.length) S.diffIdx = -1;
}

/* ---------------- top bar ------------------------------------------------ */
function renderBar() {
  const kbBtn = $("kbBtn"), docBtn = $("docBtn"), chips = $("chips"), nav = $("nav");
  kbBtn.className = "pick" + (S.kb ? "" : " unset");
  kbBtn.querySelector(".v").textContent = S.kb ? S.kb.name : "Seç";
  docBtn.disabled = !S.kb;
  docBtn.className = "pick" + (S.kb && !S.doc && !S.prep ? " unset" : "");
  docBtn.querySelector(".v").textContent = S.doc ? S.doc.label : (S.prep ? S.prep.name : (S.kb ? "Seç" : "—"));

  const tabs = $("tabs");
  tabs.hidden = false;
  tabs.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.t === S.mode));

  if (S.doc && S.mode === "incele") {
    const avail = methodsOf(S.doc);
    chips.hidden = false;
    chips.innerHTML = avail.map((a) => {
      const at = S.sel.indexOf(a);
      const note = isDeep(a) ? deepNote(S.doc) : null;
      return `<button class="chip${at >= 0 ? " on" : ""}" data-m="${a}">` +
        (at >= 0 && S.sel.length > 1 ? `<span class="ord">${at + 1}</span>` : "") +
        esc(mLabel(a)) + (note ? `<span class="note">${esc(note)}</span>` : "") + `</button>`;
    }).join("");
  } else { chips.hidden = true; chips.innerHTML = ""; }

  const showNav = !!(S.doc && S.mode === "incele" && S.sel.length && S.page != null);
  nav.hidden = !showNav;
  if (showNav) {
    const pages = S.doc.pages, i = pages.indexOf(S.page);
    $("pPrev").disabled = i <= 0; $("pNext").disabled = i >= pages.length - 1;
    const sel = $("pSel");
    sel.innerHTML = pages.map((p) => `<option value="${p}"${p === S.page ? " selected" : ""}>${p}</option>`).join("");
    $("pTot").textContent = "/ " + pages[pages.length - 1];
    const dg = $("dGrp"), n = S.diffs.length;
    dg.hidden = !(S.sel.length > 1 && n > 0);
    if (!dg.hidden) {
      $("dPos").textContent = (S.diffIdx >= 0 ? S.diffIdx + 1 : "–") + " / " + n;
      $("dPrev").disabled = n === 0; $("dNext").disabled = n === 0;
    }
  }
  updatePill();
}

/* ---------------- stage: empty states ------------------------------------ */
function steps(stage) {
  const items = [["Bilgi tabanı", 0], ["Doküman", 1], ["Yöntem", 2]];
  return `<div class="steps">` + items.map(([t, i]) =>
    `<div class="st${i < stage ? " done" : i === stage ? " now" : ""}"><b>${i < stage ? "✓" : i + 1}</b>${t}</div>`
  ).join("") + `</div>`;
}

function renderStage() {
  closePop();
  const st = $("stage");
  if (S.mode === "home") { renderHome(st); return; }
  if (S.mode === "bench") { renderBench(st); return; }
  if (S.mode === "debug") { renderDebug(st); return; }
  if (!S.kb) {
    st.innerHTML = `<div class="hero"><h1>Bir doküman, birden çok parçalama.</h1>
      <p>Bilgi tabanını ve dokümanı seçin; her yöntemin metni nerede kestiğini doğrudan sayfanın üzerinde görün.</p>
      ${steps(0)}<button class="primary" id="heroKb">Bilgi tabanı seç</button></div>`;
    $("heroKb").addEventListener("click", (ev) => openKbMenu(ev.currentTarget));
    return;
  }
  if (S.mode === "sorgu") { renderQuery(st); return; }
  if (S.prep) { renderPrep(st); return; }
  if (!S.doc) {
    const docs = kbDocItems(S.kb);
    st.innerHTML = `<div class="hero"><h1>${esc(S.kb.name)}</h1>
      <p>İncelemek istediğiniz dokümanı seçin.</p>${steps(1)}
      <div class="herolist">${docs.html || `<div class="quiet" style="padding:12px 14px;color:var(--mut)">Bu bilgi tabanında doküman yok.</div>`}</div></div>`;
    bindDocItems(st);
    return;
  }
  if (!S.sel.length) {
    const avail = methodsOf(S.doc);
    st.innerHTML = `<div class="hero"><h1>${esc(S.doc.label)}</h1>
      <p>${S.doc.meta && S.doc.meta.pageCount ? S.doc.meta.pageCount + " sayfa · " : ""}Bir parçalama yöntemi seçin — ikincisini seçtiğinizde aynı sayfa yan yana karşılaştırılır.</p>
      ${steps(2)}<div class="mcards">` +
      avail.map((a) => {
        const note = isDeep(a) ? deepNote(S.doc) : null;
        return `<button class="mcard" data-m="${a}"><span class="n">${esc(mLabel(a))}` +
          (note ? `<span class="note">${esc(note)}</span>` : "") + `</span>` +
          (mSummary(a) ? `<span class="s">${esc(mSummary(a))}</span>` : "") + `</button>`;
      }).join("") + `</div></div>`;
    st.querySelectorAll(".mcard").forEach((b) => b.addEventListener("click", () => toggleMethod(b.dataset.m)));
    return;
  }
  renderBoard(st);
}

function renderPrep(st) {
  const p = S.prep;
  const line = p.error
    ? `<p style="color:var(--bad)">Analiz başarısız: ${esc(p.error)}</p>`
    : `<p><span class="spin"></span>Analiz hazırlanıyor — doküman yeniden okunmaz, yalnız eksik yöntemler paketlenir.</p>`;
  st.innerHTML = `<div class="hero"><h1>${esc(p.name)}</h1>${line}${steps(1)}` +
    (p.error ? `<button class="primary" id="retryPrep">Yeniden dene</button>` : "") + `</div>`;
  const r = $("retryPrep");
  if (r) r.addEventListener("click", () => prepareLive(p.id, p.name));
}

/* ---------------- stage: the board --------------------------------------- */
function unitHtml(row) {
  const u = row.u, full = row.s === 0 && row.e === u.x.length;
  if (u.t === "heading") {
    const lv = Math.min(Math.max(u.l || 2, 1), 4);
    const body = full && u.h ? u.h : esc(u.x.slice(row.s, row.e).replace(/^#{1,6}\s+/, "").replace(/\*\*/g, ""));
    return `<div class="hx l${lv}">${body}</div>`;
  }
  if (full && u.h) return `<div class="tx">${u.h}</div>`;
  const pre = (u.t === "list" || u.t === "table") ? " pre" : "";
  return `<div class="tx${pre}">${esc(u.x.slice(row.s, row.e))}</div>`;
}

function boundaryLabel(arm, chunk, over) {
  const short = REASON_SHORT[chunk.rs] || "Yeni parça";
  const deep = !!(S.doc.story && chunk.dec && DEC_MARK.has(chunk.dec.status));
  return `<span class="bl${deep ? " deep" : ""}"><b>${chunk.num}</b> · ${esc(short)}${over ? " · örtüşme" : ""}</span>`;
}

function renderBoard(st) {
  const doc = S.doc, arms = S.sel, n = arms.length;
  const pageRows = S.rowsAll.filter((r) => r.u.p === S.page);
  const gutter = n > 1;
  const gridCols = (gutter ? "26px " : "") + `repeat(${n},minmax(0,1fr))`;
  let h = `<div id="wrap"><section class="sheet c${n}">${MARKS}` +
    `<header class="shead"><span class="dl">${esc(doc.label)}${doc.live ? " · " + esc((S.kb && S.kb.kind === "live" ? S.kb.name : doc.live.kbName) || "RAG Console") : ""}</span>` +
    `<span class="pl">Sayfa ${S.page}</span></header>` +
    `<div class="board" style="grid-template-columns:${gridCols}">`;

  if (n > 1) {
    h += `<div class="grow">` + (gutter ? `<div class="gut chead"></div>` : "");
    for (const a of arms) {
      const note = isDeep(a) ? deepNote(doc) : null;
      h += `<div class="chead">${esc(mLabel(a))}${note ? `<span class="note">${esc(note)}</span>` : ""}</div>`;
    }
    h += `</div>`;
  }

  // continuation notes: the chunk running into this page from the previous one
  const contCells = arms.map((a) => {
    const first = pageRows.find((r) => r.own[a] != null);
    if (!first || first.start[a]) return "";
    const c = doc.arms[a].chunks[first.own[a]];
    return c ? `‹ Parça ${c.num} önceki sayfadan devam ediyor` : "";
  });
  if (contCells.some(Boolean)) {
    h += `<div class="grow">` + (gutter ? `<div class="gut"></div>` : "");
    for (let i = 0; i < n; i++) h += `<div class="cont">${esc(contCells[i])}</div>`;
    h += `</div>`;
  }

  if (!pageRows.length) {
    h += `</div><div class="emptypg">Bu sayfada canonical içerik yok.</div></section></div>`;
    st.innerHTML = h; return;
  }

  for (const row of pageRows) {
    h += `<div class="grow" data-r="${row.idx}">`;
    if (gutter) h += `<div class="gut">${row.diff ? `<span class="d" title="Yöntemler burada ayrışıyor"></span>` : ""}</div>`;
    for (const a of arms) {
      const own = row.own[a];
      if (own == null) {
        h += `<div class="cell ghost" data-a="${a}">${unitHtml(row)}</div>`;
        continue;
      }
      const chunk = doc.arms[a].chunks[own];
      const cb = row.start[a] && chunk;
      const selCls = S.open && S.open.a === a && S.open.c === own ? " sel" : "";
      h += `<div class="cell k${own % 3}${cb ? " cb" : ""}${selCls}" data-a="${a}" data-c="${own}">` +
        (cb ? boundaryLabel(a, chunk, row.over[a]) : "") + unitHtml(row) + `</div>`;
    }
    h += `</div>`;
  }
  h += `</div></section></div>`;
  st.innerHTML = h;
}

/* ---------------- popover ------------------------------------------------ */
function closePop() {
  const pop = $("pop");
  pop.hidden = true; pop.style.width = "";
  if (S.open) { S.open = null; paintSel(); }
}

function paintSel() {
  document.querySelectorAll(".cell.sel").forEach((c) => c.classList.remove("sel"));
  if (S.open) document.querySelectorAll(`.cell[data-a="${S.open.a}"][data-c="${S.open.c}"]`)
    .forEach((c) => c.classList.add("sel"));
}

function openPop(a, cIdx, anchor) {
  const doc = S.doc, chunk = doc.arms[a].chunks[cIdx];
  if (!chunk) return;
  S.open = { a, c: cIdx }; paintSel();
  const sec = secOf(chunk);
  const reason = REASON_LONG[chunk.rs] || null;
  let deepBx = "";
  if (doc.story && chunk.dec && DEC_TEXT[chunk.dec.status]) {
    const rm = smellNames(chunk.dec.removed_smells);
    deepBx = `<div class="deepbx"><b>Deep Analysis</b> — ${esc(DEC_TEXT[chunk.dec.status])}` +
      (rm ? `<br>Giderilen: ${esc(rm)}.` : "") + `</div>`;
  }
  const cont = chunk.rt === "TOKEN_BUDGET_CONTINUATION" ? "önceki parçanın bütçe devamı" : (chunk.rt || "—");
  const pop = $("pop");
  pop.innerHTML =
    `<div class="t">Parça ${chunk.num}<span class="mth">${esc(mLabel(a))}</span></div>` +
    `<div class="meta">${esc(fmtPages(chunk.pg))} · ${chunk.n} token</div>` +
    (sec ? `<div class="row"><span class="k">Bölüm</span>${esc(sec)}</div>` : "") +
    (reason ? `<div class="row"><span class="k">Neden burada başladı?</span>${esc(reason)}</div>` : "") +
    deepBx +
    `<details><summary>Teknik ayrıntı</summary><dl>` +
    `<dt>id</dt><dd>${esc(chunk.id)}</dd>` +
    `<dt>motor</dt><dd>${esc(doc.arms[a].kind)}</dd>` +
    (chunk.st && chunk.st.length ? `<dt>strateji</dt><dd>${esc(chunk.st.join(", "))}</dd>` : "") +
    `<dt>birim</dt><dd>${chunk.u.length}</dd>` +
    `<dt>sınır kodu</dt><dd>${esc(chunk.rs)}</dd>` +
    `<dt>devam</dt><dd>${esc(cont)}</dd>` +
    `</dl></details>`;
  pop.hidden = false;
  const r = anchor.getBoundingClientRect(), pw = 308, ph = pop.offsetHeight;
  let x = r.right + 14, y = Math.max(64, Math.min(r.top, innerHeight - ph - 12));
  if (x + pw > innerWidth - 10) x = Math.max(10, r.left - pw - 14);
  if (x < 10) { x = Math.min(innerWidth - pw - 10, Math.max(10, r.left)); y = Math.min(r.bottom + 10, innerHeight - ph - 12); }
  pop.style.left = x + "px"; pop.style.top = y + "px";
}

/* ---------------- sorgu (ask the document) ------------------------------- */
function apiDocId() { return S.docKey ? S.docKey.slice(2) : null; }

function qArms() {
  const doc = S.doc, live = doc.live && doc.live.methods;
  return (DATA.methodOrder || []).filter((a) => doc.arms && doc.arms[a] &&
    (!live || !live[a] || !live[a].status || live[a].status === "ready"));
}

let qRun = 0; // a new question supersedes any still-running one

/* Session-local query history: the last few questions asked in this page
   load, so a demo can re-run one with a click. Never persisted anywhere. */
const QHIST = [];
function relTime(ts) {
  const s = (Date.now() - ts) / 1000;
  if (s < 90) return "az önce";
  const m = Math.round(s / 60);
  if (m < 60) return m + " dk önce";
  const hh = Math.round(m / 60);
  if (hh < 24) return hh + " sa önce";
  return hh < 48 ? "dün" : Math.round(hh / 24) + " gün önce";
}
function pushHist(q, method, n) {
  QHIST.unshift({ q, method, n, at: Date.now() });
  if (QHIST.length > 6) QHIST.pop();
}
function histHtml() {
  if (!QHIST.length) return "";
  return `<div class="qsect2" style="margin-top:34px">Son sorgular</div><div class="qhist">` +
    QHIST.map((r, i) =>
      `<button class="qhrow" data-h="${i}"><span class="hq">${esc(r.q)}</span>` +
      `<span class="hm">${esc(r.method)}</span><span class="hn">${r.n != null ? r.n + " parça" : ""}</span>` +
      `<span class="ht">${relTime(r.at)}</span></button>`).join("") + `</div>`;
}

/* The ready documents of the knowledge base the reader is in, with the
   methods each can actually answer with -- from the embedded payloads for
   the built-in corpus, from the workspace snapshot for a live KB. */
function kbCandidates() {
  if (!S.kb) return [];
  if (S.kb.kind === "builtin")
    return (DATA.docOrder || []).map((id) => ({ id, name: DATA.docs[id].label, methods: methodsOf(DATA.docs[id]) }));
  return ((S.kb.raw && S.kb.raw.documents) || [])
    .filter((d) => d.viewer && d.viewer.status === "ready")
    .map((d) => ({ id: d.doc_id, name: d.name, methods: (d.viewer && d.viewer.ready_methods) || [] }));
}

function qTarget() {
  const t = S.q.target;
  return t && t.kind === "doc" ? t : { kind: "kb" };
}

function qArmOptions() {
  const t = qTarget();
  if (t.kind === "doc") {
    if (S.doc && apiDocId() === t.id) return qArms();
    const c = kbCandidates().find((d) => d.id === t.id);
    return c ? (DATA.methodOrder || []).filter((a) => c.methods.indexOf(a) >= 0) : [];
  }
  const seen = new Set();
  kbCandidates().forEach((d) => d.methods.forEach((m) => seen.add(m)));
  return (DATA.methodOrder || []).filter((a) => seen.has(a));
}

function ensureHealth() {
  if (!SERVED || S.q.health) return Promise.resolve(S.q.health);
  return fetch("/api/health").then((r) => r.json()).catch(() => null)
    .then((h) => { S.q.health = h; return h; });
}

function qDefaults() {
  const avail = qArmOptions();
  S.q.arms = (S.q.arms || []).filter((a) => avail.indexOf(a) >= 0);
  if (!S.q.arms.length && avail.length)
    S.q.arms = [avail.indexOf(DEEP) >= 0 ? DEEP : avail[0]];
  // KB-wide search runs one method at a time.
  if (qTarget().kind === "kb" && S.q.arms.length > 1) S.q.arms = [S.q.arms[0]];
  if (!S.q.topk)
    S.q.topk = (S.q.health && S.q.health.retrieval && S.q.health.retrieval.top_k) || 5;
}

/* Every row is live: models and the context budget come from the server's
   own /api/health, top-k mirrors the picker, the method row mirrors the
   selected scope, and the source row names the knowledge base the reader is
   ACTUALLY in -- never the one the analysis happened to be staged under. */
function paramsHtml() {
  const h = S.q.health, t = qTarget();
  const arm0 = S.q.arms[0];
  let methodRow;
  if (t.kind === "kb") {
    const n = kbCandidates().filter((d) => d.methods.indexOf(arm0) >= 0).length;
    methodRow = mLabel(arm0) + " · " + n + " doküman aranır";
  } else if (S.q.arms.length > 1) {
    methodRow = "karşılaştırma · " + S.q.arms.map(mLabel).join(", ");
  } else {
    const loaded = S.doc && apiDocId() === t.id;
    const n = loaded && S.doc.arms[arm0] ? S.doc.arms[arm0].chunks.length : null;
    methodRow = mLabel(arm0) + (n ? " · " + n + " parça" : "");
  }
  const model = h ? (h.answer_model || null) : null;
  const rows = [
    ["Embedding", h ? (h.embedding_model || "yok (BM25)") : "—"],
    ["Retrieval", h ? (h.dense ? "dense + BM25, RRF" : "BM25") : "—"],
    ["Bağlam", h && h.context
      ? h.context.max_context_tokens + " token bütçe · devam genişletme " + (h.context.expansion_enabled ? "açık" : "kapalı")
      : "—"],
    ["Kapsam", t.kind === "kb" ? "Tüm bilgi tabanı · " + S.kb.name : t.name],
    ["Yöntem", methodRow],
  ];
  if (S.kb && S.kb.kind === "live")
    rows.push(["Kaynak", "RAG Console · " + S.kb.name + (t.kind === "doc" ? " · canlı doküman" : "")]);
  return (SERVED
      ? `<span class="livechip${h ? "" : " off"}">${h ? "canlı" : "bağlanıyor"}</span>`
      : `<span class="livechip off">çevrimdışı</span>`) +
    `<h3>Parametreler</h3>` +
    `<label class="qf qcf"><span>Model</span><select id="qModel">` +
    (model ? `<option>${esc(model)}</option>` : `<option>—</option>`) + `</select></label>` +
    `<label class="qf qcf"><span>Top-k</span><select id="qK">` +
    [3, 5, 8, 10].map((k) => `<option value="${k}"${k === S.q.topk ? " selected" : ""}>${k}</option>`).join("") + `</select></label>` +
    `<dl class="qkv">` +
    rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("") + `</dl>` +
    (SERVED ? "" : `<div class="qoff">Sunucu kapalı — değerler bağlanınca dolar.</div>`);
}

function srcCard(s, i) {
  const sec = ((s.section_path && s.section_path.length ? s.section_path.join(" › ") : (s.heading || "")) || "")
    .replace(/[#*]/g, "").trim();
  return `<div class="qsrc${s.used ? " used" : ""}">` +
    `<div class="qsrchead"><span class="slab">${esc(s.label || "S" + (i + 1))}</span>` +
    `<span class="sinfo">${esc(sec || s.chunk_id)}</span>` +
    `<span class="smeta">${esc(fmtPages(s.pages))} · ${s.token_count} tk${s.used ? " · cevapta kullanıldı" : ""}</span></div>` +
    `<div class="qsrcbody" hidden><div class="qtxt">${esc(s.text || "")}</div>` +
    (S.q.canJump ? `<button class="qjump" data-arm="${esc(s.arm)}" data-cid="${esc(s.chunk_id)}">İncele görünümünde aç</button>` : "") +
    `</div></div>`;
}

function answerHtml(res) {
  let h = "";
  const a = res.answer;
  if (res.error) h += `<div class="qnote warn">${esc(res.error)}</div>`;
  if (a && a.text) {
    h += `<div class="qans">${esc(a.text).replace(/\n/g, "<br>")}</div>`;
    if (a.sufficient === false) h += `<div class="qnote warn" style="margin-top:10px">Model, kaynakları bu soru için yetersiz buldu.</div>`;
  }
  const srcs = res.sources || [];
  if (srcs.length)
    h += `<div class="qsect">Kaynaklar · ${esc(mLabel(res.arm))}</div>` + srcs.map(srcCard).join("");
  else if (!res.error && !(a && a.text))
    h += `<div class="qnote">Bu soruya kaynak bulunamadı.</div>`;
  return h;
}

function compareHtml(cmp) {
  const base = S.q.cmpArms && S.q.cmpArms.length ? S.q.cmpArms : (DATA.methodOrder || []);
  const order = base.filter((a) => cmp.arms && cmp.arms[a]);
  return order.map((a) => {
    const r = cmp.arms[a], ans = r.answer;
    const ov = cmp.unit_overlap_with_other_arms ? cmp.unit_overlap_with_other_arms[a] : null;
    const srcs = r.sources || [];
    return `<div class="qcmpcol"><div class="qsect" style="margin-top:0">${esc(mLabel(a))}` +
      (ov != null ? `<span class="ov">diğer yöntemlerle örtüşme %${Math.round(ov * 100)}</span>` : "") + `</div>` +
      (r.error ? `<div class="qnote warn">${esc(r.error)}</div>` : "") +
      (ans && ans.text ? `<div class="qans sm">${esc(ans.text).replace(/\n/g, "<br>")}</div>` : "") +
      (srcs.length ? `<div class="qmini">${srcs.map((s, i) =>
        `<button type="button" class="qminisrc qsrcbtn" data-arm="${esc(a)}" data-i="${i}">` +
        `<span class="slab">${esc(s.label)}</span> ${esc(fmtPages(s.pages))} · ${s.token_count} tk${s.used ? " · kullanıldı" : ""}</button>`).join("")}</div>` : "") +
      `</div>`;
  }).join("");
}

/* The frozen benchmark's own query view, offline: the gold questions and, per
   method, the rank of the first relevant chunk the frozen run recorded. */
function goldHtml(doc) {
  const gold = doc.gold || [];
  if (!gold.length) return "";
  const arms = (DATA.methodOrder || []).filter((a) =>
    doc.arms[a] && doc.arms[a].q && Object.keys(doc.arms[a].q).length);
  const rows = gold.map((g) => {
    const cells = arms.map((a) => {
      const e = doc.arms[a].q[g.id], f = e && e.f;
      return `<td class="${f === 1 ? "hit" : f ? "" : "miss"}">${f ? f + "." : "–"}</td>`;
    }).join("");
    return `<tr><td class="q" data-q="${esc(g.q)}">${esc(g.q.length > 92 ? g.q.slice(0, 90) + "…" : g.q)}</td>` +
      `<td class="pg">${(g.pg || []).join(", ")}</td>${cells}</tr>`;
  }).join("");
  return `<details class="qgold"${S.q.showGold ? " open" : ""}><summary>Ölçüm soruları · ${gold.length} soru` +
    `<span class="qhint2">frozen koşunun kayıtlı sonuçları · ilk isabetin sırası</span></summary>` +
    `<div class="qgoldwrap"><table><thead><tr><th>Soru</th><th>Kanıt syf.</th>` +
    arms.map((a) => `<th>${esc(mLabel(a))}</th>`).join("") +
    `</tr></thead><tbody>${rows}</tbody></table></div></details>`;
}

function renderQuery(st) {
  if (!S.kb) {
    st.innerHTML = `<div class="hero"><div class="kicker">Sorgu</div><h1>Bilgi tabanı gerekli</h1>` +
      `<p class="qnote err" style="display:inline-block;margin-top:18px">Sorgu için önce bir bilgi tabanı seçin.</p></div>`;
    return;
  }
  qDefaults();
  const t = qTarget(), h = S.q.health, cands = kbCandidates();
  const loadedDoc = t.kind === "doc" && S.doc && apiDocId() === t.id ? S.doc : null;
  S.q.canJump = !!loadedDoc;
  const gold = loadedDoc ? (loadedDoc.gold || []) : [];
  const arms = qArmOptions();
  let out;
  if (!SERVED)
    out = `<div class="qnote">Canlı soru-cevap, sayfa <b>viewer_server</b> üzerinden sunulduğunda çalışır.` +
      (gold.length ? " Aşağıdaki ölçüm soruları çevrimdışı görülebilir." : "") + `</div>`;
  else if (S.q.busy)
    out = S.q.prog
      ? `<div class="qnote"><span class="spin"></span>Bilgi tabanı aranıyor · ${S.q.prog.done}/${S.q.prog.total} doküman</div>`
      : `<div class="qnote"><span class="spin"></span>${S.q.arms.length > 1 ? "Aynı soru seçili yöntemlerle koşuluyor…" : "Cevap aranıyor…"}</div>`;
  else if (S.q.err) out = `<div class="qnote err">${esc(S.q.err)}</div>`;
  else if (S.q.kbres) out = kbResHtml(S.q.kbres);
  else if (S.q.cmp) out = compareHtml(S.q.cmp);
  else if (S.q.res) out = answerHtml(S.q.res);
  else out = "";

  const kicker = "Sorgu · " + (t.kind === "kb"
    ? esc(S.kb.name)
    : (S.q.arms.length > 1 ? S.q.arms.length + " yöntem" : esc(mLabel(S.q.arms[0] || ""))));
  const title = t.kind === "kb" ? "Bilgi tabanına sor" : "Bu dokümana sor";
  const sub = t.kind === "kb"
    ? esc(S.kb.name) + " içindeki " + cands.length + " hazır doküman aranır; en iyi eşleşen doküman cevaplanır."
    : esc(t.name) + " · seçili kapsamda " + (h ? (h.dense ? "dense + BM25" : "BM25") : "dense + BM25") +
      " geri getirme çalışır, sonuç parça referanslarıyla birlikte döner.";
  st.innerHTML = `<div class="qwrap"><div class="qmaincol">` +
    `<div class="kicker">${kicker}</div>` +
    `<h1 class="ql1">${title}</h1>` +
    `<p class="qsub">${sub}</p>` +
    `<div class="qpanel">${MARKS}` +
    `<label class="qlab" for="qIn">Soru</label>` +
    `<textarea id="qIn" rows="3" placeholder="${t.kind === "kb" ? "Bu bilgi tabanına doğal dilde bir soru sorun…" : "Bu dokümana doğal dilde bir soru sorun…"}">${esc(S.q.text || "")}</textarea>` +
    `<div class="qctl">` +
    `<label class="qf"><span>Kapsam</span><select id="qScope">` +
    `<option value="__kb"${t.kind === "kb" ? " selected" : ""}>Tüm bilgi tabanı</option>` +
    cands.map((c) => `<option value="${esc(c.id)}"${t.kind === "doc" && t.id === c.id ? " selected" : ""}>${esc(c.name)}</option>`).join("") +
    `</select></label>` +
    `<div class="qf qmths"><span>${t.kind === "kb" ? "Yöntem" : "Yöntemler"}</span><div class="qmchips">` +
    arms.map((a) => `<button type="button" class="mchip${S.q.arms.indexOf(a) >= 0 ? " on" : ""}" data-a="${a}">${esc(mLabel(a))}</button>`).join("") +
    `</div></div>` +
    `</div>` +
    `<div class="qbottom"><span class="qmnote">${t.kind === "doc" && S.q.arms.length > 1 ? S.q.arms.length + " yöntem karşılaştırılır" : (t.kind === "kb" ? "Bilgi tabanı aramasında tek yöntem koşar" : "")}</span>` +
    `<button class="primary qgo" id="qGo"${SERVED ? "" : " disabled"}>Sor</button></div>` +
    `</div>` +
    `<div id="qOut">${out}</div>` +
    (gold.length ? `<div class="qsect2">Başlangıç soruları</div><div class="qsug">` +
      gold.slice(0, 6).map((g, i) => `<button data-i="${i}">${esc(g.q.length > 96 ? g.q.slice(0, 94) + "…" : g.q)}</button>`).join("") + `</div>` : "") +
    histHtml() +
    (loadedDoc ? goldHtml(loadedDoc) : "") +
    `</div><aside class="qside"><div class="qcard">${MARKS}${paramsHtml()}</div></aside></div>`;
  bindQuery(st);
}

function bindQuery(st) {
  const qIn = $("qIn");
  qIn.addEventListener("input", () => { S.q.text = qIn.value; });
  qIn.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); runAsk(); }
  });
  const sc = $("qScope");
  if (sc) sc.addEventListener("change", (ev) => {
    const v = ev.target.value;
    S.q.target = v === "__kb" ? { kind: "kb" }
      : { kind: "doc", id: v, name: (kbCandidates().find((c) => c.id === v) || { name: v }).name };
    S.q.res = null; S.q.cmp = null; S.q.kbres = null; S.q.err = null;
    renderQuery($("stage"));
  });
  st.querySelectorAll(".qaskdoc").forEach((b) => b.addEventListener("click", (ev) => {
    ev.stopPropagation();
    S.q.target = { kind: "doc", id: b.dataset.id, name: b.dataset.name };
    runAsk();
  }));
  st.querySelectorAll(".mchip").forEach((b) => b.addEventListener("click", () => {
    const a = b.dataset.a;
    if (qTarget().kind === "kb") S.q.arms = [a];
    else {
      const i = S.q.arms.indexOf(a);
      if (i >= 0) { if (S.q.arms.length > 1) S.q.arms.splice(i, 1); }
      else S.q.arms.push(a);
    }
    renderQuery($("stage"));
  }));
  $("qK").addEventListener("change", (ev) => { S.q.topk = parseInt(ev.target.value, 10); renderQuery($("stage")); });
  $("qGo").addEventListener("click", runAsk);
  st.querySelectorAll(".qsug button").forEach((b) => b.addEventListener("click", () => {
    S.q.text = (S.doc.gold || [])[parseInt(b.dataset.i, 10)].q;
    renderQuery($("stage")); $("qIn").focus();
  }));
  st.querySelectorAll(".qhrow").forEach((b) => b.addEventListener("click", () => {
    const r = QHIST[parseInt(b.dataset.h, 10)];
    if (r) { S.q.text = r.q; renderQuery($("stage")); $("qIn").focus(); }
  }));
  const det = st.querySelector(".qgold");
  if (det) det.addEventListener("toggle", () => { S.q.showGold = det.open; });
  st.querySelectorAll(".qgold td.q").forEach((td) => td.addEventListener("click", () => {
    S.q.text = td.dataset.q; renderQuery($("stage")); $("qIn").focus();
  }));
  st.querySelectorAll(".qsrc .qsrchead").forEach((hd) => hd.addEventListener("click", () => {
    const body = hd.parentElement.querySelector(".qsrcbody");
    if (body) body.hidden = !body.hidden;
  }));
  st.querySelectorAll(".qjump[data-cid]").forEach((b) => b.addEventListener("click", (ev) => {
    ev.stopPropagation(); jumpToChunk(b.dataset.arm, b.dataset.cid);
  }));
  st.querySelectorAll(".qsrcbtn").forEach((b) => b.addEventListener("click", (ev) => {
    ev.stopPropagation();
    const arm = b.dataset.arm, i = parseInt(b.dataset.i, 10);
    const src = S.q.cmp && S.q.cmp.arms && S.q.cmp.arms[arm] && (S.q.cmp.arms[arm].sources || [])[i];
    if (src) openSrcPop(src, b);
  }));
}

/* A retrieved source in the comparison, in a small floating card: the chunk
   text as the server returned it, and a way into the İncele view when this
   document's payload carries that chunk. */
function openSrcPop(s, anchor) {
  const sec = ((s.section_path && s.section_path.length ? s.section_path.join(" › ") : (s.heading || "")) || "")
    .replace(/[#*]/g, "").trim();
  const armData = S.doc && S.doc.arms && S.doc.arms[s.arm];
  const canJump = !!(armData && armData.chunks.some((c) => c.id === s.chunk_id));
  const pop = $("pop");
  pop.innerHTML =
    `<div class="t">${esc(s.label || "Kaynak")}<span class="mth">${esc(mLabel(s.arm))}</span></div>` +
    `<div class="meta">${esc(fmtPages(s.pages))} · ${s.token_count} token${s.used ? " · cevapta kullanıldı" : ""}</div>` +
    (sec ? `<div class="row"><span class="k">Bölüm</span>${esc(sec)}</div>` : "") +
    `<div class="ptxt">${esc(s.text || "")}</div>` +
    (canJump ? `<div class="pfoot"><button class="qjump" id="popJump">İncele görünümünde aç →</button></div>` : "");
  pop.hidden = false;
  const pw = Math.min(360, innerWidth - 20);
  pop.style.width = pw + "px";
  const r = anchor.getBoundingClientRect(), ph = pop.offsetHeight;
  let x = r.right + 14, y = Math.max(64, Math.min(r.top, innerHeight - ph - 12));
  if (x + pw > innerWidth - 10) x = Math.max(10, r.left - pw - 14);
  if (x < 10) { x = Math.min(innerWidth - pw - 10, Math.max(10, r.left)); y = Math.min(r.bottom + 10, innerHeight - ph - 12); }
  pop.style.left = x + "px"; pop.style.top = Math.max(10, y) + "px";
  const j = $("popJump");
  if (j) j.addEventListener("click", () => { closePop(); jumpToChunk(s.arm, s.chunk_id); });
}

function runAsk() {
  if (!SERVED || S.q.busy) return;
  const question = (S.q.text || "").trim();
  if (!question) { const qi = $("qIn"); if (qi) qi.focus(); return; }
  const t = qTarget();
  if (t.kind === "kb") { runAskKb(question); return; }
  const run = ++qRun;
  const multi = S.q.arms.length > 1;
  S.q.busy = true; S.q.err = null; S.q.res = null; S.q.cmp = null; S.q.kbres = null; S.q.prog = null;
  S.q.cmpArms = multi ? S.q.arms.slice() : null;
  renderQuery($("stage"));
  const body = { doc: t.id, question, top_k: S.q.topk };
  if (multi) body.arms = S.q.arms.slice(); else body.arm = S.q.arms[0];
  fetch(multi ? "/api/compare" : "/api/chat", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  })
    .then((r) => r.json())
    .then((res) => {
      if (run !== qRun) return;
      S.q.busy = false;
      if (res && res.error && !res.arms && !res.answer && !(res.sources || []).length) S.q.err = res.error;
      else if (multi) { S.q.cmp = res; pushHist(question, "Karşılaştırma · " + (S.q.cmpArms || []).length + " yöntem", null); }
      else { S.q.res = res; pushHist(question, mLabel(S.q.arms[0]), (res.sources || []).length); }
      renderQuery($("stage"));
    })
    .catch(() => { if (run !== qRun) return; S.q.busy = false; S.q.err = "Sunucuya ulaşılamadı."; renderQuery($("stage")); });
}

/* Ask the whole knowledge base: every ready document that carries the chosen
   method is searched in turn with the existing per-document /api/retrieve
   (progress shown), the best-matching document is answered with /api/chat,
   and the runners-up stay one click away. No new endpoint, no merged answer
   pretending to be one document's. */
function runAskKb(question) {
  const arm = S.q.arms[0], all = kbCandidates();
  const cands = all.filter((d) => d.methods.indexOf(arm) >= 0);
  const skipped = all.length - cands.length;
  if (!cands.length) {
    S.q.err = "Bu bilgi tabanında '" + mLabel(arm) + "' yöntemiyle hazır doküman yok.";
    renderQuery($("stage")); return;
  }
  const run = ++qRun;
  S.q.busy = true; S.q.err = null; S.q.res = null; S.q.cmp = null; S.q.kbres = null;
  S.q.prog = { done: 0, total: cands.length, errs: 0 };
  renderQuery($("stage"));
  const found = [];
  const finish = () => {
    if (run !== qRun) return;
    found.sort((x, y) => y.score - x.score);
    if (!found.length) {
      const errs = S.q.prog ? S.q.prog.errs : 0;
      S.q.busy = false; S.q.prog = null;
      S.q.kbres = { question, arm, best: null, others: [], skipped, errs };
      renderQuery($("stage")); return;
    }
    const best = found[0];
    fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc: best.doc.id, arm, question, top_k: S.q.topk }) })
      .then((r) => r.json()).catch(() => ({ error: "Sunucuya ulaşılamadı." }))
      .then((res) => {
        if (run !== qRun) return;
        const errs = S.q.prog ? S.q.prog.errs : 0;
        S.q.busy = false; S.q.prog = null;
        S.q.kbres = { question, arm, best: { doc: best.doc, res }, others: found.slice(1, 6), skipped, errs };
        pushHist(question, "Bilgi tabanı · " + mLabel(arm), (res.sources || []).length);
        renderQuery($("stage"));
      });
  };
  const next = (i) => {
    if (run !== qRun) return;
    if (i >= cands.length) { finish(); return; }
    const d = cands[i];
    fetch("/api/retrieve", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc: d.id, arm, question, top_k: S.q.topk }) })
      .then((r) => r.json()).catch(() => null)
      .then((res) => {
        if (run !== qRun) return;
        S.q.prog.done = i + 1;
        if (res && (res.sources || []).length)
          found.push({ doc: d, score: (res.hits && res.hits[0] && res.hits[0].rrf_score) || 0, sources: res.sources });
        else if (!res || res.error) S.q.prog.errs += 1;
        const el = $("qOut");
        if (el) el.innerHTML = `<div class="qnote"><span class="spin"></span>Bilgi tabanı aranıyor · ${S.q.prog.done}/${S.q.prog.total} doküman${S.q.prog.errs ? " · " + S.q.prog.errs + " aranamadı" : ""}</div>`;
        next(i + 1);
      });
  };
  next(0);
}

function kbResHtml(k) {
  if (!k.best)
    return `<div class="qnote">Bu soruya bilgi tabanında kaynak bulunamadı.` +
      (k.skipped ? ` (${k.skipped} doküman '${esc(mLabel(k.arm))}' yöntemiyle hazır olmadığı için aranmadı.)` : "") + `</div>`;
  let h = `<div class="qsect" style="margin-top:0">En iyi eşleşme · ${esc(k.best.doc.name)}</div>`;
  h += answerHtml(k.best.res);
  if (k.others.length) {
    h += `<div class="qsect">Diğer eşleşen dokümanlar</div>` + k.others.map((o) => {
      const s = o.sources[0];
      const sec = ((s.section_path && s.section_path.length ? s.section_path.join(" › ") : (s.heading || "")) || "")
        .replace(/[#*]/g, "").trim();
      return `<div class="qsrc"><div class="qsrchead"><span class="sinfo">${esc(o.doc.name)}</span>` +
        `<span class="smeta">${esc(sec ? sec + " · " : "")}${esc(fmtPages(s.pages))}</span>` +
        `<button class="qjump qaskdoc" data-id="${esc(o.doc.id)}" data-name="${esc(o.doc.name)}">Bu dokümanda cevapla</button></div></div>`;
    }).join("");
  }
  if (k.skipped)
    h += `<div class="qoff" style="margin-top:12px">${k.skipped} doküman '${esc(mLabel(k.arm))}' yöntemiyle hazır olmadığı için aranmadı.</div>`;
  if (k.errs) h += `<div class="qoff">${k.errs} doküman aranamadı.</div>`;
  return h;
}

function jumpToChunk(arm, cid) {
  const doc = S.doc, armData = doc.arms[arm];
  if (!armData) return;
  const idx = armData.chunks.findIndex((c) => c.id === cid);
  if (idx < 0) return;
  if (S.sel.indexOf(arm) < 0) S.sel = [arm];
  S.mode = "incele";
  buildRows();
  const chunk = armData.chunks[idx];
  S.page = (chunk.pg && chunk.pg[0]) || doc.pages[0];
  renderBar(); renderStage();
  S.open = { a: arm, c: idx };
  requestAnimationFrame(() => {
    paintSel();
    const el = document.querySelector(`.cell[data-a="${arm}"][data-c="${idx}"]`);
    if (el) el.scrollIntoView({ block: "center" });
  });
}

/* ---------------- home / overview ----------------------------------------- */
let _bChunks = null;
function builtinChunkTotal() {
  if (_bChunks == null) {
    _bChunks = 0;
    for (const id of DATA.docOrder || []) {
      const d = DATA.docs[id];
      for (const a in d.arms) _bChunks += d.arms[a].chunks.length;
    }
  }
  return _bChunks;
}

/* The overview answers three questions with real state and nothing else:
   what is in the system, what is ready, and where can I go next. */
function renderHome(st) {
  const b = (DATA.docOrder || []).length;
  const connected = SERVED && WS && WS.connected;
  const kbs = connected ? (WS.knowledge_bases || []) : [];
  const t = connected ? (WS.totals || {}) : null;
  const liveDocs = t ? (t.documents || 0) : 0;
  const stats = [
    ["Bilgi tabanı", kbs.length + 1,
      SERVED ? (connected ? "RAG Console + yerleşik" : (WS ? "konsola ulaşılamadı" : "konsol okunuyor…")) : "yerleşik korpus"],
    ["Doküman", b + liveDocs, b + " yerleşik" + (t ? " · " + liveDocs + " canlı" : "")],
    ["Hazır analiz", (t ? (t.viewer_ready || 0) : 0) + b, "İncele ve Sorgu'ya açık"],
    ["Parça", builtinChunkTotal().toLocaleString("tr-TR"),
      "yerleşik korpus · " + (DATA.methodOrder || []).length + " yöntem"],
  ];

  let kbRows = `<button class="hrow" data-kb="__builtin"><span class="n">Yerleşik korpus</span>` +
    `<span class="m">${b} doküman · benchmark</span><span class="schip ok">hazır</span></button>`;
  if (SERVED) {
    if (!WS) kbRows += `<div class="hquiet"><span class="spin"></span>RAG Console okunuyor…</div>`;
    else if (!WS.connected) kbRows += `<div class="hquiet">RAG Console'a ulaşılamadı — canlı bilgi tabanları sunucu bağlıyken listelenir.</div>`;
    else if (!kbs.length) kbRows += `<div class="hquiet">Konsolda bilgi tabanı yok.</div>`;
    else kbRows += kbs.map((kb) => {
      const docs = kb.documents || [];
      const rdy = docs.filter((d) => d.viewer && d.viewer.status === "ready").length;
      const id = kb.kb_id == null ? "__orphan" : kb.kb_id;
      return `<button class="hrow" data-kb="live:${esc(id)}"><span class="n">${esc(kb.name)}</span>` +
        `<span class="m">${docs.length} doküman · ${rdy} hazır</span>` +
        `<span class="schip ${rdy ? "ok" : "wait"}">${rdy ? "hazır" : "bekliyor"}</span></button>`;
    }).join("");
  } else {
    kbRows += `<div class="hquiet">Canlı bilgi tabanları, sayfa viewer_server üzerinden açıldığında listelenir.</div>`;
  }

  const pool = [];
  if (connected)
    for (const kb of kbs) for (const d of kb.documents || [])
      pool.push({ d, kb, at: Date.parse(d.ingested_at || "") || 0 });
  let recTitle, recRows;
  if (pool.length) {
    recTitle = "Son eklenenler";
    pool.sort((x, y) => y.at - x.at);
    recRows = pool.slice(0, 6).map((r) => {
      const stt = (r.d.viewer && r.d.viewer.status) || "missing";
      const chip = stt === "ready" ? `<span class="schip ok">hazır</span>`
        : stt === "running" ? `<span class="schip run">işleniyor</span>`
        : stt === "pending" ? `<span class="schip wait">kuyrukta</span>`
        : stt === "failed" ? `<span class="schip err">hata</span>`
        : `<span class="schip wait">analiz yok</span>`;
      return `<button class="hrow" data-doc="${esc(r.d.doc_id)}" data-kb2="${esc(r.kb.kb_id == null ? "__orphan" : r.kb.kb_id)}" data-st="${stt}" data-name="${esc(r.d.name)}">` +
        `<span class="n">${esc(r.d.name)}</span><span class="m">${esc(r.kb.name)}${r.at ? " · " + relTime(r.at) : ""}</span>${chip}</button>`;
    }).join("");
  } else {
    recTitle = "Yerleşik dokümanlar";
    recRows = (DATA.docOrder || []).map((id) => {
      const d = DATA.docs[id];
      return `<button class="hrow" data-bdoc="${esc(id)}"><span class="n">${esc(d.label)}</span>` +
        `<span class="m">${d.meta && d.meta.pageCount ? d.meta.pageCount + " sayfa · " : ""}${methodsOf(d).length} yöntem</span>` +
        `<span class="schip ok">hazır</span></button>`;
    }).join("");
  }

  st.innerHTML = `<div class="home">` +
    `<div><div class="kicker">Chunk Viewer</div><h1 class="ql1">Genel bakış</h1>` +
    `<p class="hsub">Bir dokümanın hangi yöntemle nasıl parçalandığını sayfanın üzerinde inceleyin, aynı içerikte yöntemleri karşılaştırın, dokümana ya da bilgi tabanına soru sorun.</p></div>` +
    `<div class="statrow">${MARKS}` + stats.map(([k, v, s]) =>
      `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${v}</div><div class="s">${esc(s)}</div></div>`).join("") + `</div>` +
    `<div class="hpanels">` +
    `<div class="hpanel">${MARKS}<div class="hphead"><span class="t">Bilgi tabanları</span>` +
    (SERVED ? `<button id="hRefresh">Yenile</button>` : `<span class="r">yerleşik</span>`) + `</div>${kbRows}</div>` +
    `<div class="hpanel">${MARKS}<div class="hphead"><span class="t">${recTitle}</span>` +
    `<span class="r">${pool.length ? Math.min(6, pool.length) + " / " + pool.length : ""}</span></div>${recRows}</div>` +
    `</div>` +
    (QHIST.length ? `<div class="qsect2" style="margin-top:34px">Son sorgular</div><div class="qhist">` +
      QHIST.map((r, i) => `<button class="qhrow" data-h="${i}"><span class="hq">${esc(r.q)}</span>` +
        `<span class="hm">${esc(r.method)}</span><span class="hn">${r.n != null ? r.n + " parça" : ""}</span>` +
        `<span class="ht">${relTime(r.at)}</span></button>`).join("") + `</div>` : "") +
    `</div>`;
  bindHome(st);
}

function bindHome(st) {
  st.querySelectorAll(".hrow[data-kb]").forEach((btn) => btn.addEventListener("click", () => {
    selectKb(btn.dataset.kb); S.mode = "incele"; renderBar(); renderStage();
  }));
  st.querySelectorAll(".hrow[data-bdoc]").forEach((btn) => btn.addEventListener("click", () => {
    selectKb("__builtin"); S.mode = "incele"; openDoc("b:" + btn.dataset.bdoc);
  }));
  st.querySelectorAll(".hrow[data-doc]").forEach((btn) => btn.addEventListener("click", () => {
    selectKb("live:" + btn.dataset.kb2);
    S.mode = "incele";
    if (btn.dataset.st === "ready") loadLive(btn.dataset.doc, btn.dataset.name || btn.dataset.doc);
    else { renderBar(); renderStage(); }
  }));
  const rf = $("hRefresh");
  if (rf) rf.addEventListener("click", () => {
    WS = null; renderHome($("stage"));
    fetchWorkspace();
  });
  st.querySelectorAll(".qhrow").forEach((btn) => btn.addEventListener("click", () => {
    const r = QHIST[parseInt(btn.dataset.h, 10)];
    if (!r) return;
    S.q.text = r.q; S.mode = "sorgu";
    ensureHealth().then(() => { if (S.mode === "sorgu") renderStage(); });
    renderBar(); renderStage();
  }));
}

/* ---------------- benchmark ----------------------------------------------- */
const SMELL_ORDER = ["orphan_label", "lead_in_cut", "continuation_cut", "run_split_when_fits",
  "table_split", "fragment_cut", "below_min", "above_soft_max"];
const fmt3 = (x) => (x == null ? "—" : Number(x).toFixed(3));
const fmt1 = (x) => (x == null ? "—" : Number(x).toFixed(1));

function tokenStats(chunks) {
  const arr = chunks.map((c) => c.n).filter((n) => typeof n === "number").sort((a, b) => a - b);
  if (!arr.length) return { med: null, p90: null };
  const q = (p) => arr[Math.min(arr.length - 1, Math.round(p * (arr.length - 1)))];
  return { med: q(0.5), p90: q(0.9) };
}
const benchArms = (doc) => (DATA.methodOrder || []).filter((a) => doc.arms && doc.arms[a]);

function deepSeconds(dp) {
  const t = dp && dp.timing;
  if (!t) return null;
  let s = 0, any = false;
  for (const k in t) if (typeof t[k] === "number") { s += t[k]; any = true; }
  return any ? s : null;
}

function fmtDur(d) { return d == null ? "—" : (d >= 10 ? Math.round(d) + " s" : d.toFixed(1) + " s"); }

/* Structural quality side by side -- everything computed from the real chunk
   rows and the packaged structural_quality, never invented. */
function benchMethodsPanel(doc) {
  const lm = doc.live && doc.live.methods;
  const tm = doc.meta.timing || {};
  let anyDur = false;
  const body = benchArms(doc).map((a) => {
    const arm = doc.arms[a];
    const ts = tokenStats(arm.chunks);
    const frag = arm.sq && arm.sq.fragmentation;
    const head = arm.chunks.length ? arm.chunks.filter((c) => c.hd).length / arm.chunks.length : null;
    let dur = null;
    if (isDeep(a)) dur = deepSeconds(doc.meta.deep);
    else if (lm && lm[a] && typeof lm[a].seconds === "number") dur = lm[a].seconds;
    else if (tm[a] && tm[a].chunk_ms_median != null) dur = tm[a].chunk_ms_median / 1000;
    if (dur != null) anyDur = true;
    return `<tr><td>${esc(mLabel(a))}<span class="tech">${esc(a)}</span></td>` +
      `<td>${arm.chunks.length}</td><td>${ts.med != null ? ts.med : "—"}</td><td>${ts.p90 != null ? ts.p90 : "—"}</td>` +
      `<td>${head != null ? fmt3(head) : "—"}</td>` +
      `<td>${frag ? frag.table_units_fragmented : "—"}</td>` +
      `<td>${frag ? frag.list_units_fragmented : "—"}</td>` +
      `<td>${fmtDur(dur)}</td></tr>`;
  }).join("");
  return `<div class="hpanel">${MARKS}<div class="hphead"><span class="t">Yapısal kalite</span>` +
    `<span class="r">gerçek parça satırlarından</span></div>` +
    `<table class="btable"><thead><tr><th>Yöntem</th><th>Parça</th><th>Token medyan</th><th>P90</th>` +
    `<th>Başlıkla açılan</th><th>Tablo böl.</th><th>Liste böl.</th><th>Süre</th></tr></thead>` +
    `<tbody>${body}</tbody></table>` +
    (anyDur ? "" : `<div class="bnote">Bu doküman için süre kaydı yok; yeni yüklemelerde her yöntemin işleme süresi otomatik kaydedilir.</div>`) +
    `</div>`;
}

function benchTimingPanel(doc) {
  const tm = doc.meta.timing || {};
  const arms = benchArms(doc).filter((a) => tm[a]);
  if (!arms.length) return "";
  let body = arms.map((a) => {
    const t = tm[a];
    return `<tr><td>${esc(mLabel(a))}</td>` +
      `<td>${fmt1(t.chunk_ms_median)}</td><td>${fmt1(t.index_build_ms)}</td>` +
      `<td>${t.search_p90_ms != null ? t.search_p90_ms.toFixed(2) : "—"}</td></tr>`;
  }).join("");
  const dt = doc.arms[DEEP] && doc.arms[DEEP].tim;
  if (dt) body += `<tr><td>${esc(mLabel(DEEP))}</td><td>—</td>` +
    `<td>${fmt1(dt.index_build_ms)}</td><td>${dt.search_p90_ms != null ? dt.search_p90_ms.toFixed(2) : "—"}</td></tr>`;
  const parse = tm.parse;
  return `<div class="hpanel">${MARKS}<div class="hphead"><span class="t">Zamanlama (ms)</span>` +
    `<span class="r">medyan · tek koşu</span></div>` +
    `<table class="btable"><thead><tr><th>Yöntem</th><th>Chunking</th><th>İndeks</th><th>Arama p90</th></tr></thead>` +
    `<tbody>${body}</tbody></table>` +
    (dt ? `<div class="bnote">Deep Analysis chunking süresi sağlayıcıya bağlıdır; yerel kollarla karşılaştırılmaz ve bu tabloya yazılmaz.</div>` : "") +
    (parse && parse.parse_ms ? `<div class="bnote">Parse: ${Math.round(parse.parse_ms / 1000)} s · tüm yöntemlerin paylaştığı tek ayrıştırma (${parse.unit_count} birim).</div>` : "") +
    `</div>`;
}

function benchDeepSection(doc, no) {
  const dp = doc.meta.deep;
  if (!dp) return "";
  const sm = dp.smellTotal || {}, tot = dp.totals || {};
  const sc = dp.storyCounts || (doc.story && doc.story.counts) || {};
  const calls = (dp.calls && dp.calls.total) || 0;
  const secs = deepSeconds(dp);
  const rDeep = dp.retrieval && dp.retrieval.deep, rStd = dp.retrieval && dp.retrieval.standard;
  const note = deepNote(doc);
  const removed = (sm.standard != null && sm.deep != null) ? sm.standard - sm.deep : null;

  const stats = [
    ["Yapısal problem", sm.standard != null ? `${sm.standard} → ${sm.deep}` : "—",
      removed > 0 ? removed + " sorunlu sınır ortadan kalktı" : "toplam problem sayısı korundu"],
    ["Kötüleşen bölüm", dp.regressions != null ? dp.regressions : "—",
      dp.regressions === 0 ? "Hiçbir bölümde, hiçbir problem türünde Standard'ın gerisine düşülmedi"
        : "bölümde en az bir problem türü arttı"],
  ];
  if (rDeep && rStd)
    stats.push(["İlk 5'te doğru parça", fmt3(rDeep.hit_at_5),
      rDeep.hit_at_5 === rStd.hit_at_5 ? "Standard ile aynı — arama kalitesi korunuyor, iddia bu"
        : (rDeep.hit_at_5 > rStd.hit_at_5 ? "Standard'dan iyi (" + fmt3(rStd.hit_at_5) + ")"
          : "Standard: " + fmt3(rStd.hit_at_5))]);
  else
    stats.push(["Modele danışılan bölüm",
      sc.llm_consulted_sections != null ? sc.llm_consulted_sections + " / " + (sc.sections || "?") : "—",
      "yalnız kararsız sınırı olan bölümler"]);
  stats.push(["Ek maliyet",
    calls > 0 ? (dp.estCostUsd != null ? "≈ $" + dp.estCostUsd : calls + " çağrı") : "$0",
    calls > 0
      ? calls + " LLM çağrısı" + (secs != null ? " · " + Math.round(secs) + " s" : "") + " · yüklemede tek sefer"
      : "model çağrısı yok · kural katmanı"]);

  let rows = "";
  for (const k of SMELL_ORDER) {
    const s = (tot.standard || {})[k], d = (tot.deep || {})[k];
    if (s == null && d == null) continue;
    const delta = (s != null && d != null) ? d - s : null;
    rows += `<tr><td>${esc(SMELLS[k] || k)}<span class="tech">${k}</span></td>` +
      `<td>${s != null ? s : "—"}</td><td>${d != null ? d : "—"}</td>` +
      `<td class="${delta < 0 ? "good" : delta > 0 ? "badv" : ""}">${delta == null ? "—" : delta === 0 ? "–" : (delta > 0 ? "+" + delta : delta)}</td></tr>`;
  }
  const smd = (sm.deep != null && sm.standard != null) ? sm.deep - sm.standard : null;
  rows += `<tr class="total"><td>Toplam</td><td>${sm.standard != null ? sm.standard : "—"}</td>` +
    `<td>${sm.deep != null ? sm.deep : "—"}</td>` +
    `<td class="${smd < 0 ? "good" : ""}">${smd == null ? "—" : smd === 0 ? "–" : smd}</td></tr>`;

  const cost = [];
  if (sc.llm_consulted_sections != null) cost.push(["Modele danışılan bölüm", sc.llm_consulted_sections + " / " + (sc.sections || "?")]);
  if (sc.llm_accepted != null) cost.push(["Kabul edilen model önerisi", sc.llm_accepted]);
  if (sc.deterministic_improved != null) cost.push(["Kural ile düzeltilen bölüm", sc.deterministic_improved]);
  if (sc.llm_reverted != null) cost.push(["Doğrulayıcının geri çevirdiği", sc.llm_reverted]);
  if (secs != null) cost.push(["Ek süre (yükleme)", Math.round(secs) + " s"]);
  if (dp.model && calls > 0) cost.push(["Model", dp.model]);

  const claim = calls > 0
    ? `Deep Analysis model kullanır; aynı koşu birebir tekrarlanmaz ve tek başına bir "kazanan yöntem" ilan edilmez. Garanti edilen şey: yapısal problem sayısı artmaz, hiçbir bölüm Standard'ın gerisine düşmez` +
      (rDeep ? ", arama kalitesi bu gold sette en azından korunur." : ".")
    : "Bu koşuda modele hiç danışılmadı; kazancın tamamı deterministik kural katmanından. Aynı canonical ile koşu birebir tekrarlanabilir.";

  return `<div class="bsec"><span class="no">${no}</span><h2>Standard → Deep Analysis</h2>` +
    (note ? `<span class="bn">${esc(note)}</span>` : "") + `</div>` +
    `<div class="statrow b">${MARKS}` + stats.map(([k, v, s]) =>
      `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${v}</div><div class="s">${esc(s)}</div></div>`).join("") + `</div>` +
    `<div class="bgrid">` +
    `<div class="hpanel">${MARKS}<div class="hphead"><span class="t">Sınır kalitesi — problem türü başına</span>` +
    `<span class="r">bölüm bazında sayaçlar</span></div>` +
    `<table class="btable"><thead><tr><th>Problem türü</th><th>Standard</th><th>Deep</th><th>Δ</th></tr></thead>` +
    `<tbody>${rows}</tbody></table></div>` +
    `<div><div class="hpanel">${MARKS}<div class="hphead"><span class="t">Bedeli</span></div>` +
    cost.map(([k, v]) => `<div class="bkrow"><span>${esc(k)}</span><span class="v">${esc(String(v))}</span></div>`).join("") +
    `</div><div class="claim"><div class="t">Neyi iddia etmiyoruz</div><p>${esc(claim)}</p></div></div>` +
    `</div>`;
}

function benchRetrievalSection(doc, no) {
  const arms = benchArms(doc).filter((a) => doc.arms[a].ret);
  if (arms.length < 2) return "";
  const rows = arms.map((a) => ({ a, r: doc.arms[a].ret }));
  const cols = [["hit_at_1", "İlk sonuçta"], ["hit_at_3", "İlk 3'te"], ["hit_at_5", "İlk 5'te"],
    ["mrr", "Sıralama (MRR)"], ["evidence_coverage_at_5", "Kanıt kapsama"]];
  const best = {};
  for (const [k] of cols) best[k] = Math.max.apply(null, rows.map((x) => x.r[k] || 0));
  const body = rows.map(({ a, r }) =>
    `<tr><td>${esc(mLabel(a))}<span class="tech">${esc(a)}</span></td>` +
    cols.map(([k]) => `<td class="${r[k] === best[k] ? "best" : ""}">${fmt3(r[k])}</td>`).join("") + `</tr>`).join("");
  return `<div class="bsec"><span class="no">${no}</span><h2>Arama başarısı — ${arms.length} yöntem yan yana</h2>` +
    `<span class="bn">aynı ${rows[0].r.query_count} soru · 0–1 arası, yüksek olan iyi</span></div>` +
    `<div class="hpanel" style="margin-top:18px">${MARKS}` +
    `<table class="btable"><thead><tr><th>Yöntem</th>${cols.map(([, l]) => `<th>${l}</th>`).join("")}</tr></thead>` +
    `<tbody>${body}</tbody></table></div>` +
    `<div class="bnote">● bu koşuda gözlenen en iyi değer. Hiçbir yöntem her sütunda önde değil — beklenen sonuç bu; tablo tek başına bir kazanan ilan etmez.</div>`;
}

function renderBench(st) {
  const doc = S.doc;
  if (!doc) {
    const items = (DATA.docOrder || []).map((id) => {
      const d = DATA.docs[id];
      const g = (d.gold || []).length;
      return `<button class="it" data-bdoc="${esc(id)}"><span class="n">${esc(d.label)}</span>` +
        `<span class="m">${g ? "dondurulmuş set · " + g + " gold sorgu" : "Deep koşusu · gold set yok"}</span></button>`;
    }).join("");
    st.innerHTML = `<div class="hero"><div class="kicker">Benchmark</div><h1>Bir doküman seçin</h1>` +
      `<p>Dondurulmuş benchmark dokümanları gömülü ölçümleriyle açılır; canlı bir doküman için önce bilgi tabanından dokümanı açın.</p>` +
      `<div class="herolist">${items}</div></div>`;
    st.querySelectorAll("[data-bdoc]").forEach((b) => b.addEventListener("click", () => {
      selectKb("__builtin"); S.mode = "bench"; openDoc("b:" + b.dataset.bdoc);
    }));
    return;
  }
  const hasGold = benchArms(doc).filter((a) => doc.arms[a].ret).length >= 2;
  const kicker = "Benchmark · " + (hasGold ? "Dondurulmuş set" : (doc.live ? "Canlı doküman" : "Deep koşusu"));
  const sub = hasGold
    ? "Aynı canonical girdi, aynı BM25 ayarları, aynı gold set — kollar arasında yalnız chunker değişir."
    : "Gold sorgu seti yok; Hit@k / MRR bu doküman için üretilmez ve uydurulmaz. Aşağıdakilerin hepsi gerçekten ölçülmüş değerler.";
  const chips = [benchArms(doc).length + " yöntem"];
  if (doc.meta.pageCount) chips.push(doc.meta.pageCount + " sayfa");
  chips.push((doc.gold || []).length ? doc.gold.length + " gold sorgu" : "gold set yok");
  if (doc.meta.budgets && doc.meta.budgets.target_tokens) chips.push("hedef " + doc.meta.budgets.target_tokens + " token");

  let no = 0; const sec = () => String(++no).padStart(2, "0");
  let body = "";
  if (hasGold) {
    body += benchDeepSection(doc, sec());
    body += benchRetrievalSection(doc, sec());
    body += `<details class="bdetails"><summary><span class="no">${sec()}</span><h2>Ham ölçümler</h2>` +
      `<span class="tog">göster +</span></summary>` +
      `<div class="bgrid" style="margin-top:18px"><div>${benchMethodsPanel(doc)}</div><div>${benchTimingPanel(doc)}</div></div></details>`;
  } else {
    body += `<div class="bsec"><span class="no">${sec()}</span><h2>Yöntemler yan yana</h2>` +
      `<span class="bn">aynı canonical girdi · ortak token bütçesi</span></div>` +
      `<div style="margin-top:18px">${benchMethodsPanel(doc)}</div>`;
    body += benchDeepSection(doc, sec());
  }
  st.innerHTML = `<div class="bench">` +
    `<div class="bhead"><div><div class="kicker">${esc(kicker)}</div><h1 class="ql1">${esc(doc.label)}</h1>` +
    `<p class="qsub">${esc(sub)}</p></div>` +
    `<div class="bchips">${chips.map((c) => `<span class="bchip">${esc(c)}</span>`).join("")}</div></div>` +
    body + `</div>`;
  st.querySelectorAll(".bdetails").forEach((d) => d.addEventListener("toggle", () => {
    const tog = d.querySelector(".tog");
    if (tog) tog.textContent = d.open ? "gizle −" : "göster +";
  }));
}

/* ---------------- debug ---------------------------------------------------
   The one screen that answers "why does this boundary exist, and how did the
   system get there" -- from the recorded decision story alone. Nothing here
   is estimated or invented: a value the artifacts did not record is either
   hidden or written as unmeasured. */
const DEEP_STATUS_TXT = {
  ok: "model koştu",
  deterministic: "kural tabanlı — model istenmedi",
  degraded: "kısmi model — bazı çağrılar yanıtsız",
  fallback_no_provider: "sağlayıcıya ulaşılamadı — deterministik tamamlandı",
  fallback_provider_error: "model yanıt vermedi — deterministik tamamlandı",
};
const SECT_STATUS = {
  deterministic_improved: { src: "Kural", cls: "rule", res: "düzeltildi", resCls: "ok" },
  llm_accepted: { src: "Model", cls: "model", res: "kabul", resCls: "ok" },
  llm_reverted: { src: "Model", cls: "model", res: "geri çevrildi", resCls: "no" },
  contract_reverted: { src: "Kalite kontrol", cls: "qc", res: "geri alındı", resCls: "rv" },
};
const DBG_FILTERS = [["all", "Tümü"], ["rule", "Kural"], ["model", "Model"], ["rev", "Geri çevrilen"]];
// "Kural" and "Model" filter by the decision's SOURCE (so a reverted model
// proposal still counts as the model's), "Geri çevrilen" by the OUTCOME.
const dbgMatch = (st, f) => f === "all"
  || (f === "rule" && st === "deterministic_improved")
  || (f === "model" && (st === "llm_accepted" || st === "llm_reverted"))
  || (f === "rev" && (st === "llm_reverted" || st === "contract_reverted"));

function dbgJump(pg) {
  if (pg == null || !S.doc) return;
  const arms = [BASE, DEEP].filter((a) => S.doc.arms[a]);
  if (arms.length) S.sel = arms;
  S.mode = "incele"; S.diffIdx = -1;
  buildRows(); S.page = pg;
  renderBar(); renderStage(); window.scrollTo({ top: 0 });
}

function dbgSectionRows(doc) {
  const rows = [];
  for (const s of (doc.story && doc.story.sections) || []) {
    const cfg = SECT_STATUS[s.st];
    if (!cfg) continue;
    const rm = []; for (const g of s.gr || []) for (const x of g.rm || []) rm.push(x);
    const added = []; for (const g of s.gr || []) for (const x of g.in || []) added.push(x);
    let trigger = rm.length ? rm.join(" · ") : null;
    if (!trigger && s.pr && s.pr.length) {
      const reasons = [...new Set(s.pr.filter((p) => (s.st === "llm_accepted") === !!p.a && p.r).map((p) => p.r))];
      trigger = reasons.join(" · ") || null;
    }
    if (!trigger && s.rv) trigger = String(s.rv);
    rows.push({ s, cfg, rm, added, trigger });
  }
  return rows;
}

function dbgDetail(row, doc) {
  const s = row.s, cells = [];
  const add = (k, v) => { if (v != null && v !== "") cells.push([k, v]); };
  add("Sayfa", (s.pg || []).join(", "));
  add("Bölüm tokeni", s.tt);
  if (s.std && s.fin) add("Kesim sayısı", s.std.length + " → " + s.fin.length);
  add("Giderilen", row.rm.length ? row.rm.map((k) => SMELLS[k] || k).join(", ") : null);
  add("Eklenen problem", row.added.length ? row.added.map((k) => SMELLS[k] || k).join(", ") : null);
  if (s.pr && s.pr.length) add("Model önerisi", s.pr.length + " · kabul " + s.pr.filter((p) => p.a).length);
  if (s.cons != null) add("Modele danışıldı", s.cons ? "evet" : "hayır");
  if (s.sz) add("Boyut ödünleşimi", "evet — daha az problem karşılığında");
  if (s.rv) add("Geri alma nedeni", String(s.rv));
  return `<div class="dg">` +
    cells.map(([k, v]) => `<span><span class="k">${esc(k)}</span><span class="v2">${esc(String(v))}</span></span>`).join("") +
    ((s.pg || []).length ? `<span><span class="k">Görünüm</span><button class="qjump djump" data-pg="${s.pg[0]}">İncele${String.fromCharCode(39)}de aç →</button></span>` : "") +
    `</div>`;
}

function dbgReasonHistPanel(doc) {
  const arms = benchArms(doc);
  const codes = new Set();
  const counts = {};
  for (const a of arms) {
    counts[a] = {};
    for (const c of doc.arms[a].chunks) { codes.add(c.rs); counts[a][c.rs] = (counts[a][c.rs] || 0) + 1; }
  }
  const order = ["doc_start", "new_section", "label_split", "budget_split", "md_heading", "md_size", "md_overlap"];
  const list = order.filter((c) => codes.has(c)).concat([...codes].filter((c) => order.indexOf(c) < 0));
  const body = list.map((code) =>
    `<tr><td>${esc(REASON_SHORT[code] || code)}<span class="tech">${esc(code)}</span></td>` +
    arms.map((a) => `<td>${counts[a][code] || "–"}</td>`).join("") + `</tr>`).join("");
  return `<div class="hpanel">${MARKS}<div class="hphead"><span class="t">Sınır nedenleri — yöntem başına</span>` +
    `<span class="r">her parçanın kayıtlı başlama nedeni</span></div>` +
    `<table class="btable"><thead><tr><th>Neden</th>` +
    arms.map((a) => `<th>${esc(mLabel(a))}</th>`).join("") + `</tr></thead><tbody>${body}</tbody></table></div>`;
}

function renderDebug(st) {
  const doc = S.doc;
  if (!doc) {
    const items = (DATA.docOrder || []).map((id) => {
      const d = DATA.docs[id];
      return `<button class="it" data-bdoc="${esc(id)}"><span class="n">${esc(d.label)}</span>` +
        `<span class="m">${d.story ? "Deep karar izi kayıtlı" : "karar izi yok"}</span></button>`;
    }).join("");
    st.innerHTML = `<div class="hero"><div class="kicker">Debug</div><h1>Bir doküman seçin</h1>` +
      `<p>Sınır karar izi, Deep Analysis koşusu paketlenmiş dokümanlarda kayıtlıdır; canlı bir doküman için önce bilgi tabanından dokümanı açın.</p>` +
      `<div class="herolist">${items}</div></div>`;
    st.querySelectorAll("[data-bdoc]").forEach((b) => b.addEventListener("click", () => {
      selectKb("__builtin"); S.mode = "debug"; openDoc("b:" + b.dataset.bdoc);
    }));
    return;
  }
  const dp = doc.meta.deep, story = doc.story;
  const sc = (story && story.counts) || (dp && dp.storyCounts) || null;
  const calls = (dp && dp.calls && dp.calls.total) || 0;
  const tm = doc.meta.timing || {};
  const lm = doc.live && doc.live.methods;

  const chips = [];
  if (dp && dp.mode) chips.push("mod: " + dp.mode);
  if (dp && dp.status && DEEP_STATUS_TXT[dp.status]) chips.push(DEEP_STATUS_TXT[dp.status]);
  if (dp && dp.model && calls > 0) chips.push(dp.model.split("/").pop());
  if (dp && dp.promptVersion) chips.push(dp.promptVersion);
  const dSecs = deepSeconds(dp);
  if (dSecs != null) chips.push(fmtDur(dSecs));

  // -- 01 pipeline: only measured numbers, only recorded times --------------
  const parse = tm.parse;
  let stdDur = null;
  if (tm[BASE] && tm[BASE].chunk_ms_median != null) stdDur = tm[BASE].chunk_ms_median / 1000;
  else if (lm && lm[BASE] && typeof lm[BASE].seconds === "number") stdDur = lm[BASE].seconds;
  const steps = [];
  steps.push({ n: "01", nm: "Parser", t: parse && parse.parse_ms ? fmtDur(parse.parse_ms / 1000) : null,
    ds: (doc.meta.pageCount || "?") + " sayfa · " + (doc.meta.unitCount || "?") + " birim" +
      (doc.parser && doc.parser.count ? " · " + doc.parser.count + " bulgu" : "") });
  steps.push(sc
    ? { n: "02", nm: "Yapısal sınır", t: stdDur != null ? fmtDur(stdDur) : null,
        ds: sc.standard_kept + " bölüm dokunulmadan geçti · " + (sc.sections || "?") + " bölüm" }
    : { n: "02", nm: "Yapısal sınır", t: stdDur != null ? fmtDur(stdDur) : null,
        ds: doc.arms[BASE] ? doc.arms[BASE].chunks.length + " parça üretildi" : "bu dokümanda koşmadı", dim: !doc.arms[BASE] });
  steps.push(sc
    ? { n: "03", nm: "Kural katmanı", t: dp && dp.timing && dp.timing.selection != null ? fmtDur(dp.timing.selection) : null,
        ds: sc.deterministic_improved + " bölümde sınır düzeltildi" }
    : { n: "03", nm: "Kural katmanı", ds: "karar izi kayıtlı değil", dim: true });
  steps.push(dp && calls > 0 && sc
    ? { n: "04", nm: "Model önerisi", t: dp.timing && dp.timing.llm_calls != null ? fmtDur(dp.timing.llm_calls) : null,
        ds: sc.llm_consulted_sections + " bölüm modele danışıldı · " + ((dp.proposer && dp.proposer.call_count) || 0) + " çağrı" }
    : { n: "04", nm: "Model önerisi", ds: dp ? "modele danışılmadı" : "Deep koşusu yok", dim: true });
  const ver = dp && dp.verifier;
  steps.push(ver && ver.group_count
    ? { n: "05", nm: "Doğrulama", t: dp.timing && dp.timing.verifier_calls != null ? fmtDur(dp.timing.verifier_calls) : null,
        ds: ver.accepted + " öneri kabul · " + ver.reverted + " geri çevrildi (" + ver.group_count + " grup ×2 sıra)" }
    : { n: "05", nm: "Doğrulama", ds: "çalışmadı", dim: true });

  let no = 0; const sec = () => String(++no).padStart(2, "0");
  let body = `<div class="bsec"><span class="no">${sec()}</span><h2>Boru hattı</h2></div>` +
    `<div class="pipe">${MARKS}` + steps.map((p) =>
      `<div class="pstep${p.dim ? " dim" : ""}"><span class="pn">${p.n}</span>` +
      (p.t ? `<span class="pt">${esc(p.t)}</span>` : "") +
      `<div class="nm">${esc(p.nm)}</div><div class="ds">${esc(p.ds)}</div></div>`).join("") + `</div>`;

  // -- 02 boundary decisions ------------------------------------------------
  if (story) {
    const all = dbgSectionRows(doc);
    const rows = all.filter((r) => dbgMatch(r.s.st, S.dbg.filter));
    body += `<div class="bsec"><span class="no">${sec()}</span><h2>Sınır kararları</h2>` +
      `<span class="bn">${all.length} kayıt · ${(sc && sc.sections) || "?"} bölüm · ${(sc && sc.standard_kept) || "?"} bölümde Standard korundu</span>` +
      `<div class="dfilters">` + DBG_FILTERS.map(([k, l]) =>
        `<button data-f="${k}" class="${S.dbg.filter === k ? "on" : ""}">${l}</button>`).join("") + `</div></div>`;
    let trs = "";
    rows.forEach((r, i) => {
      const s = r.s;
      const open = S.dbg.open === s.i;
      trs += `<tr class="drow${open ? " openrow" : ""}" data-si="${s.i}">` +
        `<td>§${String(s.i).padStart(3, "0")}</td>` +
        `<td class="l">${esc((s.h || "(başlıksız bölüm)").slice(0, 70))}${(s.pg || []).length ? `<span class="tech">s. ${s.pg[0]}</span>` : ""}</td>` +
        `<td style="text-align:left"><span class="srcchip ${r.cfg.cls}">${r.cfg.src}</span></td>` +
        `<td class="l">${r.trigger ? `<span class="tech" style="margin-left:0">${esc(r.trigger)}</span>` : "—"}</td>` +
        `<td>${s.std && s.fin ? s.std.length + " → " + s.fin.length : "—"}</td>` +
        `<td><span class="res ${r.cfg.resCls}">${r.cfg.res}</span></td></tr>`;
      if (open) trs += `<tr class="ddetail"><td colspan="6">${dbgDetail(r, doc)}</td></tr>`;
    });
    if (!rows.length) trs = `<tr><td colspan="6" class="l" style="color:var(--faint)">Bu filtrede kayıt yok.</td></tr>`;
    body += `<div class="hpanel" style="margin-top:18px">${MARKS}` +
      `<table class="btable"><thead><tr><th style="text-align:left">Bölüm</th><th style="text-align:left">Başlık</th>` +
      `<th style="text-align:left">Kaynak</th><th style="text-align:left">Tetikleyen</th><th>Kesim</th><th>Sonuç</th></tr></thead>` +
      `<tbody>${trs}</tbody></table></div>` +
      `<div class="bnote">Yalnız bir şeyin değiştiği bölümler listelenir; satıra tıklayınca kayıtlı karar ayrıntısı açılır. Bölüm başına süre kaydedilmez — toplam süreler boru hattında.</div>`;
  } else {
    body += `<div class="bsec"><span class="no">${sec()}</span><h2>Sınır nedenleri</h2>` +
      `<span class="bn">karar izi yalnız Deep koşularında kaydedilir</span></div>` +
      `<div style="margin-top:18px">${dbgReasonHistPanel(doc)}</div>`;
  }

  // -- 03 model usage + 04 parser findings ----------------------------------
  let modelPanel;
  if (dp && calls > 0) {
    const rowsM = [];
    if (sc && sc.llm_consulted_sections != null) rowsM.push(["Modele danışılan bölüm", sc.llm_consulted_sections + " / " + (sc.sections || "?")]);
    const pr = dp.proposer || {};
    if (pr.call_count != null) rowsM.push(["Öneri çağrısı — başarılı", ((pr.call_status && pr.call_status.ok) || 0) + " / " + pr.call_count]);
    if (ver && ver.group_count != null) rowsM.push(["Doğrulama çağrısı (her grup 2 sıra)", 2 * ver.group_count]);
    if (dp.selection && dp.selection.vote_count != null) rowsM.push(["İşaretlenen / yasaklanan sınır oyu", dp.selection.vote_count + " / " + (dp.selection.forbidden_vote_count || 0)]);
    if (ver && ver.accepted != null) rowsM.push(["Kabul / geri çevrilen grup", ver.accepted + " / " + ver.reverted]);
    if (sc && sc.contract_reverted != null) rowsM.push(["Kalite kontrolünün geri aldığı", sc.contract_reverted]);
    if (dp.estTokens) rowsM.push(["Token — tahmini (karakterden)", Math.round(dp.estTokens.prompt / 1000) + "K / " + Math.round(dp.estTokens.completion / 1000) + "K"]);
    if (dp.estCostUsd != null) rowsM.push(["Yaklaşık maliyet (liste fiyatı)", "≈ $" + dp.estCostUsd]);
    modelPanel = `<div class="hpanel">${MARKS}<div class="hphead"><span class="t">Model kullanımı</span>` +
      (dp.model ? `<span class="r">${esc(dp.model)}</span>` : "") + `</div>` +
      rowsM.map(([k, v]) => `<div class="bkrow"><span>${esc(k)}</span><span class="v">${esc(String(v))}</span></div>`).join("") + `</div>`;
  } else {
    modelPanel = `<div class="hpanel">${MARKS}<div class="hphead"><span class="t">Model kullanımı</span></div>` +
      `<div class="hquiet">${dp
        ? esc((dp.status && DEEP_STATUS_TXT[dp.status]) || "Bu koşuda model çağrısı kaydı yok") + " — kazanç kural katmanından."
        : "Bu dokümanda Deep Analysis koşusu yok; model hiç devrede olmadı."}</div></div>`;
  }
  const findings = (doc.parser && doc.parser.findings) || [];
  const oversized = doc.units.filter((u) => u.big).length;
  let logLines;
  if (findings.length) {
    logLines = findings.slice(0, 14).map((f) =>
      `<div><span class="u">${esc(f.t)}</span>  ${esc(f.r)}</div>`).join("") +
      (findings.length > 14 ? `<div class="more">… +${findings.length - 14} kayıt daha</div>` : "");
  } else {
    logLines = `<div class="more">parser bulgusu yok</div>`;
  }
  if (oversized) logLines += `<div class="more">temsil tavanı üstü birim: ${oversized}</div>`;
  body += `<div class="bgrid"><div>` +
    `<div class="bsec" style="margin-top:0"><span class="no">${sec()}</span><h2>Model kullanımı</h2></div>` +
    `<div style="margin-top:18px">${modelPanel}</div></div>` +
    `<div><div class="bsec" style="margin-top:0"><span class="no">${sec()}</span><h2>Parser bulguları</h2>` +
    `<span class="bn">${findings.length} kayıt · canonical üzerinde</span></div>` +
    `<div class="dlog" style="margin-top:18px">${logLines}</div></div></div>`;

  st.innerHTML = `<div class="bench">` +
    `<div class="bhead"><div><div class="kicker">Debug · ${esc(doc.label)}</div><h1 class="ql1">Bölümleme izi</h1>` +
    `<p class="qsub">Her sınırın nereden geldiği: parser tabanı, yapısal sınır, kural katmanı, model önerisi ve doğrulama kararı. Yalnız kayıtlı değerler gösterilir.</p></div>` +
    (chips.length ? `<div class="bchips">${chips.map((c) => `<span class="bchip">${esc(c)}</span>`).join("")}</div>` : "") +
    `</div>` + body + `</div>`;

  st.querySelectorAll(".dfilters button").forEach((b) => b.addEventListener("click", () => {
    S.dbg.filter = b.dataset.f; S.dbg.open = null; renderDebug(st);
  }));
  st.querySelectorAll(".drow").forEach((tr) => tr.addEventListener("click", () => {
    const si = parseInt(tr.dataset.si, 10);
    S.dbg.open = S.dbg.open === si ? null : si;
    renderDebug(st);
  }));
  st.querySelectorAll(".djump").forEach((b) => b.addEventListener("click", (ev) => {
    ev.stopPropagation(); dbgJump(parseInt(b.dataset.pg, 10));
  }));
}

/* ---------------- console pill ------------------------------------------- */
function updatePill() {
  const pill = $("pill");
  if (!SERVED) { pill.hidden = true; return; }
  pill.hidden = false;
  const t = WS && WS.totals;
  if (WS && WS.connected && t) {
    pill.classList.add("on");
    $("pillTxt").textContent = "RAG Console · " + (t.viewer_ready || 0) + "/" + (t.documents || 0) + " doküman hazır";
  } else {
    pill.classList.remove("on");
    $("pillTxt").textContent = "RAG Console · " + (WS ? "bağlı değil" : "…");
  }
}

/* ---------------- selection actions -------------------------------------- */
function toggleMethod(a) {
  const at = S.sel.indexOf(a);
  if (at >= 0) S.sel.splice(at, 1);
  else { if (S.sel.length >= 3) return; S.sel.push(a); }
  S.diffIdx = -1;
  buildRows();
  if (S.sel.length && S.page == null) S.page = S.doc.pages[0];
  if (!S.sel.length) S.page = null;
  renderBar(); renderStage();
}

function setPage(p) {
  if (p === S.page) return;
  S.page = p; closePop(); renderBar(); renderStage();
  window.scrollTo({ top: 0 });
}

function stepPage(d) {
  const pages = S.doc.pages, i = pages.indexOf(S.page) + d;
  if (i >= 0 && i < pages.length) setPage(pages[i]);
}

function jumpDiff(d) {
  if (!S.diffs.length) return;
  S.diffIdx = S.diffIdx < 0 ? (d > 0 ? 0 : S.diffs.length - 1)
    : (S.diffIdx + d + S.diffs.length) % S.diffs.length;
  const row = S.rowsAll[S.diffs[S.diffIdx]];
  if (row.u.p !== S.page) { S.page = row.u.p; closePop(); renderStage(); window.scrollTo({ top: 0 }); }
  renderBar();
  requestAnimationFrame(() => {
    const el = document.querySelector(`.grow[data-r="${row.idx}"]`);
    if (!el) return;
    const gut = el.querySelector(".gut .d");
    el.querySelector(".gut, .cell").scrollIntoView({ block: "center", behavior: "smooth" });
    if (gut) { gut.classList.remove("fl"); void gut.offsetWidth; gut.classList.add("fl"); }
  });
}

function openDoc(key, payload) {
  REG[key] = REG[key] || payload;
  S.docKey = key; S.doc = REG[key]; S.prep = null;
  S.sel = []; S.page = null; S.rowsAll = []; S.diffs = []; S.diffIdx = -1; S.open = null;
  S.dbg = { filter: "all", open: null };
  S.q = { text: "", arms: [], topk: S.q.topk, busy: false,
          res: null, cmp: null, err: null, health: S.q.health, showGold: false,
          target: { kind: "doc", id: key.slice(2), name: S.doc.label } };
  if (S.mode === "sorgu") ensureHealth().then(() => { if (S.mode === "sorgu" && S.doc) renderStage(); });
  renderBar(); renderStage();
}

/* ---------------- menus -------------------------------------------------- */
function openMenu(anchor, html) {
  const layer = $("layer"), menu = $("menu");
  menu.innerHTML = html; layer.hidden = false;
  const r = anchor.getBoundingClientRect();
  menu.style.left = Math.min(r.left, innerWidth - menu.offsetWidth - 12) + "px";
  menu.style.top = (r.bottom + 6) + "px";
  return menu;
}
function closeMenu() { $("layer").hidden = true; }
$("layer").addEventListener("click", (ev) => { if (ev.target.id === "layer") closeMenu(); });

function kbMenuHtml() {
  let h = `<div class="sect">Yerleşik korpus</div>`;
  const cur = S.kb;
  h += `<button class="it${cur && cur.kind === "builtin" ? " cur" : ""}" data-kb="__builtin">` +
    `<span class="n">Yerleşik korpus</span><span class="m">${(DATA.docOrder || []).length} doküman · build'e gömülü</span></button>`;
  if (SERVED) {
    h += `<div class="sect">RAG Console</div>`;
    if (!WS) h += `<div class="quiet"><span class="spin"></span>bilgi tabanları okunuyor…</div>`;
    else if (!WS.connected) h += `<div class="quiet">RAG Console'a ulaşılamadı — canlı bilgi tabanları sunucu bağlıyken listelenir.</div>`;
    else {
      const kbs = WS.knowledge_bases || [];
      if (!kbs.length) h += `<div class="quiet">Konsolda bilgi tabanı yok.</div>`;
      for (const kb of kbs) {
        const id = kb.kb_id == null ? "__orphan" : kb.kb_id;
        h += `<button class="it${cur && cur.kind === "live" && cur.id === id ? " cur" : ""}" data-kb="live:${esc(id)}">` +
          `<span class="n">${esc(kb.name)}</span><span class="m">${kb.document_count || (kb.documents || []).length} doküman</span></button>`;
      }
    }
  } else {
    h += `<div class="sect">RAG Console</div><div class="quiet">Canlı bilgi tabanları, sayfa <i>viewer_server</i> üzerinden açıldığında listelenir.</div>`;
  }
  return h;
}

function openKbMenu(anchor) {
  const menu = openMenu(anchor, kbMenuHtml());
  const bind = () => menu.querySelectorAll(".it[data-kb]").forEach((b) =>
    b.addEventListener("click", () => { selectKb(b.dataset.kb); closeMenu(); }));
  bind();
  if (SERVED && (!WS || Date.now() - wsAt > 5000)) {
    fetchWorkspace().then(() => { if (!$("layer").hidden) { menu.innerHTML = kbMenuHtml(); bind(); } });
  }
}

function selectKb(token) {
  if (token === "__builtin") S.kb = { kind: "builtin", id: "__builtin", name: "Yerleşik korpus" };
  else if (token.startsWith("live:")) {
    const id = token.slice(5);
    const raw = ((WS && WS.knowledge_bases) || []).find((k) => String(k.kb_id == null ? "__orphan" : k.kb_id) === id);
    if (!raw) return;
    S.kb = { kind: "live", id, name: raw.name, raw };
  }
  S.docKey = null; S.doc = null; S.prep = null; S.sel = [];
  S.q.target = null; S.q.res = null; S.q.cmp = null; S.q.kbres = null; S.q.err = null; S.q.prog = null;
  if (S.mode === "sorgu") ensureHealth().then(() => { if (S.mode === "sorgu") renderStage(); });
  renderBar(); renderStage();
}

function kbDocItems(kb) {
  let h = "", binds = [];
  if (kb.kind === "builtin") {
    for (const id of DATA.docOrder || []) {
      const d = DATA.docs[id];
      const ms = methodsOf(d).map(mLabel).join(", ");
      h += `<button class="it${S.docKey === "b:" + id ? " cur" : ""}" data-doc="b:${esc(id)}">` +
        `<span class="n">${esc(d.label)}</span><span class="m">${d.meta && d.meta.pageCount ? d.meta.pageCount + " sayfa · " : ""}${esc(ms)}</span></button>`;
    }
  } else {
    const docs = (kb.raw && kb.raw.documents) || [];
    if (!docs.length) h += `<div class="quiet">Bu bilgi tabanında doküman yok.</div>`;
    for (const d of docs) {
      const v = d.viewer || {}; const st = v.status || "missing";
      let meta, dis = false, err = false;
      if (st === "ready") meta = (v.ready_methods || []).map(mLabel).join(", ") || "hazır";
      else if (st === "pending" || st === "running") { meta = "analiz hazırlanıyor…"; dis = true; }
      else if (st === "failed") { meta = "analiz başarısız — yeniden denemek için tıklayın"; err = true; }
      else meta = "analiz yok — hazırlamak için tıklayın";
      h += `<button class="it${S.docKey === "l:" + d.doc_id ? " cur" : ""}" data-doc="l:${esc(d.doc_id)}" data-st="${st}" data-name="${esc(d.name)}"${dis ? " disabled" : ""}>` +
        `<span class="n">${esc(d.name)}</span><span class="m${err ? " err" : ""}">${esc(meta)}</span></button>`;
    }
  }
  return { html: h };
}

function bindDocItems(scope) {
  scope.querySelectorAll(".it[data-doc]").forEach((b) => b.addEventListener("click", () => {
    closeMenu();
    const key = b.dataset.doc;
    if (key.startsWith("b:")) { openDoc(key); return; }
    const id = key.slice(2), st = b.dataset.st, name = b.dataset.name || id;
    if (REG[key]) { openDoc(key); return; }
    if (st === "ready") loadLive(id, name);
    else prepareLive(id, name);
  }));
}

function openDocMenu(anchor) {
  if (!S.kb) return;
  const menu = openMenu(anchor, kbDocItems(S.kb).html || `<div class="quiet">Doküman yok.</div>`);
  bindDocItems(menu);
}

/* ---------------- live workspace ----------------------------------------- */
function fetchWorkspace(prepare) {
  return fetch("/api/workspace" + (prepare ? "?prepare=1" : ""))
    .then((r) => r.json()).catch(() => ({ connected: false }))
    .then((w) => { WS = w; wsAt = Date.now();
      updatePill();
      if (S.mode === "home") renderStage();
      if (S.kb && S.kb.kind === "live") {
        const raw = ((w && w.knowledge_bases) || []).find((k) => String(k.kb_id == null ? "__orphan" : k.kb_id) === S.kb.id);
        if (raw) S.kb.raw = raw;
      }
      return w; });
}

function loadLive(id, name) {
  S.prep = { id, name, status: "loading" }; S.doc = null; S.docKey = null;
  renderBar(); renderStage();
  fetch("/api/live-document?doc=" + encodeURIComponent(id)).then((r) => r.json())
    .then((res) => {
      if (S.prep && S.prep.id !== id) return;
      if (res && res.payload) openDoc("l:" + id, res.payload);
      else { S.prep = { id, name, error: (res && (res.reason || res.error)) || "payload alınamadı" }; renderStage(); }
    })
    .catch(() => { if (S.prep && S.prep.id === id) { S.prep = { id, name, error: "sunucuya ulaşılamadı" }; renderStage(); } });
}

function prepareLive(id, name) {
  S.prep = { id, name, status: "preparing" }; S.doc = null; S.docKey = null;
  renderBar(); renderStage();
  fetch("/api/live-prepare", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ doc: id }) })
    .then((r) => r.json()).catch(() => null)
    .then(() => pollLive(id, name, Date.now()));
}

function pollLive(id, name, started) {
  if (pollTimer) clearTimeout(pollTimer);
  if (!S.prep || S.prep.id !== id) return;
  fetchWorkspace().then((w) => {
    if (!S.prep || S.prep.id !== id) return;
    let entry = null;
    for (const kb of (w && w.knowledge_bases) || [])
      for (const d of kb.documents || []) if (d.doc_id === id) entry = d;
    const st = entry && entry.viewer ? entry.viewer.status : null;
    if (st === "ready") { loadLive(id, name); return; }
    if (st === "failed") { S.prep = { id, name, error: (entry.viewer && entry.viewer.error) || "analiz başarısız" }; renderStage(); return; }
    if (Date.now() - started > 180000) { S.prep = { id, name, error: "zaman aşımı — konsoldaki işleyici hâlâ çalışıyor olabilir" }; renderStage(); return; }
    pollTimer = setTimeout(() => pollLive(id, name, started), 4000);
  });
}

/* ---------------- events ------------------------------------------------- */
$("kbBtn").addEventListener("click", (ev) => openKbMenu(ev.currentTarget));
$("docBtn").addEventListener("click", (ev) => openDocMenu(ev.currentTarget));
$("chips").addEventListener("click", (ev) => {
  const b = ev.target.closest(".chip"); if (b) toggleMethod(b.dataset.m);
});
$("pPrev").addEventListener("click", () => stepPage(-1));
$("pNext").addEventListener("click", () => stepPage(1));
$("pSel").addEventListener("change", (ev) => setPage(parseInt(ev.target.value, 10)));
$("dPrev").addEventListener("click", () => jumpDiff(-1));
$("dNext").addEventListener("click", () => jumpDiff(1));
$("tabs").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-t]");
  if (!b || S.mode === b.dataset.t) return;
  S.mode = b.dataset.t; closePop();
  if (S.mode === "sorgu") ensureHealth().then(() => {
    if (S.mode === "sorgu") renderStage();
  });
  if (S.mode === "home" && SERVED && (!WS || Date.now() - wsAt > 15000)) fetchWorkspace();
  renderBar(); renderStage();
});
$("pill").addEventListener("click", (ev) => openKbMenu(ev.currentTarget));

const stage = $("stage");
stage.addEventListener("mouseover", (ev) => {
  const cell = ev.target.closest(".cell[data-c]"); if (!cell) return;
  document.querySelectorAll(".cell.hov").forEach((c) => c.classList.remove("hov"));
  document.querySelectorAll(`.cell[data-a="${cell.dataset.a}"][data-c="${cell.dataset.c}"]`)
    .forEach((c) => c.classList.add("hov"));
});
stage.addEventListener("mouseleave", () => {
  document.querySelectorAll(".cell.hov").forEach((c) => c.classList.remove("hov"));
});
stage.addEventListener("click", (ev) => {
  const cell = ev.target.closest(".cell[data-c]");
  if (!cell) { if (!ev.target.closest("#pop")) closePop(); return; }
  const a = cell.dataset.a, c = parseInt(cell.dataset.c, 10);
  if (S.open && S.open.a === a && S.open.c === c) { closePop(); return; }
  openPop(a, c, cell);
});
document.addEventListener("keydown", (ev) => {
  if (ev.target.tagName === "SELECT" || ev.target.tagName === "INPUT" || ev.target.tagName === "TEXTAREA") return;
  if (ev.key === "Escape") { closePop(); closeMenu(); return; }
  if (S.mode !== "incele" || !S.doc || !S.sel.length) return;
  if (ev.key === "ArrowLeft") stepPage(-1);
  else if (ev.key === "ArrowRight") stepPage(1);
  else if (ev.key === "n") jumpDiff(1);
  else if (ev.key === "p") jumpDiff(-1);
});
window.addEventListener("scroll", () => { if (S.open) closePop(); }, { passive: true });

/* ---------------- init --------------------------------------------------- */
renderBar(); renderStage();
if (SERVED) fetchWorkspace();
</script>
</body>
</html>
"""
