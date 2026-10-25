"""The single-page web UI, served inline at /."""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>yt · local library</title>
<style>
  :root {
    --bg:#faf9f7; --panel:#fff; --edge:#e3e0da; --ink:#1c1b19; --dim:#75726c;
    --accent:#b4532a; --ok:#2f7a4f; --shadow:0 1px 2px rgba(0,0,0,.06);
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#141416; --panel:#1c1c20; --edge:#2e2e34; --ink:#eceae6;
            --dim:#8e8b85; --accent:#e07d52; --ok:#5fbf8b;
            --shadow:0 1px 2px rgba(0,0,0,.4); }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5
         ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }
  header { position:sticky; top:0; z-index:20; background:var(--bg);
           border-bottom:1px solid var(--edge); padding:12px 20px;
           display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
  .brand { font-weight:650; letter-spacing:-.01em; margin-right:4px; }
  .brand span { color:var(--accent); }
  input[type=search], select {
    background:var(--panel); color:var(--ink); border:1px solid var(--edge);
    border-radius:7px; padding:7px 10px; font:inherit; font-size:14px; }
  input[type=search] { flex:1; min-width:180px; }
  .chips { display:flex; gap:6px; }
  .chip { border:1px solid var(--edge); background:var(--panel); color:var(--dim);
          border-radius:999px; padding:5px 12px; font-size:13px; cursor:pointer; }
  .chip[aria-pressed=true] { background:var(--accent); border-color:var(--accent);
                             color:#fff; }
  /* Who the current view belongs to. A collapsed <select> shows only the
     option's own text, so the optgroup that carries the creator goes out of
     sight the moment you pick a playlist -- this keeps it on screen. */
  .who-src { color:var(--dim); font-size:12.5px; max-width:40ch;
             overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
             background:none; border:none; padding:0; font-family:inherit; }
  .who-src[hidden] { display:none; }
  /* With a handle known, the label opens that creator's other playlists. */
  .who-src.more { cursor:pointer; }
  .who-src.more:hover { color:var(--accent); }
  .stats { color:var(--dim); font-size:13px; margin-left:auto; }
  #shelve[hidden] { display:none; }
  main { padding:20px; flex:1; min-width:0; }
  .layout { display:flex; align-items:flex-start; }
  /* The sidebar scrolls on its own and stays put under the header. */
  #side { position:sticky; top:var(--hh, 60px); width:270px; flex-shrink:0;
          height:calc(100vh - var(--hh, 60px)); overflow:auto; box-sizing:border-box;
          border-right:1px solid var(--edge); padding:12px 8px 80px; }
  #sidefilter { width:100%; box-sizing:border-box; margin-bottom:8px; }
  #sidetree { display:flex; flex-direction:column; font-size:13.5px; }
  #sidetree button { background:none; border:none; font:inherit; color:inherit;
                     cursor:pointer; text-align:left; }
  #side .sitem { display:flex; gap:8px; align-items:baseline; width:100%;
                padding:3px 8px; border-radius:6px; color:var(--ink); }
  #side .sitem:hover, #side .sfold:hover { background:var(--panel); }
  #side .sitem.on { background:var(--accent); color:#fff; }
  #side .sitem.on .ct { color:#fff; }
  #side .nm { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis;
              white-space:nowrap; }
  #side .ct { color:var(--dim); font-size:11.5px; font-variant-numeric:tabular-nums; }
  #side .sfold { display:flex; align-items:center; gap:2px; border-radius:6px;
                 padding-right:6px; margin-top:2px; }
  #side .sfold .nm { font-weight:600; padding:3px 0; }
  #side .tw { width:18px; color:var(--dim); font-size:11px; padding:3px 0; }
  #side .tbtn { color:var(--dim); padding:0 6px; border-radius:4px; visibility:hidden; }
  #side .sfold:hover .tbtn { visibility:visible; }
  #side .tbtn:hover { color:var(--accent); }
  #side .tedit { flex:1; min-width:0; font:inherit; font-size:12.5px; padding:2px 6px;
                 background:var(--panel); color:var(--ink); border:1px solid var(--accent);
                 border-radius:5px; }
  #side .snone { color:var(--dim); padding:8px; font-size:13px; }
  #sidebtn { display:none; }
  /* Phone width: the sidebar slides over the grid when you ask for it. */
  @media (max-width:800px) {
    #sidebtn { display:inline-block; }
    #side { display:none; position:fixed; left:0; z-index:35; background:var(--bg);
            box-shadow:var(--shadow); width:min(300px, 85vw); }
    body.side-on #side { display:block; }
  }
  .grid { display:grid; gap:18px;
          grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); }
  .card { background:var(--panel); border:1px solid var(--edge); border-radius:10px;
          overflow:hidden; box-shadow:var(--shadow); display:flex;
          flex-direction:column; }
  .thumbwrap { position:relative; aspect-ratio:16/9; background:#26262c;
               cursor:pointer; }
  .thumbwrap img { width:100%; height:100%; object-fit:cover; display:block; }
  .badge { position:absolute; right:6px; bottom:6px; background:rgba(0,0,0,.78);
           color:#fff; font-size:12px; padding:1px 6px; border-radius:4px;
           font-variant-numeric:tabular-nums; }
  .flag { position:absolute; left:6px; top:6px; background:rgba(0,0,0,.72);
          color:#fff; font-size:11px; padding:2px 7px; border-radius:4px; }
  .flag.have { background:var(--ok); }
  .card.watched .thumbwrap img { opacity:.45; }
  .card.gone .thumbwrap { background:repeating-linear-gradient(45deg,
      #26262c, #26262c 8px, #2c2c33 8px, #2c2c33 16px); cursor:default; }
  .card.gone .thumbwrap img, .card.gone .title { opacity:.5; }
  /* Watched: a green tick in the thumbnail's middle, big enough to read the
     state of a whole course at a glance. */
  .flag.seen { left:50%; top:50%; transform:translate(-50%,-50%); width:46px;
               height:46px; padding:0; border-radius:50%; display:grid;
               place-items:center; background:var(--ok); color:#fff;
               font-size:26px; font-weight:700; box-shadow:0 2px 10px rgba(0,0,0,.5); }
  .flag.seen[hidden] { display:none; }
  .card.watched .bar i { background:var(--ok); }
  /* How much of the open channel, playlist or collection you have watched. */
  #viewprog { display:flex; align-items:center; gap:8px; color:var(--dim);
              font-size:12.5px; white-space:nowrap; }
  #viewprog[hidden] { display:none; }
  #viewprog .track { width:90px; height:6px; border-radius:3px;
                     background:rgba(127,127,127,.25); overflow:hidden; }
  #viewprog .track i { display:block; height:100%; background:var(--ok); }
  .bar { position:absolute; left:0; right:0; bottom:0; height:3px;
         background:rgba(255,255,255,.18); }
  .bar i { display:block; height:100%; background:var(--accent); }
  .meta { padding:10px 12px 12px; display:flex; flex-direction:column; gap:6px;
          flex:1; }
  .title { font-weight:560; font-size:14px; line-height:1.35; cursor:pointer;
           display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
           overflow:hidden; }
  .sub { color:var(--dim); font-size:12.5px; }
  .row { display:flex; flex-wrap:wrap; gap:4px; margin-top:auto; padding-top:4px; }
  /* Icons take their own width; the main button gets what is left. */
  .row button.act.icon { flex:0 0 auto; width:24px; padding-left:0; padding-right:0; }
  .row button.act.primary { padding-left:6px; padding-right:6px; }
  button.act { flex:1; border:1px solid var(--edge); background:transparent;
               color:var(--ink); border-radius:6px; padding:5px 8px; font-size:12.5px;
               cursor:pointer; }
  button.act:hover { border-color:var(--accent); color:var(--accent); }
  button.act.primary { background:var(--accent); border-color:var(--accent);
                       color:#fff; }
  button.act:disabled { opacity:.55; cursor:default; }
  .icon { flex:0 0 auto; width:30px; padding:5px 4px; }
  .empty { color:var(--dim); text-align:center; padding:64px 20px; }
  .empty.thin { padding:34px 20px 4px; }
  /* Watched videos sink out of the grid into a fold at the foot of the page,
     so what is still ahead of you keeps the top. Collapsing a card in place
     would not buy anything: a grid row is as tall as its tallest card, so a
     shrunken one just leaves a hole. */
  /* The bar is pinned to the window's bottom edge rather than left at the foot
     of the document: in a 300-card view the foot of the document is a few
     hundred cards away, which is nowhere to keep a control you want to reach.
     The list opens upward from it, so the handle never moves. */
  .fold { position:fixed; left:0; right:0; bottom:0; z-index:30;
          display:flex; flex-direction:column; background:var(--bg);
          border-top:1px solid var(--edge);
          box-shadow:0 -2px 12px rgba(0,0,0,.14); }
  .foldbar { display:flex; align-items:center; gap:9px; width:100%;
             background:none; border:none; color:var(--dim); font:inherit;
             font-size:13px; cursor:pointer; padding:11px 20px; text-align:left; }
  .foldbar:hover { color:var(--ink); }
  /* Collapsed the caret points up -- the list comes up from here; open, it
     points down at the way to put it away again. */
  .foldbar .tw { font-size:10px; transition:transform .18s;
                 transform:rotate(-90deg); }
  .foldbar[aria-expanded=true] .tw { transform:rotate(90deg); }
  .foldbar .grow { flex:1; }
  .seenlist { display:flex; flex-direction:column; gap:1px;
              max-height:min(50vh,420px); overflow-y:auto;
              padding:8px 20px 6px; border-bottom:1px solid var(--edge); }
  /* Room for the bar, so the last row of cards and the job stack are not
     sitting underneath it. */
  body.hasfold main { padding-bottom:72px; }
  body.hasfold #jobs { bottom:62px; }
  /* A class selector outranks the browser's own [hidden] rule, so the
     display above would keep the list on screen while it is collapsed. */
  .seenlist[hidden] { display:none; }
  .srow { display:flex; align-items:center; gap:10px; padding:5px 6px;
          border-radius:7px; cursor:pointer; }
  .srow:hover { background:var(--panel); }
  .srow img { flex:0 0 auto; width:64px; height:36px; object-fit:cover;
              border-radius:4px; background:#26262c; opacity:.5; }
  .srow:hover img { opacity:.85; }
  .srow .t { flex:1; min-width:0; font-size:13.5px; color:var(--dim);
             overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .srow:hover .t { color:var(--ink); }
  .srow .d { font-size:12px; color:var(--dim); font-variant-numeric:tabular-nums; }
  .srow .act { flex:0 0 auto; width:28px; }
  /* The trip between grid and fold is played out where the card stands, so it
     is seen to go somewhere rather than blink across the page. */
  .card.sinking, .srow.rising { transition:opacity .22s, transform .22s;
                                opacity:0; pointer-events:none; }
  .card.sinking { transform:translateY(16px) scale(.96); }
  .srow.rising { transform:translateY(-12px); }
  @media (prefers-reduced-motion: reduce) {
    .card.sinking, .srow.rising { transition:none; }
  }
  /* player overlay */
  #player { position:fixed; inset:0; background:rgba(8,8,10,.94); z-index:50;
            display:none; flex-direction:column; padding:24px; }
  #player.on { display:flex; }
  #player video { width:100%; max-width:1100px; max-height:70vh; margin:0 auto;
                  background:#000; border-radius:8px; outline:none; }
  #pmeta { max-width:1100px; margin:14px auto 0; width:100%; color:#e9e7e3; }
  #pmeta h2 { margin:0 0 4px; font-size:17px; font-weight:600; }
  #pmeta .sub { color:#9b988f; }
  /* Chapters: the bar is split into the creator's sections like YouTube's
     timeline, each filling as you pass through it; the list jumps to one. */
  #pchap { display:flex; gap:3px; max-width:1100px; width:100%; height:6px;
           flex-shrink:0;
           margin:8px auto 0; }
  #pchap[hidden], #pchlist[hidden] { display:none; }
  #pchap button { flex:1 1 0; min-width:2px; padding:0; border:none;
                  border-radius:2px; cursor:pointer; transition:transform .1s;
                  background:linear-gradient(to right, var(--accent) var(--p,0%),
                                             rgba(233,231,227,.22) var(--p,0%)); }
  #pchap button:hover { transform:scaleY(1.8); }
  #pchlist { list-style:none; margin:10px 0 0; padding:0; max-height:18vh;
             overflow:auto; font-size:13.5px; color-scheme:dark; }
  #pchlist button { display:flex; gap:10px; width:100%; text-align:left;
                    background:none; border:none; border-radius:4px; padding:2px 6px;
                    font:inherit; color:#c3c0b8; cursor:pointer; }
  #pchlist button:hover { background:rgba(233,231,227,.08); color:#e9e7e3; }
  #pchlist li.on button { color:var(--accent); }
  #pchlist .ts { color:#9b988f; min-width:5ch; font-variant-numeric:tabular-nums; }
  /* Speed: the browser's own menu forgets it on every new video, so the
     choice lives here and follows you from one video to the next. */
  #pspeed, #pquality { display:flex; gap:4px; margin-top:8px; }
  #pquality[hidden] { display:none; }
  #pspeed button, #pquality button { background:none; border:1px solid rgba(233,231,227,.25);
                   border-radius:6px; padding:2px 9px; font:inherit; font-size:12.5px;
                   color:#c3c0b8; cursor:pointer; font-variant-numeric:tabular-nums; }
  #pspeed button:hover, #pquality button:hover { border-color:var(--accent); color:var(--accent); }
  #pspeed button.on, #pquality button.on { background:var(--accent); border-color:var(--accent); color:#fff; }
  /* Marks: ticks on a strip under the picture, and a list you can annotate. */
  #pmstrip { position:relative; max-width:1100px; width:100%; height:12px;
             margin:4px auto 0; flex-shrink:0; }
  #pmstrip button { position:absolute; top:0; width:4px; height:12px; padding:0;
                    margin-left:-2px; border:none; border-radius:2px;
                    background:#f2c14e; cursor:pointer; }
  #pmstrip button:hover { transform:scaleX(1.8); }
  #pmarkrow { display:flex; align-items:center; gap:10px; margin-top:10px; }
  #pmarkrow .hint { color:#9b988f; font-size:12px; }
  #pmarkadd { background:none; border:1px solid rgba(233,231,227,.35); color:#e9e7e3;
              border-radius:6px; padding:4px 10px; font:inherit; font-size:13px;
              cursor:pointer; }
  #pmarkadd:hover { border-color:#f2c14e; color:#f2c14e; }
  #pmarks { list-style:none; margin:6px 0 0; padding:0; max-height:16vh; overflow:auto;
            font-size:13.5px; color-scheme:dark; }
  #pmarks li { display:flex; align-items:center; gap:8px; padding:1px 0; }
  #pmarks .ts { background:none; border:none; color:#f2c14e; font:inherit; cursor:pointer;
                min-width:5ch; text-align:left; font-variant-numeric:tabular-nums; padding:2px 6px; }
  #pmarks .note { flex:1; min-width:0; background:none; border:1px solid transparent;
                  color:#c3c0b8; font:inherit; padding:2px 6px; border-radius:4px; }
  #pmarks .note:hover { border-color:rgba(233,231,227,.2); }
  #pmarks .note:focus { border-color:#f2c14e; outline:none; color:#e9e7e3; }
  #pmarks .x { background:none; border:none; color:#9b988f; cursor:pointer; font-size:16px; }
  #pmarks .x:hover { color:#e9e7e3; }
  #qmenu { position:fixed; z-index:70; background:var(--panel); border:1px solid var(--edge);
           border-radius:8px; box-shadow:0 6px 24px rgba(0,0,0,.25); padding:4px;
           display:flex; flex-direction:column; min-width:190px; }
  #qmenu .qh { color:var(--dim); font-size:12px; padding:4px 8px 6px; }
  #qmenu button { background:none; border:none; color:var(--ink); font:inherit;
                  font-size:13.5px; text-align:left; padding:5px 8px; border-radius:5px;
                  cursor:pointer; }
  #qmenu button:hover { background:var(--accent); color:#fff; }
  #pdesc { max-height:20vh; overflow:auto; white-space:pre-wrap; margin-top:10px;
           font-size:13.5px; color:#c3c0b8; }
  /* The Toggl timer, when a token is configured. Without one the whole row
     stays away rather than offering a button that cannot work. */
  #ptoggl { display:flex; align-items:center; gap:10px; margin-top:12px; }
  #ptoggl[hidden] { display:none; }
  #tgbtn { border:1px solid rgba(233,231,227,.35); background:transparent;
           color:#e9e7e3; border-radius:6px; padding:6px 12px; font:inherit;
           font-size:13px; cursor:pointer; }
  #tgbtn:hover { border-color:var(--accent); color:var(--accent); }
  #tgbtn.on { background:var(--accent); border-color:var(--accent); color:#fff; }
  #tgbtn:disabled { opacity:.55; cursor:default; }
  #tgwhat { color:#9b988f; font-size:12.5px; overflow:hidden;
            text-overflow:ellipsis; white-space:nowrap; }
  /* z-index matters: the button sits over the video's top-right corner, and
     without it the <video> swallows every click that lands on the glyph. */
  #pclose { position:absolute; top:10px; right:14px; z-index:2;
            width:40px; height:40px; display:grid; place-items:center; padding:0;
            background:none; border:none; border-radius:8px; color:#e9e7e3;
            font-size:26px; line-height:1; cursor:pointer; }
  #pclose:hover { background:rgba(233,231,227,.14); }
  .seq { position:absolute; left:6px; top:6px; background:var(--accent);
         color:#fff; font-size:11px; font-weight:600; padding:2px 7px;
         border-radius:4px; font-variant-numeric:tabular-nums; }
  /* One overlay style, two sheets: add to a collection, and track a source. */
  .sheet { position:fixed; inset:0; background:rgba(8,8,10,.6); z-index:60;
           display:none; align-items:center; justify-content:center; }
  .sheet.on { display:flex; }
  .sheet .box { background:var(--panel); border:1px solid var(--edge);
                border-radius:10px; padding:18px; width:min(440px,92vw);
                box-shadow:0 8px 30px rgba(0,0,0,.3); }
  .sheet h3 { margin:0 0 4px; font-size:15px; }
  .sheet .who { color:var(--dim); font-size:12.5px; margin-bottom:12px;
                overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  /* The add-a-source hint is a sentence, not a title: let it wrap. */
  .sheet .hint { color:var(--dim); font-size:12.5px; white-space:normal; }
  .sheet .err { color:#d4705c; font-size:12.5px; margin-top:10px; }
  .sheet label { display:flex; gap:9px; align-items:center; padding:6px 2px;
                 font-size:14px; cursor:pointer; }
  .sheet .mk { display:flex; gap:6px; margin-top:12px; }
  .sheet .mk input { flex:1; background:var(--bg); color:var(--ink);
                     border:1px solid var(--edge); border-radius:6px;
                     padding:6px 9px; font:inherit; font-size:13.5px; }
  /* A creator's playlist index runs to dozens; it scrolls inside the sheet
     rather than pushing the buttons off the bottom of the screen. */
  .sheet .picks { max-height:min(46vh,340px); overflow-y:auto; margin-top:10px;
                  border-top:1px solid var(--edge); border-bottom:1px solid var(--edge);
                  padding:4px 0; }
  .sheet .picks label { padding:5px 2px; font-size:13.5px; align-items:start; }
  /* min-width:0 so a long course title wraps inside the row instead of
     stretching it past the sheet. */
  .sheet .picks label span { flex:1; min-width:0; overflow-wrap:anywhere; }
  .sheet .picks input { margin-top:3px; }
  .sheet .picks .tag { color:var(--dim); font-size:11.5px; flex:0 0 auto;
                       margin-top:2px; }
  .sheet .picks .sec { color:var(--dim); font-size:11.5px; text-transform:uppercase;
                       letter-spacing:.06em; padding:10px 2px 2px; }
  .sheet .picks .sec:first-child { padding-top:4px; }
  .sheet .bar2 { display:flex; gap:6px; align-items:center; margin-top:12px; }
  .sheet .bar2 .grow { flex:1; }
  .sheet .link { border:0; background:none; color:var(--accent); font:inherit;
                 font-size:12.5px; padding:2px 4px; cursor:pointer; }
  .sheet .link:hover { text-decoration:underline; }
  .sheet .count { color:var(--dim); font-size:12.5px; }
  /* The Toggl sheet carries three fields a row, so it gets more room. */
  .sheet .box.wide { width:min(680px,94vw); }
  .tgrows { display:flex; flex-direction:column; gap:12px; padding:2px 2px 0;
            max-height:min(58vh,440px); overflow-y:auto; }
  .tgrow { display:grid; gap:6px;
           grid-template-columns:repeat(3,minmax(0,1fr)); }
  .tgrow .ch { grid-column:1/-1; font-size:12.5px; color:var(--dim);
               overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .tgrow input { background:var(--bg); color:var(--ink); min-width:0;
                 border:1px solid var(--edge); border-radius:6px;
                 padding:6px 8px; font:inherit; font-size:13px; }
  .tgrow input:focus { outline:none; border-color:var(--accent); }
  @media (max-width:560px) {
    .tgrow { grid-template-columns:1fr; }
  }
  #jobs { position:fixed; right:16px; bottom:16px; width:300px; z-index:40;
          display:flex; flex-direction:column; gap:8px; }
  .job { position:relative; background:var(--panel); border:1px solid var(--edge);
         border-radius:8px; padding:9px 11px; font-size:12.5px;
         box-shadow:var(--shadow); }
  .job .t { font-weight:550; overflow:hidden; text-overflow:ellipsis;
            white-space:nowrap; padding-right:18px; }
  .job .x { position:absolute; top:4px; right:5px; width:20px; height:20px;
            display:grid; place-items:center; border:0; border-radius:4px;
            background:none; color:var(--dim); font:inherit; font-size:14px;
            line-height:1; cursor:pointer; }
  .job .x:hover { background:var(--edge); color:var(--ink); }
  #jobs .clearall { align-self:flex-end; border:1px solid var(--edge);
                    border-radius:6px; background:var(--panel); color:var(--dim);
                    font:inherit; font-size:12px; padding:3px 8px; cursor:pointer;
                    box-shadow:var(--shadow); }
  #jobs .clearall:hover { color:var(--ink); }
  .job .d { color:var(--dim); font-variant-numeric:tabular-nums; }
  .job .track { height:3px; background:var(--edge); border-radius:2px; margin-top:6px; }
  .job .track i { display:block; height:100%; background:var(--accent);
                  border-radius:2px; transition:width .3s; }
  .job.error { border-color:#a8412f; }
  .job.error .d { color:#d4705c; }
</style>
</head>
<body>
<header>
  <div class="brand">yt<span>·</span>local</div>
  <input type="search" id="q" placeholder="Search titles and descriptions…" autocomplete="off">
  <button class="chip" id="sidebtn" title="Channels and playlists">☰</button>
  <button class="who-src" id="whosrc" hidden></button>
  <button class="chip" id="shelve" hidden></button>
  <select id="sort" title="Sort order (remembered per view)"></select>
  <div class="chips">
    <button class="chip" id="f-have"      aria-pressed="false">Downloaded</button>
    <button class="chip" id="f-starred"   aria-pressed="false">Starred</button>
    <button class="chip" id="f-unwatched" aria-pressed="false">Unwatched</button>
    <button class="chip" id="f-hidden" aria-pressed="false"
            title="Show what is hidden — private or deleted entries, and anything you hid">Hidden</button>
  </div>
  <button class="chip" id="newsrc"
          title="Track a channel or playlist">＋ source</button>
  <button class="chip" id="newcoll" title="New collection">＋ collection</button>
  <button class="chip" id="togglcfg"
          title="How each channel shows up in Toggl Track">⏱ toggl</button>
  <div id="viewprog" hidden><span class="track"><i></i></span><span></span></div>
  <div class="stats" id="stats"></div>
</header>
<div class="layout">
<aside id="side">
  <input type="search" id="sidefilter" placeholder="Find a channel or playlist…"
         autocomplete="off">
  <datalist id="topiclist"></datalist>
  <nav id="sidetree"></nav>
</aside>
<main>
  <div class="grid" id="grid"></div>
  <div class="empty" id="empty" hidden></div>
</main>
</div>

<div class="fold" id="fold" hidden>
  <div class="seenlist" id="seenlist" hidden></div>
  <button class="foldbar" id="foldbar" aria-expanded="false"
          aria-controls="seenlist">
    <span class="tw">&#9654;</span>
    <span class="grow" id="foldn"></span>
    <span id="foldhint">show</span>
  </button>
</div>

<div id="jobs"></div>

<div id="modal" class="sheet"><div class="box">
  <h3>Add to collection</h3>
  <div class="who" id="mwho"></div>
  <div id="mlist"></div>
  <div class="mk"><input id="mnew" placeholder="New collection…" autocomplete="off">
    <button class="act" id="madd">Create</button></div>
</div></div>

<div id="tgmodal" class="sheet"><div class="box wide">
  <h3>Toggl Track</h3>
  <div class="who hint">One row per channel: what to call it in Toggl, the
    project it counts towards, and any tags. Leave a field blank and the
    channel's own name stands in. A project has to exist in Toggl already —
    it will not be created for you. Needs <code>toggl_token</code> in your
    config; without one the timer button stays away.</div>
  <div class="who hint" id="tgoff" hidden style="color:#d4705c">
    No <code>toggl_token</code> in your config yet, so nothing here can start a
    timer. Toggl → Profile settings → API token, then restart <code>yt
    serve</code>.</div>
  <div class="tgrows" id="tgrows"></div>
  <div class="bar2">
    <span class="count grow" id="tgnote"></span>
    <button class="act" id="tgdone">Done</button>
  </div>
</div></div>

<div id="srcmodal" class="sheet"><div class="box">
  <h3 id="stitle">Track a channel or playlist</h3>
  <div class="who hint" id="shint">An @handle, a channel URL, a playlist URL
    or <code>PL…</code> id, or one video's link — unlisted ones too.</div>
  <div id="sask">
    <div class="mk" style="margin-top:0">
      <input id="snew" placeholder="@3blue1brown" autocomplete="off"
             spellcheck="false">
      <button class="act primary" id="sadd">Add</button></div>
    <div class="bar2">
      <span class="count grow">…or see a creator's courses, live and playlists:</span>
      <button class="link" id="sbrowse">Browse →</button></div>
  </div>
  <div id="spick" hidden>
    <div class="bar2" style="margin-top:0">
      <span class="count grow" id="spickwho"></span>
      <button class="link" id="sall">all</button>
      <button class="link" id="snone">none</button></div>
    <div class="picks" id="spicks"></div>
    <div class="bar2">
      <button class="link grow" style="text-align:left" id="sback">← back</button>
      <button class="act primary" id="spickadd">Track selected</button></div>
  </div>
  <div class="err" id="serr" hidden></div>
  <div class="who hint" style="margin:12px 0 0">Cataloguing reads titles only —
    nothing downloads until you ask for it.</div>
</div></div>

<div id="player">
  <button id="pclose" title="Close (Esc)">&times;</button>
  <video id="pvideo" controls playsinline></video>
  <div id="pchap" hidden></div>
  <div id="pmstrip"></div>
  <div id="pmeta"><h2 id="ptitle"></h2><div class="sub" id="psub"></div>
    <div class="sub" id="pstatus" hidden></div>
    <div id="pspeed" title="Speed (Shift+&lt; / Shift+&gt;)"></div>
    <div id="pquality" title="Streaming quality" hidden></div>
    <ol id="pchlist" hidden></ol>
    <div id="pmarkrow"><button id="pmarkadd" title="Mark where you are (M)">🔖 Mark this spot</button>
      <span class="hint">M · click a mark to jump back</span></div>
    <ol id="pmarks"></ol>
    <div id="pdesc"></div></div>
</div>

<script>
const state = { q:"", source:"", collection:"", have:null, starred:false,
                unwatched:false, hidden:false, videos:[], ordered:false, sources:[],
                collections:[], sort:"default", toggl:{}, togglChannels:[] };
const $ = s => document.querySelector(s);
const fmtDur = s => { if(!s) return ""; s=Math.round(s);
  const h=Math.floor(s/3600), m=Math.floor(s%3600/60), x=s%60;
  return h ? `${h}:${String(m).padStart(2,"0")}:${String(x).padStart(2,"0")}`
           : `${m}:${String(x).padStart(2,"0")}`; };
const fmtDate = v => !v.date ? "" : (v.date_approx ? "~" + v.date.slice(0,7) : v.date);
const fmtSize = b => b ? (b/1e9 >= 1 ? (b/1e9).toFixed(1)+" GB" : Math.round(b/1e6)+" MB") : "";

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(()=>({}))).error || r.statusText);
  return r.json();
}
const post = (p, body) => api(p, {method:"POST", headers:{"Content-Type":"application/json"},
                                 body: JSON.stringify(body||{})});

