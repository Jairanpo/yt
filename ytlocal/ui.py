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
  .stats { color:var(--dim); font-size:13px; margin-left:auto; }
  main { padding:20px; }
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
  .flag.seen { left:auto; right:6px; bottom:6px; top:auto; background:rgba(0,0,0,.72);
               color:#cfcbc2; }
  .bar { position:absolute; left:0; right:0; bottom:0; height:3px;
         background:rgba(255,255,255,.18); }
  .bar i { display:block; height:100%; background:var(--accent); }
  .meta { padding:10px 12px 12px; display:flex; flex-direction:column; gap:6px;
          flex:1; }
  .title { font-weight:560; font-size:14px; line-height:1.35; cursor:pointer;
           display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
           overflow:hidden; }
  .sub { color:var(--dim); font-size:12.5px; }
  .row { display:flex; gap:6px; margin-top:auto; padding-top:4px; }
  button.act { flex:1; border:1px solid var(--edge); background:transparent;
               color:var(--ink); border-radius:6px; padding:5px 8px; font-size:12.5px;
               cursor:pointer; }
  button.act:hover { border-color:var(--accent); color:var(--accent); }
  button.act.primary { background:var(--accent); border-color:var(--accent);
                       color:#fff; }
  button.act:disabled { opacity:.55; cursor:default; }
  .icon { flex:0 0 auto; width:30px; padding:5px 4px; }
  .empty { color:var(--dim); text-align:center; padding:64px 20px; }
  /* player overlay */
  #player { position:fixed; inset:0; background:rgba(8,8,10,.94); z-index:50;
            display:none; flex-direction:column; padding:24px; }
  #player.on { display:flex; }
  #player video { width:100%; max-width:1100px; max-height:70vh; margin:0 auto;
                  background:#000; border-radius:8px; outline:none; }
  #pmeta { max-width:1100px; margin:14px auto 0; width:100%; color:#e9e7e3; }
  #pmeta h2 { margin:0 0 4px; font-size:17px; font-weight:600; }
  #pmeta .sub { color:#9b988f; }
  #pdesc { max-height:20vh; overflow:auto; white-space:pre-wrap; margin-top:10px;
           font-size:13.5px; color:#c3c0b8; }
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
  #modal { position:fixed; inset:0; background:rgba(8,8,10,.6); z-index:60;
           display:none; align-items:center; justify-content:center; }
  #modal.on { display:flex; }
  #modal .box { background:var(--panel); border:1px solid var(--edge);
                border-radius:10px; padding:18px; width:min(380px,92vw);
                box-shadow:0 8px 30px rgba(0,0,0,.3); }
  #modal h3 { margin:0 0 4px; font-size:15px; }
  #modal .who { color:var(--dim); font-size:12.5px; margin-bottom:12px;
                overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  #modal label { display:flex; gap:9px; align-items:center; padding:6px 2px;
                 font-size:14px; cursor:pointer; }
  #modal .mk { display:flex; gap:6px; margin-top:12px; }
  #modal .mk input { flex:1; background:var(--bg); color:var(--ink);
                     border:1px solid var(--edge); border-radius:6px;
                     padding:6px 9px; font:inherit; font-size:13.5px; }
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
  <select id="src"><option value="">Everything</option></select>
  <select id="sort" title="Sort order (remembered per view)"></select>
  <div class="chips">
    <button class="chip" id="f-have"      aria-pressed="false">Downloaded</button>
    <button class="chip" id="f-starred"   aria-pressed="false">Starred</button>
    <button class="chip" id="f-unwatched" aria-pressed="false">Unwatched</button>
    <button class="chip" id="f-hidden" aria-pressed="false"
            title="Show what is hidden — private or deleted entries, and anything you hid">Hidden</button>
  </div>
  <button class="chip" id="newcoll" title="New collection">＋ collection</button>
  <div class="stats" id="stats"></div>
</header>
<main><div class="grid" id="grid"></div><div class="empty" id="empty" hidden></div></main>