function params() {
  const p = new URLSearchParams();
  if (state.q) p.set("q", state.q);
  if (state.source) p.set("source", state.source);
  if (state.collection) p.set("collection", state.collection);
  if (state.have !== null) p.set("have", state.have ? "1" : "0");
  if (state.starred) p.set("starred", "1");
  if (state.unwatched) p.set("unwatched", "1");
  if (state.hidden) p.set("hidden", "1");
  return p.toString();
}

let pickerKey = "";
// The sidebar sits right under the header, whose height changes as it wraps.
new ResizeObserver(([e]) => document.documentElement.style
  .setProperty("--hh", `${e.target.offsetHeight}px`)).observe($("header"));
async function refresh(opts) {
  const qs = params();
  // The view lives in the address bar, so a refresh (or a bookmark) lands you
  // where you were rather than back on Everything. Picking a source is a
  // navigation and gets its own history entry; typing in the search box or
  // flipping a chip only rewrites the current one.
  const step = opts && opts.push ? "pushState" : "replaceState";
  history[step](null, "", qs ? "?" + qs : location.pathname);
  const d = await api("/api/state?" + qs);
  state.videos = d.videos;
  state.ordered = d.ordered;
  state.sources = d.sources;
  state.collections = d.collections;
  state.sort = d.sort;
  state.toggl = d.toggl || {};
  state.togglChannels = d.toggl_channels || [];
  buildPicker(d.sources, d.collections);
  buildSorts(d.sorts, d.sort);
  const s = d.stats;
  $("#stats").textContent =
    `${s.have}/${s.total} on disk · ${fmtSize(s.bytes)} · ` +
    `${s.channels} channels · ${s.playlists} playlists` +
    (s.hidden ? ` · ${s.hidden} hidden` : "");
  render(d.videos);
  paintViewProgress();
  renderJobs(d.jobs);
}

// One mark per kind of source, the same ones `yt sources` prints.
const GLYPHS = {channel:"▸", course:"◆", live:"●", playlist:"▤", picks:"✦"};
const glyph = s => GLYPHS[s.kind === "channel" ? "channel" : s.section || "playlist"];

/* ---- sidebar: topics, then creators, then their channel and playlists ----
   A dropdown stops scaling past a dozen creators. Here every creator sits on
   a topic shelf you choose (Japanese, Unreal...), folds open to what you track
   from them, and the box at the top narrows the whole tree as you type. */
let sideOpen = new Set();
try { sideOpen = new Set(JSON.parse(localStorage.getItem("yt.side-open") || "[]")); }
catch (e) {}
const saveSideOpen = () => {
  try { localStorage.setItem("yt.side-open", JSON.stringify([...sideOpen])); } catch (e) {}
};
let sideFilter = "";
const NO_TOPIC = "No topic";

function buildPicker(sources, colls) {
  const known = state.source ? sources.some(s => s.id === state.source)
              : state.collection ? colls.some(c => String(c.id) === String(state.collection))
              : true;
  if (!known) {
    // A URL naming a source that has since been forgotten: back to Everything.
    state.source = state.collection = "";
    refresh();
    return;
  }
  paintWho(sources, colls);
  paintShelve(sources);
  // The 1.2s job polling refreshes too; rebuilding under an open topic box
  // would throw away what you were typing.
  if ($("#side .tedit")) return;
  const key = JSON.stringify([sources.map(s => [s.id, s.group, s.topic, s.section,
                                                 s.creator, s.shelved, s.seen, s.total]),
                              colls.map(c => [c.id, c.seen, c.total]),
                              sideFilter, [...sideOpen], state.source, state.collection]);
  if (key === pickerKey) return;
  pickerKey = key;
  paintSide(sources, colls);
}