<div id="jobs"></div>

<div id="modal"><div class="box">
  <h3>Add to collection</h3>
  <div class="who" id="mwho"></div>
  <div id="mlist"></div>
  <div class="mk"><input id="mnew" placeholder="New collection…" autocomplete="off">
    <button class="act" id="madd">Create</button></div>
</div></div>

<div id="player">
  <button id="pclose" title="Close (Esc)">&times;</button>
  <video id="pvideo" controls playsinline></video>
  <div id="pmeta"><h2 id="ptitle"></h2><div class="sub" id="psub"></div>
    <div id="pdesc"></div></div>
</div>

<script>
const state = { q:"", source:"", collection:"", have:null, starred:false,
                unwatched:false, hidden:false, videos:[], ordered:false, collections:[],
                sort:"default" };
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
async function refresh() {
  const d = await api("/api/state?" + params());
  state.videos = d.videos;
  state.ordered = d.ordered;
  state.collections = d.collections;
  state.sort = d.sort;
  buildPicker(d.sources, d.collections);
  buildSorts(d.sorts, d.sort);
  const s = d.stats;
  $("#stats").textContent =
    `${s.have}/${s.total} on disk · ${fmtSize(s.bytes)} · ` +
    `${s.channels} channels · ${s.playlists} playlists` +
    (s.hidden ? ` · ${s.hidden} hidden` : "");
  render(d.videos);
  renderJobs(d.jobs);
}

function buildPicker(sources, colls) {
  // Rebuild only when the set actually changes, so the open dropdown and the
  // current selection survive the 1.2s job-polling refreshes.
  const key = JSON.stringify([sources.map(s => [s.id, s.have, s.total]),
                              colls.map(c => [c.id, c.have, c.total])]);
  if (key === pickerKey) return;
  pickerKey = key;
  const sel = $("#src"), keep = sel.value;
  sel.innerHTML = '<option value="">Everything</option>';
  const group = (label, items, prefix) => {
    if (!items.length) return;
    const g = document.createElement("optgroup"); g.label = label;
    for (const it of items) {
      const o = document.createElement("option");
      o.value = prefix + it.id;
      o.textContent = `${it.name} (${it.have}/${it.total})`;
      g.appendChild(o);
    }
    sel.appendChild(g);
  };
  group("Channels",  sources.filter(s => s.kind === "channel"),  "s:");
  group("Playlists", sources.filter(s => s.kind === "playlist"), "s:");
  group("Collections", colls, "c:");
  sel.value = keep;
}

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

function render(vs) {
  const grid = $("#grid"), empty = $("#empty");
  grid.innerHTML = "";
  empty.hidden = vs.length > 0;
  if (!vs.length) {
    empty.textContent = state.hidden
      ? "Nothing is hidden."
      : state.q || state.source || state.collection || state.have !== null
      ? "Nothing matches those filters."
      : "Catalog is empty — run  yt add @channel  in the terminal.";
    return;
  }
  vs.forEach((v, i) => grid.appendChild(card(v, state.ordered ? i + 1 : null)));
}