function paintSide(sources, colls) {
  const tree = $("#sidetree");
  tree.replaceChildren();
  const q = sideFilter.toLowerCase();
  const hit = (...xs) => !q || xs.some(x => x && x.toLowerCase().includes(q));
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };
  const count = it => it.total ? `${it.seen}/${it.total}` : "";
  const row = (label, id, it, depth) => {
    const b = el("button", "sitem" + (id === activeId() ? " on" : ""));
    b.style.paddingLeft = `${8 + depth * 14}px`;
    b.append(el("span", "nm", label), el("span", "ct", count(it)));
    b.title = it.total ? `${label} — ${it.seen} watched, ${it.have} on disk, of ${it.total}` : label;
    b.onclick = () => pick(id);
    return b;
  };
  // A fold: its header toggles it open; searching opens everything it holds.
  const fold = (k, label, n, depth, extra) => {
    const open = !!q || sideOpen.has(k);
    const h = el("div", "sfold");
    h.style.paddingLeft = `${4 + depth * 14}px`;
    const t = el("button", "tw", open ? "▾" : "▸");
    const nm = el("button", "nm", label);
    const toggle = () => {
      sideOpen.has(k) ? sideOpen.delete(k) : sideOpen.add(k);
      saveSideOpen(); pickerKey = ""; buildPicker(state.sources, state.collections);
    };
    t.onclick = toggle;
    nm.onclick = extra && extra.onName ? extra.onName : toggle;
    h.append(t, nm);
    if (n != null) h.append(el("span", "ct", n));
    if (extra && extra.tail) h.append(extra.tail);
    tree.append(h);
    return open;
  };

  tree.append(row("Everything", "", {}, 0));

  // Group live sources by creator (the server sends them already ordered),
  // then creators by topic.
  const creators = new Map();
  for (const s of sources.filter(s => !s.shelved)) {
    if (!creators.has(s.group))
      creators.set(s.group, {key: s.group, name: s.creator || "unknown creator",
                             handle: s.handle, topic: s.topic || NO_TOPIC, items: []});
    creators.get(s.group).items.push(s);
  }
  const topics = new Map();
  for (const c of creators.values()) {
    if (!topics.has(c.topic)) topics.set(c.topic, []);
    topics.get(c.topic).push(c);
  }
  const names = [...topics.keys()].sort((a, b) =>
    (a === NO_TOPIC) - (b === NO_TOPIC) || a.localeCompare(b));
  // Everyone on one shelf needs no shelf at all.
  const flat = names.length === 1 && names[0] === NO_TOPIC;
  for (const t of names) {
    const all = topics.get(t);
    const topicHit = q && t !== NO_TOPIC && hit(t);
    const shown = all.map(c => {
      const whole = topicHit || hit(c.name, c.handle);
      const items = whole ? c.items : c.items.filter(s => hit(s.name));
      return items.length ? {...c, items} : null;
    }).filter(Boolean);
    if (!shown.length) continue;
    const depth = flat ? 0 : 1;
    if (!flat && !fold("t:" + t, t, all.length, 0)) continue;
    for (const c of shown) {
      const chan = c.items.find(s => s.kind === "channel");
      const edit = el("button", "tbtn", "⋯");
      edit.title = `Topic for ${c.name}`;
      edit.onclick = e => { e.stopPropagation(); editTopic(edit, c); };
      // With their channel tracked, the name opens all their videos.
      const open = fold("g:" + c.key, c.name, null, depth, {
        tail: edit,
        onName: chan ? () => pick("s:" + chan.id) : null});
      if (!open) continue;
      for (const s of c.items)
        tree.append(row(s.kind === "channel" ? `${glyph(s)} All videos` : `${glyph(s)} ${s.name}`,
                        "s:" + s.id, s, depth + 1));
    }
  }

  const cs = colls.filter(c => hit(c.name));
  if (cs.length && fold("collections", "Collections", colls.length, 0))
    for (const c of cs) tree.append(row(c.name, "c:" + c.id, c, 1));
  const shelved = sources.filter(s => s.shelved && hit(s.name, s.creator));
  if (shelved.length && fold("shelved", "Shelved", shelved.length, 0))
    for (const s of shelved)
      tree.append(row(s.kind === "channel" ? `${glyph(s)} ${s.name}`
                                           : `${glyph(s)} ${s.name} — ${s.creator || "?"}`,
                      "s:" + s.id, s, 1));
  if (tree.children.length === 1 && q)
    tree.append(el("div", "snone", "Nothing tracked matches."));
}

const activeId = () => state.source ? "s:" + state.source
                     : state.collection ? "c:" + state.collection : "";

function pick(id) {
  state.source     = id.startsWith("s:") ? id.slice(2) : "";
  state.collection = id.startsWith("c:") ? id.slice(2) : "";
  document.body.classList.remove("side-on");          // phone: get out of the way
  refresh({push: true});
}

// An inline box, suggesting the topics already in use; Enter keeps it,
// Escape or leaving it blank-and-unchanged walks away.
function editTopic(btn, c) {
  const inp = document.createElement("input");
  inp.className = "tedit";
  inp.value = c.topic === NO_TOPIC ? "" : c.topic;
  inp.placeholder = "Topic, e.g. Japanese";
  inp.setAttribute("list", "topiclist");
  $("#topiclist").replaceChildren(...[...new Set(state.sources.map(s => s.topic).filter(Boolean))]
    .sort().map(t => Object.assign(document.createElement("option"), {value: t})));
  btn.replaceWith(inp);
  inp.focus(); inp.select();
  let done = false;
  const finish = async save => {
    if (done) return;
    done = true;
    if (save) {
      const topic = inp.value.trim();
      await post("/api/topic", {creator: c.key, topic}).catch(e => alert(e.message));
      if (topic) sideOpen.add("t:" + topic);
      saveSideOpen();
    }
    inp.remove();
    pickerKey = "";
    refresh();
  };
  inp.onkeydown = e => {
    if (e.key === "Enter") finish(true);
    else if (e.key === "Escape") { e.stopPropagation(); finish(false); }
  };
  inp.onblur = () => finish(true);
}

$("#sidefilter").addEventListener("input", e => {
  sideFilter = e.target.value.trim();
  pickerKey = ""; buildPicker(state.sources, state.collections);
});
$("#sidebtn").onclick = () => document.body.classList.toggle("side-on");

// The creator of the view you are in, kept beside the picker: a collapsed
// select shows the option text alone, and the option text is the bit that is
// ambiguous between two playlists called the same thing.
function paintWho(sources, colls) {
  const el = $("#whosrc");
  const src = state.source && sources.find(s => s.id === state.source);
  let text = "";
  if (src && src.kind === "playlist")
    text = glyph(src) + " " + (src.creator || "unknown creator");
  else if (src)
    text = glyph(src) + " " + (src.creator || src.name);
  else if (state.collection)
    text = "yours";
  const handle = src && src.handle;
  if (handle) text += ` · ${handle} — more →`;
  el.textContent = text;
  el.classList.toggle("more", !!handle);
  el.dataset.handle = handle || "";
  el.title = handle ? `See ${handle}'s courses, live and playlists, and track more`
                    : text && src ? src.name : "";
  el.hidden = !text;
}
$("#whosrc").onclick = () => {
  const handle = $("#whosrc").dataset.handle;
  if (!handle) return;
  $("#newsrc").onclick();
  $("#snew").value = handle;
  browseSource();
};

// Only a source can be shelved; the button names what pressing it would do.
function paintShelve(sources) {
  const b = $("#shelve");
  const src = state.source && sources.find(s => s.id === state.source);
  b.hidden = !src;
  if (!src) return;
  b.textContent = src.shelved ? "Unshelve" : "Shelve";
  b.title = src.shelved
    ? "Bring it back into the picker, Everything and full syncs"
    : "Put it away for later: out of the picker, Everything and full syncs. " +
      "Still tracked, and still under Shelved in the picker.";
}
$("#shelve").onclick = async () => {
  const src = state.sources.find(s => s.id === state.source);
  if (!src) return;
  await post("/api/shelve", {source: src.id, value: !src.shelved});
  refresh();
};

function buildSorts(sorts, current) {
  const sel = $("#sort");
  if (!sel.options.length) {
    for (const s of sorts) {
      const o = document.createElement("option");
      o.value = s.key; o.textContent = s.label;
      sel.appendChild(o);
    }
  }
  // The server decides which sort this view gets, so the dropdown follows it
  // rather than the other way round -- switching source shows that view's own.
  // Only when it actually differs: job polling refreshes every 1.2s and must
  // not reach into a dropdown the user has open.
  if (sel.value !== current) sel.value = current;
}

// How long a card is given to play itself out before the page is rebuilt
// around its absence.
const SINK_MS = 240;
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
let foldOpen = false;
try { foldOpen = localStorage.getItem("yt.watched-open") === "1"; } catch (e) {}

// A card in mid-flight between the grid and the fold must not be torn out from
// under its own animation, and job polling rebuilds the page every 1.2s.
let sinking = 0;
function moveOut(el, cls) {
  sinking++;
  el.classList.add(cls);
  setTimeout(() => { if (!--sinking) render(state.videos); },
             REDUCED ? 0 : SINK_MS);
}

function render(vs) {
  if (sinking) return;
  const grid = $("#grid"), empty = $("#empty"), fold = $("#fold");
  grid.innerHTML = "";
  fold.hidden = true;
  document.body.classList.remove("hasfold");
  empty.classList.remove("thin");
  empty.hidden = vs.length > 0;
  if (!vs.length) {
    empty.textContent = state.hidden
      ? "Nothing is hidden."
      : state.q || state.source || state.collection || state.have !== null
      ? "Nothing matches those filters."
      : "Catalog is empty — press ＋ source above, or run  yt add @channel.";
    return;
  }
  // Under a playlist's or a collection's own order the position numbers are
  // the whole point, so nothing is allowed to move; everywhere else what you
  // have already seen drops below the fold.
  const split = !state.ordered;
  const live = split ? vs.filter(v => !v.watched) : vs;
  const seen = split ? vs.filter(v =>  v.watched) : [];
  live.forEach((v, i) => grid.appendChild(card(v, state.ordered ? i + 1 : null)));

  if (!live.length && seen.length) {
    empty.hidden = false;
    empty.classList.add("thin");
    empty.textContent = "You have watched everything here.";
  }
  if (!seen.length) return;
  fold.hidden = false;
  document.body.classList.add("hasfold");
  $("#foldn").textContent = `Watched · ${seen.length}`;
  const list = $("#seenlist");
  list.innerHTML = "";
  seen.forEach(v => list.appendChild(seenRow(v)));
  paintFold();
}

function paintViewProgress() {
  const it = state.source ? state.sources.find(s => s.id === state.source)
           : state.collection ? state.collections.find(c => String(c.id) === String(state.collection))
           : null;
  const box = $("#viewprog");
  box.hidden = !it || !it.total;
  if (box.hidden) return;
  box.querySelector("i").style.width = `${100 * it.seen / it.total}%`;
  box.lastChild.textContent = `✓ ${it.seen} of ${it.total} watched`;
}

// A tick or an undo changes the count without a full reload.
function bumpSeen(by) {
  const it = state.source ? state.sources.find(s => s.id === state.source)
           : state.collections.find(c => String(c.id) === String(state.collection));
  if (it) it.seen = Math.max(0, it.seen + by);
  paintViewProgress();
}

function paintFold() {
  $("#foldbar").setAttribute("aria-expanded", String(foldOpen));
  $("#foldhint").textContent = foldOpen ? "hide" : "show";
  $("#seenlist").hidden = !foldOpen;
}
$("#foldbar").onclick = () => {
  foldOpen = !foldOpen;
  try { localStorage.setItem("yt.watched-open", foldOpen ? "1" : "0"); }
  catch (e) {}
  paintFold();
};

// One line apiece down in the fold: enough to recognise a video and send it
// back up, without the full card's worth of buttons you are done with.
function seenRow(v) {
  const el = document.createElement("div");
  el.className = "srow";
  el.innerHTML = `<img loading="lazy" src="/thumb/${v.id}" alt="">
                  <span class="t"></span>
                  <span class="d">${v.duration ? fmtDur(v.duration) : ""}</span>`;
  el.querySelector(".t").textContent =
    v.unavailable ? "Private or deleted video" : v.title;
  el.title = v.unavailable ? v.id : v.title;
  if (v.have || !v.unavailable) el.onclick = () => open_(v);
  else el.style.cursor = "default";

  if (!v.have && !v.unavailable) {
    const get = document.createElement("button");
    get.className = "act icon"; get.textContent = "↓";
    get.title = "Download";
    get.onclick = e => { e.stopPropagation(); grab(v, get); };
    el.appendChild(get);
  }
  // Not a tick: every row down here is already watched, so a checkmark would
  // read as "mark this done" when the only thing it does is undo that.
  const back = document.createElement("button");
  back.className = "act icon"; back.textContent = "↺";
  back.title = "Put back in the queue — marks it not watched";
  back.onclick = async e => {
    e.stopPropagation();
    const r = await post(`/api/watched/${v.id}`);
    v.watched = r.watched;
    bumpSeen(r.watched ? 1 : -1);
    moveOut(el, "rising");
  };
  el.appendChild(back);
  return el;
}

function card(v, seq) {
  const el = document.createElement("div");
  el.className = "card" + (v.watched ? " watched" : "")
                        + (v.unavailable ? " gone" : "");
  // Streamed videos keep their place too, so any video can show a bar.
  const pct = v.watched ? 100 : v.duration && v.progress
              ? Math.min(100, 100 * v.progress / v.duration) : 0;
  el.innerHTML = `
    <div class="thumbwrap">
      <img loading="lazy" src="/thumb/${v.id}" alt="">
      ${seq ? `<span class="seq">${seq}</span>` : ''}
      ${v.have ? `<span class="flag have" style="${seq ? 'left:auto;right:6px' : ''}">${v.audio ? "audio ♪" : "on disk"}</span>` : ''}
      ${v.starred ? '<span class="flag" style="left:auto;right:6px;top:6px">★</span>' : ''}
      ${v.duration ? `<span class="badge">${fmtDur(v.duration)}</span>` : ''}
      ${v.marks ? `<span class="flag" style="top:auto;bottom:6px" title="${v.marks} marked spot${v.marks > 1 ? "s" : ""}">🔖 ${v.marks}</span>` : ''}
      <span class="flag seen" title="Watched" ${v.watched ? '' : 'hidden'}>✓</span>
      ${pct ? `<div class="bar"><i style="width:${pct}%"></i></div>` : ''}
    </div>
    <div class="meta">
      <div class="title"></div>
      <div class="sub"></div>
      <div class="row"></div>
    </div>`;
  // An unavailable entry has no title of its own -- the id stood in for one.
  el.querySelector(".title").textContent =
    v.unavailable ? "Private or deleted video" : v.title;
  el.querySelector(".sub").textContent = v.unavailable
    ? `${v.id} · nothing to play`
    : [v.channel, fmtDate(v), v.have ? fmtSize(v.size) : null].filter(Boolean).join(" · ");

  const row = el.querySelector(".row");
  const main = document.createElement("button");
  main.className = "act primary";
  main.textContent = v.have ? "Watch" : "Download";
  main.onclick = () => v.have ? open_(v) : grab(v, main);
  main.disabled = v.unavailable && !v.have;
  row.appendChild(main);

  if (!v.unavailable) {
    const q = document.createElement("button");
    q.className = "act icon"; q.textContent = "▾";
    q.title = v.have ? "Download again at another quality" : "Download at a chosen quality";
    q.onclick = e => { e.stopPropagation(); qualityMenu(v, q, main); };
    row.appendChild(q);
  }

  if (!v.have && !v.unavailable) {
    const play = document.createElement("button");
    play.className = "act icon";
    play.textContent = "▶";
    play.title = "Stream it now — nothing is saved to disk";
    play.onclick = () => open_(v);
    row.appendChild(play);
  }

  const hide = document.createElement("button");
  hide.className = "act icon";
  hide.textContent = v.hidden ? "◉" : "⊘";
  hide.title = v.hidden ? "Unhide — keep showing this one" : "Hide from every view";
  hide.onclick = async () => {
    const r = await post(`/api/hidden/${v.id}`);
    v.hidden = r.hidden;
    // Either way it no longer belongs in the list it is sitting in.
    refresh();
  };
  row.appendChild(hide);

  const star = document.createElement("button");
  star.className = "act icon"; star.title = "Star";
  star.textContent = v.starred ? "★" : "☆";
  star.onclick = async () => { const r = await post(`/api/star/${v.id}`);
                               v.starred = r.starred;
                               star.textContent = r.starred ? "★" : "☆"; };
  row.appendChild(star);

  // The glyph is what the button will do, not what the video already is: a
  // tick you press to tick something off. Undoing gets the same arrow the
  // folded rows use, so one symbol never means both.
  const seen = document.createElement("button");
  seen.className = "act icon";
  const paintSeen = () => {
    seen.textContent = v.watched ? "↺" : "✓";
    seen.title = v.watched ? "Put back in the queue — marks it not watched"
                           : "Mark as watched";
    el.classList.toggle("watched", !!v.watched);
    el.querySelector(".flag.seen").hidden = !v.watched;
  };
  paintSeen();
  seen.onclick = async () => {
    const r = await post(`/api/watched/${v.id}`);
    v.watched = r.watched;
    bumpSeen(r.watched ? 1 : -1);
    paintSeen();
    // The Unwatched filter is showing a list this video may have just left.
    if (state.unwatched) { refresh(); return; }
    // Otherwise it sinks out of the grid and into the fold at the bottom.
    if (!state.ordered) moveOut(el, "sinking");
  };
  row.appendChild(seen);

  const plus = document.createElement("button");
  plus.className = "act icon"; plus.title = "Add to a collection";
  plus.textContent = "＋";
  plus.onclick = () => openModal(v);
  row.appendChild(plus);

  if (v.have) {
    const del = document.createElement("button");
    del.className = "act icon"; del.title = "Delete file (keeps catalog entry)";
    del.textContent = "✕";
    del.onclick = async () => {
      if (!confirm(`Delete the downloaded file for:\n\n${v.title}\n\n` +
                   `The catalog entry stays, so you can re-download later.`)) return;
      await post(`/api/remove/${v.id}`); refresh();
    };
    row.appendChild(del);
  }
  // Looking costs nothing now: a click on something not on disk streams it.
  const openThumb = () => v.unavailable && !v.have ? null : open_(v);
  el.querySelector(".thumbwrap").onclick = openThumb;
  el.querySelector(".title").onclick = openThumb;
  return el;
}

async function grab(v, btn, audio, height) {
  const label = btn.textContent;
  btn.disabled = true; btn.textContent = "Queued…";
  dismissed.delete(v.id);
  const body = {audio: !!audio};
  if (height != null) body.height = height;
  try { await post(`/api/get/${v.id}`, body); pollJobs(); }
  catch (e) { btn.disabled = false; btn.textContent = label; alert(e.message); }
}

// Each height is a ceiling: a video without 1440p comes down at the next
// size below. Above 1080p the file is VP9 or AV1 -- sharper text in screen
// recordings, heavier to play on an old machine.
const DL_QUALITIES = [["Best available", 0], ["4K (2160p)", 2160], ["1440p", 1440],
                      ["1080p", 1080], ["720p", 720], ["480p", 480]];
function qualityMenu(v, anchor, mainBtn) {
  closeQualityMenu();
  const m = document.createElement("div");
  m.id = "qmenu";
  const head = document.createElement("div");
  head.className = "qh";
  head.textContent = v.have ? "Download again at… (replaces the file)" : "Download at…";
  m.appendChild(head);
  for (const [label, h] of DL_QUALITIES) {
    const b = document.createElement("button");
    b.textContent = label;
    b.onclick = () => { closeQualityMenu(); grab(v, mainBtn, false, h); };
    m.appendChild(b);
  }
  if (!v.have) {
    const b = document.createElement("button");
    b.textContent = "♪ Audio only (m4a)";
    b.title = "A fraction of the size";
    b.onclick = () => { closeQualityMenu(); grab(v, mainBtn, true); };
    m.appendChild(b);
  }
  document.body.appendChild(m);
  const r = anchor.getBoundingClientRect();
  m.style.left = `${Math.min(r.left, innerWidth - m.offsetWidth - 8)}px`;
  m.style.top = r.bottom + m.offsetHeight + 8 > innerHeight
    ? `${r.top - m.offsetHeight - 4}px` : `${r.bottom + 4}px`;
}
function closeQualityMenu() { $("#qmenu")?.remove(); }
document.addEventListener("click", e => { if (!e.target.closest("#qmenu")) closeQualityMenu(); });
addEventListener("scroll", closeQualityMenu, {passive: true});

/* ---- player ---- */
let current = null, saveTimer = null;
// Share of a video past which it counts as finished.
const FINISHED = 0.92;
function open_(v) {
  // Resuming a finished video lands on its last frame, which fires "ended"
  // and shuts the player straight away, so start those over instead.
  const at = v.duration && v.progress / v.duration >= FINISHED ? 0 : v.progress || 0;
  current = v;
  const vid = $("#pvideo");
  vid.querySelectorAll("track").forEach(t => t.remove());
  stopStream();
  $("#ptitle").textContent = v.title;
  $("#psub").textContent = [v.channel, fmtDate(v), fmtDur(v.duration)]
                             .filter(Boolean).join(" · ");
  $("#pdesc").textContent = v.description || "";
  showChapters([], v.id);
  showMarks([], v.id);
  api(`/api/marks/${v.id}`).then(d => showMarks(d.marks, v.id)).catch(() => {});
  togglMount(v);
  $("#player").classList.add("on");
  if (v.have) {
    vid.src = `/media/${v.id}`;
    vid.currentTime = at;
    vid.play().catch(()=>{});
    attachSubs(v.id, vid);
    api(`/api/chapters/${v.id}`).then(d => showChapters(d.chapters, v.id))
                                .catch(() => {});
  } else {
    startStream({...v, progress: at}, vid).catch(e => {
      if (current?.id === v.id) streamStatus(`Couldn't stream: ${e.message}`);
    });
  }
  clearInterval(saveTimer);
  saveTimer = setInterval(() => {
    if (!current || vid.paused) return;
    post(`/api/progress/${current.id}`, {value: vid.currentTime}).catch(()=>{});
    markIfFinished(vid);
  }, 5000);
}
// Tracking is per channel, not per video: one entry that says which creator
// you spent the time on. The start itself is made by the server -- this only
// ever calls localhost, which is what keeps the page sealed.
let tgRunning = null, tgReady = false;

async function togglPoll() {
  try {
    const d = await api("/api/toggl/status");
    tgReady = d.configured;
    tgRunning = d.running && d.running.id ? d.running : null;
  } catch (e) { tgReady = false; }
  paintToggl_();
}