function card(v, seq) {
  const el = document.createElement("div");
  el.className = "card" + (v.watched ? " watched" : "")
                        + (v.unavailable ? " gone" : "");
  const pct = v.have && v.duration && v.progress
              ? Math.min(100, 100 * v.progress / v.duration) : 0;
  el.innerHTML = `
    <div class="thumbwrap">
      <img loading="lazy" src="/thumb/${v.id}" alt="">
      ${seq ? `<span class="seq">${seq}</span>` : ''}
      ${v.have ? `<span class="flag have" style="${seq ? 'left:auto;right:6px' : ''}">on disk</span>` : ''}
      ${v.starred ? '<span class="flag" style="left:auto;right:6px;top:6px">★</span>' : ''}
      ${v.duration ? `<span class="badge">${fmtDur(v.duration)}</span>` : ''}
      <span class="flag seen" style="${v.duration ? 'bottom:26px' : ''}"
            ${v.watched ? '' : 'hidden'}>watched</span>
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

  const seen = document.createElement("button");
  seen.className = "act icon";
  const paintSeen = () => {
    seen.textContent = v.watched ? "✓" : "○";
    seen.title = v.watched ? "Mark as not watched" : "Mark as watched";
    el.classList.toggle("watched", !!v.watched);
    el.querySelector(".flag.seen").hidden = !v.watched;
  };
  paintSeen();
  seen.onclick = async () => {
    const r = await post(`/api/watched/${v.id}`);
    v.watched = r.watched;
    paintSeen();
    // The Unwatched filter is showing a list this video may have just left.
    if (state.unwatched) refresh();
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
  const openThumb = () => v.have ? open_(v) : grab(v, main);
  el.querySelector(".thumbwrap").onclick = openThumb;
  el.querySelector(".title").onclick = openThumb;
  return el;
}

async function grab(v, btn) {
  btn.disabled = true; btn.textContent = "Queued…";
  dismissed.delete(v.id);
  try { await post(`/api/get/${v.id}`); pollJobs(); }
  catch (e) { btn.disabled = false; btn.textContent = "Retry"; alert(e.message); }
}

/* ---- player ---- */
let current = null, saveTimer = null;
function open_(v) {
  current = v;
  const vid = $("#pvideo");
  vid.querySelectorAll("track").forEach(t => t.remove());
  vid.src = `/media/${v.id}`;
  $("#ptitle").textContent = v.title;
  $("#psub").textContent = [v.channel, fmtDate(v), fmtDur(v.duration)]
                             .filter(Boolean).join(" · ");
  $("#pdesc").textContent = v.description || "";
  $("#player").classList.add("on");
  vid.currentTime = v.progress || 0;
  vid.play().catch(()=>{});
  attachSubs(v.id, vid);
  clearInterval(saveTimer);
  saveTimer = setInterval(() => {
    if (!current || vid.paused) return;
    post(`/api/progress/${current.id}`, {value: vid.currentTime}).catch(()=>{});
    markIfFinished(vid);
  }, 5000);
}
async function attachSubs(id, vid) {
  let langs = [];
  try { langs = (await api(`/api/subs/${id}`)).langs || []; } catch (e) { return; }
  if (current?.id !== id) return;           // player moved on while we waited
  langs.forEach((lang, i) => {
    const t = document.createElement("track");
    t.kind = "subtitles"; t.label = lang; t.srclang = lang.split("-")[0];
    t.src = `/subs/${id}/${encodeURIComponent(lang)}`;
    if (i === 0) t.default = true;
    vid.appendChild(t);
  });
}

// Credits, an outro, a tab closed on the last thirty seconds: near enough the
// end counts as watched, since "ended" only fires on the very last frame.
function markIfFinished(vid) {
  if (!current || current.watched || !vid.duration) return;
  if (vid.currentTime / vid.duration < 0.92) return;
  current.watched = true;
  post(`/api/watched/${current.id}`, {value: 1}).catch(()=>{});
}

function close_() {
  const vid = $("#pvideo");
  if (current) post(`/api/progress/${current.id}`, {value: vid.currentTime}).catch(()=>{});
  markIfFinished(vid);
  clearInterval(saveTimer);
  vid.pause(); vid.removeAttribute("src"); vid.load();
  $("#player").classList.remove("on");
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
  if ($("#modal").classList.contains("on")) closeModal();
  else if ($("#player").classList.contains("on")) close_();
  else dismissAllJobs();
});

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
    el.querySelector(".t").textContent = j.title;
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
$("#src").addEventListener("change", e => {
  const v = e.target.value;
  state.source     = v.startsWith("s:") ? v.slice(2) : "";
  state.collection = v.startsWith("c:") ? v.slice(2) : "";
  refresh();
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

refresh();
</script>
</body>
</html>
"""