function togglMount(v) {
  togglUnmount();
  if (!tgReady) return;
  const m = state.toggl[(v.channel || "").trim()] || {};
  const el = document.createElement("div");
  el.id = "ptoggl";
  el.innerHTML = '<button id="tgbtn"></button><span id="tgwhat"></span>';
  el.dataset.videoId = v.id;
  // What this click would file, spelled out before you click it.
  el.dataset.label = m.name || v.channel || "";
  el.dataset.project = m.project || "";
  el.dataset.tags = m.tags || "";
  $("#pmeta").insertBefore(el, $("#pdesc"));
  $("#tgbtn").onclick = togglClick;
  paintToggl_();
  togglPoll();
}

// The timer can be stopped or started in Toggl itself, so the button asks
// again whenever you come back to this tab, and every few minutes while a
// player is open. Toggl's free plan allows about 30 requests an hour.
const TG_EVERY = 3 * 60 * 1000;
setInterval(() => { if ($("#ptoggl") && !document.hidden) togglPoll(); }, TG_EVERY);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && $("#ptoggl")) togglPoll();
});

function togglUnmount() {
  const el = $("#ptoggl");
  if (el) el.remove();
}

function paintToggl_() {
  const el = $("#ptoggl");
  if (!el) return;
  el.hidden = !tgReady;
  const btn = $("#tgbtn");
  btn.textContent = tgRunning ? "■ Stop Toggl" : "▶ Start Toggl";
  btn.classList.toggle("on", !!tgRunning);
  $("#tgwhat").textContent = tgRunning
    ? `tracking ${tgRunning.description || "—"}`
    : [el.dataset.label, el.dataset.project, el.dataset.tags]
        .filter(Boolean).join(" · ");
}

async function togglClick() {
  const el = $("#ptoggl"), btn = $("#tgbtn");
  btn.disabled = true;
  try {
    const r = tgRunning
      ? await post("/api/toggl/stop", {id: tgRunning.id,
                                       workspace: tgRunning.workspace_id})
      : await post("/api/toggl/start", {video: el.dataset.videoId});
    tgRunning = r.running && r.running.id ? r.running : null;
    if (r.project_missing)
      alert(`Started, but Toggl has no project called "${r.project_missing}" — ` +
            `the entry has no project. Create it in Toggl, or fix the name in ` +
            `the toggl sheet.`);
  } catch (e) { alert(e.message); }
  btn.disabled = false;
  paintToggl_();
}

/* ---- streaming: watch without downloading ----
   YouTube sends picture and sound as two separate files. Each opens with a
   small index (the `sidx` box) that says where every few seconds of it start,
   like a book's table of contents. The page reads that, then asks this server
   for only the pieces around where you are watching and hands them to the
   <video> through MediaSource. Every byte still goes through this server. */
const AHEAD = 60, BEHIND = 30;
let stream = null;

function streamStatus(msg) {
  $("#pstatus").hidden = !msg;
  $("#pstatus").textContent = msg || "";
}

async function rangeBytes(url, lo, hi) {
  const r = await fetch(url, {headers: {Range: `bytes=${lo}-${hi}`}});
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  return new Uint8Array(await r.arrayBuffer());
}

// A YouTube DASH file is ftyp, moov, sidx, then the media itself. The first
// two are the "init segment" the decoder needs before any piece of media.
async function readIndex(url) {
  let head = new Uint8Array(0), off = 0;
  const need = async n => { if (head.length < n) head = await rangeBytes(url, 0, n + 8191); };
  for (;;) {
    await need(off + 8);
    const dv = new DataView(head.buffer);
    const size = dv.getUint32(off);
    const type = String.fromCharCode(...head.subarray(off + 4, off + 8));
    if (!size) throw new Error("stream has no index");
    if (type !== "sidx") { off += size; continue; }
    await need(off + size);
    const d = new DataView(head.buffer);
    const ver = head[off + 8];
    let p = off + 16;                       // skip version/flags and reference id
    const scale = d.getUint32(p); p += 4;
    let t, first;
    if (ver === 0) { t = d.getUint32(p); first = d.getUint32(p + 4); p += 8; }
    else { t = Number(d.getBigUint64(p)); first = Number(d.getBigUint64(p + 8)); p += 16; }
    const count = d.getUint16(p + 2); p += 4;
    let byte = off + size + first;
    const segs = [];
    for (let i = 0; i < count; i++, p += 12) {
      const len = d.getUint32(p) & 0x7fffffff, dur = d.getUint32(p + 4);
      segs.push({lo: byte, hi: byte + len - 1, start: t / scale, end: (t + dur) / scale});
      byte += len; t += dur;
    }
    return {init: head.slice(0, off), segs};
  }
}

// SourceBuffer work is asynchronous; this turns one call into a promise.
const sbDo = (sb, fn) => new Promise((ok, bad) => {
  sb.addEventListener("updateend", ok, {once: true});
  sb.addEventListener("error", bad, {once: true});
  try { fn(); } catch (e) { bad(e); }
});
const buffered = (sb, s) => {
  const mid = (s.start + s.end) / 2, b = sb.buffered;
  for (let i = 0; i < b.length; i++) if (b.start(i) <= mid && mid < b.end(i)) return true;
  return false;
};

// The quality you last picked, as a ceiling: a video without that height
// plays at the tallest one below it. Nothing picked means config's max_height.
let quality = null;
try { quality = parseInt(localStorage.getItem("yt.quality")) || null; } catch (e) {}

function paintQuality(v, heights, h) {
  const box = $("#pquality");
  box.replaceChildren(...heights.map(x => {
    const b = document.createElement("button");
    b.textContent = x + "p";
    b.classList.toggle("on", x === h);
    b.onclick = () => {
      quality = x;
      try { localStorage.setItem("yt.quality", x); } catch (e) {}
      if (x !== h) switchQuality(v);
    };
    return b;
  }));
  box.hidden = false;
}

// Start over at the same moment, keeping play/pause as it was.
function switchQuality(v) {
  const vid = $("#pvideo"), paused = vid.paused;
  stopStream();
  startStream({...v, progress: vid.currentTime}, vid, paused).catch(e => {
    if (current?.id === v.id) streamStatus(`Couldn't stream: ${e.message}`);
  });
}

async function startStream(v, vid, paused = false) {
  const me = stream = {alive: true, tracks: []};
  streamStatus("Finding the stream…");
  const meta = await api(`/api/stream/${v.id}`);
  // Above 1080p the picture is AV1, which some browsers cannot decode;
  // those heights are simply not offered.
  const heights = Object.keys(meta.videos).map(Number).sort((a, b) => a - b)
                        .filter(x => MediaSource.isTypeSupported(meta.videos[x]));
  if (!heights.length) throw new Error("this browser cannot play any of its video");
  if (!MediaSource.isTypeSupported(meta.audio))
    throw new Error(`this browser cannot play ${meta.audio}`);
  const fit = heights.filter(x => x <= (quality || meta.default));
  const h = fit.length ? fit[fit.length - 1] : heights[0];
  meta.video = meta.videos[h];
  if (!me.alive) return;
  paintQuality(v, heights, h);
  showChapters(meta.chapters, v.id);
  const ms = me.ms = new MediaSource();
  me.objectUrl = URL.createObjectURL(ms);
  vid.src = me.objectUrl;
  await new Promise(r => ms.addEventListener("sourceopen", r, {once: true}));
  const idx = await Promise.all(["video", "audio"].map(async kind => {
    const url = kind === "video" ? `/stream/${v.id}/video/${h}` : `/stream/${v.id}/audio`;
    return {url, kind, ...(await readIndex(url))};
  }));
  if (!me.alive) return;
  // Both buffers must exist before either gets data: once the first one
  // has its init segment, Chrome will not accept a second.
  me.tracks = idx.map(i => ({url: i.url, sb: ms.addSourceBuffer(meta[i.kind]),
                             segs: i.segs, init: i.init, busy: false}));
  await Promise.all(me.tracks.map(t => sbDo(t.sb, () => t.sb.appendBuffer(t.init))));
  if (!me.alive) return;
  if (meta.duration) ms.duration = meta.duration;
  streamStatus("Streaming — nothing is saved to disk.");

  const pump = async t => {
    if (t.busy || !me.alive) return;
    t.busy = true;
    try {
      while (me.alive) {
        const now = vid.currentTime;
        // Let go of what is well behind, so an hour-long video does not
        // pile up in memory.
        const b = t.sb.buffered;
        if (b.length && b.start(0) < now - BEHIND - 10)
          await sbDo(t.sb, () => t.sb.remove(0, now - BEHIND));
        const seg = t.segs.find(s => s.end > now && s.start < now + AHEAD
                                     && !buffered(t.sb, s));
        if (!seg) break;
        const bytes = await rangeBytes(t.url, seg.lo, seg.hi);
        if (!me.alive) return;
        try { await sbDo(t.sb, () => t.sb.appendBuffer(bytes)); }
        catch (e) {
          // Full: drop everything but the stretch around the playhead, retry.
          if (e.name !== "QuotaExceededError") throw e;
          await sbDo(t.sb, () => t.sb.remove(0, Math.max(0, now - 5)));
          await sbDo(t.sb, () => t.sb.remove(now + AHEAD, Infinity));
          await sbDo(t.sb, () => t.sb.appendBuffer(bytes));
        }
      }
      // Tell the player there is no more once both tracks hold their last piece.
      const done = me.tracks.every(x => buffered(x.sb, x.segs[x.segs.length - 1]));
      if (done && ms.readyState === "open" && me.tracks.every(x => !x.sb.updating))
        ms.endOfStream();
    } catch (e) {
      if (me.alive) streamStatus(`Stream stalled: ${e.message}`);
    } finally { t.busy = false; }
  };
  me.kick = () => me.tracks.forEach(pump);
  vid.addEventListener("timeupdate", me.kick);
  vid.addEventListener("seeking", me.kick);
  vid.currentTime = v.progress || 0;
  me.kick();
  if (!paused) vid.play().catch(() => {});
}

function stopStream() {
  streamStatus("");
  $("#pquality").hidden = true;
  if (!stream) return;
  const vid = $("#pvideo");
  stream.alive = false;
  if (stream.kick) {
    vid.removeEventListener("timeupdate", stream.kick);
    vid.removeEventListener("seeking", stream.kick);
  }
  if (stream.objectUrl) URL.revokeObjectURL(stream.objectUrl);
  stream = null;
}

/* ---- speed ---- */
// A new src resets playbackRate to defaultPlaybackRate, so keeping both in
// step is what makes the chosen speed survive from one video to the next.
const SPEEDS = [1, 1.25, 1.5, 1.75, 2];
let speed = 1;
try { speed = parseFloat(localStorage.getItem("yt.speed")) || 1; } catch (e) {}
function paintSpeed() {
  for (const b of $("#pspeed").children)
    b.classList.toggle("on", parseFloat(b.dataset.r) === speed);
}
function setSpeed(r) {
  speed = Math.min(4, Math.max(0.25, Math.round(r * 100) / 100));
  const vid = $("#pvideo");
  vid.defaultPlaybackRate = speed;
  if (vid.playbackRate !== speed) vid.playbackRate = speed;
  try { localStorage.setItem("yt.speed", speed); } catch (e) {}
  paintSpeed();
}
for (const r of SPEEDS) {
  const b = document.createElement("button");
  b.dataset.r = r; b.textContent = r + "×";
  b.onclick = () => setSpeed(r);
  $("#pspeed").append(b);
}
// Changes from the browser's own ⋮ menu count too.
$("#pvideo").addEventListener("ratechange", e => {
  if (e.target.playbackRate !== speed) setSpeed(e.target.playbackRate);
});
$("#pvideo").addEventListener("loadedmetadata", () => setSpeed(speed));
document.addEventListener("keydown", e => {
  if (!$("#player").classList.contains("on") || e.target.matches?.("input, textarea")) return;
  if (e.key === ">") setSpeed(speed + 0.25);
  else if (e.key === "<") setSpeed(speed - 0.25);
});
setSpeed(speed);

/* ---- marks: "I got this far", as many as you like per video ---- */
let marks = [];
const markJump = t => { const vid = $("#pvideo"); vid.currentTime = t; vid.play().catch(()=>{}); };
function showMarks(list, id, focusId) {
  if (current?.id !== id) return;
  marks = list || [];
  const ol = $("#pmarks");
  ol.replaceChildren();
  for (const m of marks) {
    const li = document.createElement("li");
    const ts = document.createElement("button");
    ts.className = "ts"; ts.textContent = fmtDur(m.t) || "0:00";
    ts.onclick = () => markJump(m.t);
    const note = document.createElement("input");
    note.className = "note"; note.value = m.note; note.placeholder = "add a note…";
    const save = () => { if (note.value.trim() !== m.note)
      markPost({id: m.id, note: note.value}); };
    note.onkeydown = e => { if (e.key === "Enter") note.blur();
                            if (e.key === "Escape") { e.stopPropagation(); note.value = m.note; note.blur(); } };
    note.onblur = save;
    const x = document.createElement("button");
    x.className = "x"; x.textContent = "×"; x.title = "Remove this mark";
    x.onclick = () => markPost({drop: m.id});
    li.append(ts, note, x);
    ol.appendChild(li);
    if (m.id === focusId) setTimeout(() => note.focus(), 0);
  }
  paintMarkStrip();
}
function paintMarkStrip() {
  const strip = $("#pmstrip"), d = $("#pvideo").duration || current?.duration;
  strip.replaceChildren();
  if (!d || !isFinite(d)) return;
  for (const m of marks) {
    const b = document.createElement("button");
    b.style.left = `${Math.min(100, 100 * m.t / d)}%`;
    b.title = `${fmtDur(m.t) || "0:00"}${m.note ? " · " + m.note : ""}`;
    b.onclick = () => markJump(m.t);
    strip.appendChild(b);
  }
}
async function markPost(body) {
  if (!current) return;
  const id = current.id;
  try {
    const r = await post(`/api/marks/${id}`, body);
    const before = new Set(marks.map(m => m.id));
    // A new mark gets its note box focused, ready to say what this spot is.
    const fresh = r.marks.find(m => !before.has(m.id));
    showMarks(r.marks, id, fresh?.id);
  } catch (e) { alert(e.message); }
}
function addMark() {
  if (!current) return;
  markPost({t: Math.floor($("#pvideo").currentTime)});
}
$("#pmarkadd").onclick = addMark;
$("#pvideo").addEventListener("durationchange", paintMarkStrip);
document.addEventListener("keydown", e => {
  if (!$("#player").classList.contains("on") || e.target.matches?.("input, textarea")) return;
  if (e.key === "m" || e.key === "M") addMark();
});

/* ---- chapters ---- */
let chapters = [];
function showChapters(list, id) {
  if (current?.id !== id) return;           // player moved on while we waited
  chapters = list || [];
  const strip = $("#pchap"), ol = $("#pchlist");
  strip.replaceChildren(); ol.replaceChildren();
  strip.hidden = ol.hidden = !chapters.length;
  const jump = t => { const vid = $("#pvideo"); vid.currentTime = t; vid.play().catch(()=>{}); };
  chapters.forEach(c => {
    const ts = fmtDur(c.start) || "0:00";
    const seg = document.createElement("button");
    seg.style.flexGrow = Math.max(c.end - c.start, 1);
    seg.title = `${ts} · ${c.title}`;
    seg.onclick = () => jump(c.start);
    strip.appendChild(seg);
    const li = document.createElement("li"), b = document.createElement("button");
    b.innerHTML = `<span class="ts"></span><span></span>`;
    b.children[0].textContent = ts;
    b.children[1].textContent = c.title;
    b.onclick = () => jump(c.start);
    li.appendChild(b);
    ol.appendChild(li);
  });
  paintChapter();
}
function paintChapter() {
  if (!chapters.length) return;
  const t = $("#pvideo").currentTime, segs = $("#pchap").children,
        items = $("#pchlist").children;
  chapters.forEach((c, i) => {
    const p = Math.min(100, Math.max(0, 100 * (t - c.start) / (c.end - c.start)));
    segs[i].style.setProperty("--p", p + "%");
    const on = c.start <= t && t < c.end;
    if (items[i].classList.contains("on") !== on) {
      items[i].classList.toggle("on", on);
      if (on) items[i].scrollIntoView({block: "nearest"});
    }
  });
}
$("#pvideo").addEventListener("timeupdate", paintChapter);
$("#pvideo").addEventListener("seeked", paintChapter);

async function attachSubs(id, vid) {
  let langs = [];
  try { langs = (await api(`/api/subs/${id}`)).langs || []; } catch (e) { return; }
  if (current?.id !== id) return;           // player moved on while we waited
  // Attached but off: no `default` track, so the subtitles sit in the player's
  // CC menu until you pick one rather than covering the picture uninvited.
  langs.forEach(lang => {
    const t = document.createElement("track");
    t.kind = "subtitles"; t.label = lang; t.srclang = lang.split("-")[0];
    t.src = `/subs/${id}/${encodeURIComponent(lang)}`;
    vid.appendChild(t);
  });
  for (const track of vid.textTracks) track.mode = "disabled";
}

// Credits, an outro, a tab closed on the last thirty seconds: near enough the
// end counts as watched, since "ended" only fires on the very last frame.
function markIfFinished(vid) {
  if (!current || current.watched || !vid.duration) return;
  if (vid.currentTime / vid.duration < FINISHED) return;
  current.watched = true;
  post(`/api/watched/${current.id}`, {value: 1}).catch(()=>{});
}

function close_() {
  const vid = $("#pvideo");
  if (current) post(`/api/progress/${current.id}`, {value: vid.currentTime}).catch(()=>{});
  markIfFinished(vid);
  clearInterval(saveTimer);
  stopStream();
  vid.pause(); vid.removeAttribute("src"); vid.load();
  $("#player").classList.remove("on");
  togglUnmount();
  showChapters([], current?.id);
  current = null; refresh();
}
$("#pclose").onclick = close_;
$("#pvideo").addEventListener("ended", async () => {
  if (current && !current.watched) {
    current.watched = true;
    await post(`/api/watched/${current.id}`, {value: 1});
  }
  close_();
});
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  if ($("#tgmodal").classList.contains("on")) closeToggl();
  else if ($("#srcmodal").classList.contains("on")) closeSrc();
  else if ($("#modal").classList.contains("on")) closeModal();
  else if ($("#player").classList.contains("on")) close_();
  else dismissAllJobs();
});

/* ---- toggl sheet ---- */
let tgTimer = null;
function openToggl() {
  paintToggl();
  // Say so up front rather than letting them fill in seven rows and then
  // wonder why no button ever turns up.
  $("#tgoff").hidden = tgReady;
  $("#tgmodal").classList.add("on");
}
function closeToggl() {
  $("#tgmodal").classList.remove("on");
  refresh(); togglPoll();
}

function paintToggl() {
  const box = $("#tgrows");
  box.innerHTML = "";
  if (!state.togglChannels.length) {
    box.innerHTML = '<div class="sub">No channels yet — track a source first.</div>';
    return;
  }
  for (const c of state.togglChannels) box.appendChild(togglRow(c));
}

function togglRow(c) {
  const el = document.createElement("div");
  el.className = "tgrow";
  const label = document.createElement("div");
  label.className = "ch";
  label.textContent = c.channel;
  label.title = c.channel;
  el.appendChild(label);

  const fields = {};
  for (const [key, ph] of [["name", "Name in Toggl"], ["project", "Project"],
                           ["tags", "Tags, comma separated"]]) {
    const inp = document.createElement("input");
    inp.value = c[key] || "";
    inp.placeholder = key === "name" ? c.channel : ph;
    inp.title = ph;
    inp.autocomplete = "off";
    inp.spellcheck = false;
    // Saved as you type rather than behind a Save button: there is one row per
    // channel and nothing here is destructive, so a trip to a button would be
    // the only hard part of the job.
    inp.oninput = () => {
      clearTimeout(tgTimer);
      tgTimer = setTimeout(() => saveToggl(c, fields), 500);
    };
    fields[key] = inp;
    el.appendChild(inp);
  }
  return el;
}

async function saveToggl(c, fields) {
  const patch = {channel: c.channel, name: fields.name.value,
                 project: fields.project.value, tags: fields.tags.value};
  try {
    const r = await post("/api/toggl", patch);
    Object.assign(c, {name: patch.name, project: patch.project, tags: patch.tags});
    state.togglChannels = r.channels;
    state.toggl = Object.fromEntries(r.channels
      .filter(x => x.name || x.project || x.tags)
      .map(x => [x.channel, {name: x.name, project: x.project, tags: x.tags}]));
    note("saved");
  } catch (e) { note(e.message); }
}
function note(text) {
  $("#tgnote").textContent = text;
  setTimeout(() => { if ($("#tgnote").textContent === text) $("#tgnote").textContent = ""; },
             1600);
}
$("#togglcfg").onclick = openToggl;
$("#tgdone").onclick = closeToggl;
$("#tgmodal").onclick = e => { if (e.target.id === "tgmodal") closeToggl(); };

/* ---- collection modal ---- */
let modalVideo = null;
async function openModal(v) {
  modalVideo = v;
  $("#mwho").textContent = v.title;
  $("#mnew").value = "";
  await paintModal();
  $("#modal").classList.add("on");
  $("#mnew").focus();
}
async function paintModal() {
  const mine = new Set((await api(`/api/collections/${modalVideo.id}`))
                        .collections.map(c => c.id));
  const list = $("#mlist");
  list.innerHTML = state.collections.length ? "" :
    '<div class="sub">No collections yet — make one below.</div>';
  for (const c of state.collections) {
    const lab = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = mine.has(c.id);
    cb.onchange = async () => {
      await post(`/api/collect/${modalVideo.id}`,
                 {collection: c.id, remove: !cb.checked});
      refresh();
    };
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(`${c.name} (${c.total})`));
    list.appendChild(lab);
  }
}
$("#madd").onclick = async () => {
  const name = $("#mnew").value.trim();
  if (!name) return;
  const c = await post("/api/collections", {name});
  $("#mnew").value = "";
  if (modalVideo) await post(`/api/collect/${modalVideo.id}`, {collection: c.id});
  const d = await api("/api/state?" + params());
  state.collections = d.collections;
  pickerKey = "";                       // force the picker to pick up the new one
  await paintModal();
  refresh();
};
$("#mnew").addEventListener("keydown", e => { if (e.key === "Enter") $("#madd").click(); });
$("#modal").onclick = e => { if (e.target.id === "modal") closeModal(); };
function closeModal() { $("#modal").classList.remove("on"); modalVideo = null; }
$("#newcoll").onclick = async () => {
  modalVideo = null;
  $("#mwho").textContent = "Create a new collection";
  $("#mlist").innerHTML = "";
  $("#mnew").value = "";
  $("#modal").classList.add("on");
  $("#mnew").focus();
};

/* ---- track a channel or playlist ---- */
// The job this page is waiting on, so a source that finishes cataloguing can
// drop you straight into it -- the terminal's "next: yt list <name>", without
// the typing. Only ever one: a batch of playlists has no single view to land in.
let pendingSource = null;
function closeSrc() { $("#srcmodal").classList.remove("on"); askMode(); }
function srcError(msg) {
  // A rejected handle is worth reading next to the box that produced it, not
  // in an alert that throws away what you typed.
  const box = $("#serr");
  box.textContent = msg;
  box.hidden = false;
}
// Two modes in one sheet: ask for something to track, or pick from what a
// creator has. Browsing replaces the box rather than opening a second window.
function askMode() {
  $("#sask").hidden = false;
  $("#spick").hidden = true;
  $("#serr").hidden = true;
  $("#stitle").textContent = "Track a channel or playlist";
  $("#shint").hidden = false;
}
function pickMode(creator, playlists) {
  $("#sask").hidden = true;
  $("#spick").hidden = false;
  $("#serr").hidden = true;
  $("#shint").hidden = true;
  $("#stitle").textContent = creator;
  const n = playlists.filter(p => !p.tracked).length;
  $("#spickwho").textContent =
    `${playlists.length} to pick from · ${n} not tracked yet`;
  const list = $("#spicks");
  list.innerHTML = "";
  // Courses, live, playlists: the server sends them in that order, so a
  // heading goes in wherever the section changes.
  const heads = {course:"Courses", live:"Live", playlist:"Playlists"};
  let section = null;
  for (const pl of playlists) {
    if (pl.section !== section) {
      section = pl.section;
      const h = document.createElement("div");
      h.className = "sec";
      const count = playlists.filter(p => p.section === section).length;
      h.textContent = `${GLYPHS[section]} ${heads[section]} · ${count}`;
      list.appendChild(h);
    }
    const lab = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = pl.id;
    cb.dataset.section = pl.section;
    // One you already track is shown, but not on offer: re-adding it would
    // just be a sync, and the point of this list is what you are missing.
    cb.disabled = pl.tracked;
    cb.onchange = paintPickCount;
    const title = document.createElement("span");
    title.textContent = pl.title;
    if (pl.tracked) title.style.opacity = ".55";
    lab.appendChild(cb);
    lab.appendChild(title);
    if (pl.tracked) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = "tracked";
      lab.appendChild(tag);
    }
    list.appendChild(lab);
  }
  paintPickCount();
}
const picked = () => [...$("#spicks").querySelectorAll("input:checked")]
                       .map(cb => ({ref: cb.value, section: cb.dataset.section}));
function paintPickCount() {
  const n = picked().length;
  const btn = $("#spickadd");
  btn.textContent = n ? `Track ${n} selected` : "Track selected";
  btn.disabled = !n;
}
function setAll(on) {
  for (const cb of $("#spicks").querySelectorAll("input:not(:disabled)"))
    cb.checked = on;
  paintPickCount();
}

$("#newsrc").onclick = () => {
  $("#snew").value = "";
  askMode();
  $("#srcmodal").classList.add("on");
  $("#snew").focus();
};
$("#srcmodal").onclick = e => { if (e.target.id === "srcmodal") closeSrc(); };

async function addSource() {
  const ref = $("#snew").value.trim();
  if (!ref) return;
  const btn = $("#sadd");
  btn.disabled = true;
  try {
    const r = await post("/api/sources", {ref});
    pendingSource = r.job.id;
    closeSrc();
    pollJobs();               // the card takes it from here
  } catch (e) {
    srcError(e.message);
    $("#snew").focus();
  } finally {
    btn.disabled = false;
  }
}
async function browseSource() {
  const creator = $("#snew").value.trim();
  if (!creator) { srcError("paste a channel handle (@name) or a channel URL"); return; }
  const btn = $("#sbrowse"), label = btn.textContent;
  // Listing a creator's tabs is a few seconds of yt-dlp, so say that plainly
  // rather than leaving a dead button.
  btn.disabled = true;
  btn.textContent = "listing…";
  $("#serr").hidden = true;
  try {
    const r = await post("/api/sources/browse", {creator});
    pickMode(r.creator, r.playlists);
  } catch (e) {
    srcError(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}
async function addPicked() {
  const refs = picked();
  if (!refs.length) return;
  const btn = $("#spickadd");
  btn.disabled = true;
  try {
    const r = await post("/api/sources", {refs});
    // One pick has a view to land in; a batch does not, so the cards report it.
    pendingSource = refs.length === 1 ? r.job.id : null;
    closeSrc();
    pollJobs();
  } catch (e) {
    srcError(e.message);
  } finally {
    paintPickCount();
  }
}
$("#sadd").onclick = addSource;
$("#sbrowse").onclick = browseSource;
$("#sall").onclick = () => setAll(true);
$("#snone").onclick = () => setAll(false);
$("#sback").onclick = askMode;
$("#spickadd").onclick = addPicked;
$("#snew").addEventListener("keydown", e => { if (e.key === "Enter") addSource(); });

/* ---- jobs ---- */
let jobTimer = null, lastJobs = [];
// Cards the user closed. A finished job is dropped server-side too; a running
// one only loses its card, since the download itself keeps going.
const dismissed = new Set();
// Pending auto-dismiss timers for jobs that finished cleanly, keyed by id.
const fading = new Map();
const AUTO_DISMISS_MS = 4000;

function dismissJob(j) {
  dismissed.add(j.id);
  clearTimeout(fading.get(j.id));
  fading.delete(j.id);
  if (j.state !== "queued" && j.state !== "running")
    post("/api/jobs/clear", {id: j.id}).catch(() => {});
  renderJobs(lastJobs);
}
function renderJobs(jobs) {
  lastJobs = jobs;
  // Forget ids the server no longer reports, so a re-download shows up again.
  const live = new Set(jobs.map(j => j.id));
  for (const id of [...dismissed]) if (!live.has(id)) dismissed.delete(id);
  for (const [id, t] of [...fading])
    if (!live.has(id)) { clearTimeout(t); fading.delete(id); }
  // A clean download announces itself and then gets out of the way on its own.
  // Failures stay put: they carry a message worth reading.
  for (const j of jobs)
    if (j.state === "done" && !dismissed.has(j.id) && !fading.has(j.id))
      fading.set(j.id, setTimeout(() => dismissJob(j), AUTO_DISMISS_MS));
  // A job dismissed while running is reaped once it settles.
  for (const j of jobs)
    if (dismissed.has(j.id) && j.state !== "queued" && j.state !== "running")
      post("/api/jobs/clear", {id: j.id}).catch(() => {});

  // A source that has just finished cataloguing is the view you asked for.
  const waited = pendingSource && jobs.find(j => j.id === pendingSource);
  if (waited && waited.state === "done" && waited.result) {
    pendingSource = null;
    state.source = waited.result.source_id;
    state.collection = "";
    refresh({push: true});
  } else if (waited && waited.state === "error") {
    pendingSource = null;
  }

  const box = $("#jobs");
  box.innerHTML = "";
  const shown = jobs.filter(j => !dismissed.has(j.id));
  if (shown.length > 1) {
    const all = document.createElement("button");
    all.className = "clearall";
    all.textContent = `Dismiss all (${shown.length})`;
    all.title = "Close every card (downloads in progress keep running)";
    all.onclick = () => shown.forEach(dismissJob);
    box.appendChild(all);
  }
  for (const j of shown) {
    const el = document.createElement("div");
    el.className = "job" + (j.state === "error" ? " error" : "");
    const pct = Math.round(100 * (j.fraction || 0));
    el.innerHTML = `<button class="x" title="Dismiss">✕</button>
      <div class="t"></div><div class="d"></div>
      <div class="track"><i style="width:${pct}%"></i></div>`;
    el.querySelector(".t").textContent =
      j.kind === "source" ? `＋ ${j.title}` : j.title;
    el.querySelector(".d").textContent =
      j.state === "error" ? j.error : (j.state === "done" ? "done" : j.detail);
    el.querySelector(".x").onclick = e => { e.stopPropagation(); dismissJob(j); };
    box.appendChild(el);
  }
  const busy = jobs.some(j => j.state === "queued" || j.state === "running");
  clearInterval(jobTimer);
  if (busy) jobTimer = setInterval(pollJobs, 1200);
}
function dismissAllJobs() {
  lastJobs.filter(j => !dismissed.has(j.id)).forEach(dismissJob);
}
async function pollJobs() {
  const d = await api("/api/jobs");
  const wasBusy = d.jobs.some(j => j.state === "queued" || j.state === "running");
  renderJobs(d.jobs);
  if (!wasBusy) refresh();
}

/* ---- filters ---- */
let debounce = null;
$("#q").addEventListener("input", e => {
  state.q = e.target.value.trim();
  clearTimeout(debounce); debounce = setTimeout(refresh, 220);
});
$("#sort").addEventListener("change", async e => {
  // Persisted against the view you were looking at when you chose it.
  await post("/api/sort", {sort: e.target.value, source: state.source || null,
                           collection: state.collection || null});
  refresh();
});
function toggle(id, key) {
  const b = $(id);
  b.onclick = () => {
    const on = b.getAttribute("aria-pressed") === "true";
    b.setAttribute("aria-pressed", String(!on));
    if (key === "have") state.have = on ? null : true; else state[key] = !on;
    refresh();
  };
}
toggle("#f-have", "have"); toggle("#f-starred", "starred"); toggle("#f-unwatched", "unwatched");
toggle("#f-hidden", "hidden");

function restoreFromUrl() {
  const p = new URLSearchParams(location.search);
  state.q = p.get("q") || "";
  state.source = p.get("source") || "";
  state.collection = p.get("collection") || "";
  state.have = p.has("have") ? p.get("have") === "1" : null;
  state.starred = p.get("starred") === "1";
  state.unwatched = p.get("unwatched") === "1";
  state.hidden = p.get("hidden") === "1";
  $("#q").value = state.q;
  $("#f-have").setAttribute("aria-pressed", String(state.have === true));
  for (const [id, on] of [["#f-starred", state.starred],
                          ["#f-unwatched", state.unwatched],
                          ["#f-hidden", state.hidden]])
    $(id).setAttribute("aria-pressed", String(on));
}
restoreFromUrl();
togglPoll();
// Back and forward move between views rather than out of the library.
addEventListener("popstate", () => { restoreFromUrl(); refresh(); });

refresh();
</script>
</body>
</html>
"""
