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
  .icon { flex:0 0 auto; width:34px; }
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
  #pclose { position:absolute; top:16px; right:20px; background:none; border:none;
            color:#e9e7e3; font-size:26px; cursor:pointer; line-height:1; }
  #jobs { position:fixed; right:16px; bottom:16px; width:300px; z-index:40;
          display:flex; flex-direction:column; gap:8px; }
  .job { background:var(--panel); border:1px solid var(--edge); border-radius:8px;
         padding:9px 11px; font-size:12.5px; box-shadow:var(--shadow); }
  .job .t { font-weight:550; overflow:hidden; text-overflow:ellipsis;
            white-space:nowrap; }
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
  <select id="chan"><option value="">All channels</option></select>
  <div class="chips">
    <button class="chip" id="f-have"      aria-pressed="false">Downloaded</button>
    <button class="chip" id="f-starred"   aria-pressed="false">Starred</button>
    <button class="chip" id="f-unwatched" aria-pressed="false">Unwatched</button>
  </div>
  <div class="stats" id="stats"></div>
</header>
<main><div class="grid" id="grid"></div><div class="empty" id="empty" hidden></div></main>

<div id="jobs"></div>

<div id="player">
  <button id="pclose" title="Close (Esc)">&times;</button>
  <video id="pvideo" controls playsinline></video>
  <div id="pmeta"><h2 id="ptitle"></h2><div class="sub" id="psub"></div>
    <div id="pdesc"></div></div>
</div>

<script>
const state = { q:"", channel:"", have:null, starred:false, unwatched:false, videos:[] };
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
  if (state.channel) p.set("channel", state.channel);
  if (state.have !== null) p.set("have", state.have ? "1" : "0");
  if (state.starred) p.set("starred", "1");
  if (state.unwatched) p.set("unwatched", "1");
  return p.toString();
}

let chansRendered = false;
async function refresh() {
  const d = await api("/api/state?" + params());
  state.videos = d.videos;
  if (!chansRendered && d.channels.length) {
    const sel = $("#chan");
    for (const c of d.channels) {
      const o = document.createElement("option");
      o.value = c.id; o.textContent = `${c.name} (${c.have}/${c.total})`;
      sel.appendChild(o);
    }
    chansRendered = true;
  }
  const s = d.stats;
  $("#stats").textContent =
    `${s.have}/${s.total} on disk · ${fmtSize(s.bytes)} · ${s.channels} channels`;
  render(d.videos);
  renderJobs(d.jobs);
}

function render(vs) {
  const grid = $("#grid"), empty = $("#empty");
  grid.innerHTML = "";
  empty.hidden = vs.length > 0;
  if (!vs.length) {
    empty.textContent = state.q || state.channel || state.have !== null
      ? "Nothing matches those filters."
      : "Catalog is empty — run  yt add @channel  in the terminal.";
    return;
  }
  for (const v of vs) grid.appendChild(card(v));
}

function card(v) {
  const el = document.createElement("div");
  el.className = "card";
  const pct = v.have && v.duration && v.progress
              ? Math.min(100, 100 * v.progress / v.duration) : 0;
  el.innerHTML = `
    <div class="thumbwrap">
      <img loading="lazy" src="/thumb/${v.id}" alt="">
      ${v.have ? '<span class="flag have">on disk</span>' : ''}
      ${v.starred ? '<span class="flag" style="left:auto;right:6px;top:6px">★</span>' : ''}
      ${v.duration ? `<span class="badge">${fmtDur(v.duration)}</span>` : ''}
      ${pct ? `<div class="bar"><i style="width:${pct}%"></i></div>` : ''}
    </div>
    <div class="meta">
      <div class="title"></div>
      <div class="sub"></div>
      <div class="row"></div>
    </div>`;
  el.querySelector(".title").textContent = v.title;
  el.querySelector(".sub").textContent =
    [v.channel, fmtDate(v), v.have ? fmtSize(v.size) : null].filter(Boolean).join(" · ");

  const row = el.querySelector(".row");
  const main = document.createElement("button");
  main.className = "act primary";
  main.textContent = v.have ? "Watch" : "Download";
  main.onclick = () => v.have ? open_(v) : grab(v, main);
  row.appendChild(main);

  const star = document.createElement("button");
  star.className = "act icon"; star.title = "Star";
  star.textContent = v.starred ? "★" : "☆";
  star.onclick = async () => { const r = await post(`/api/star/${v.id}`);
                               v.starred = r.starred;
                               star.textContent = r.starred ? "★" : "☆"; };
  row.appendChild(star);

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

function close_() {
  const vid = $("#pvideo");
  if (current) post(`/api/progress/${current.id}`, {value: vid.currentTime}).catch(()=>{});
  clearInterval(saveTimer);
  vid.pause(); vid.removeAttribute("src"); vid.load();
  $("#player").classList.remove("on");
  current = null; refresh();
}
$("#pclose").onclick = close_;
$("#pvideo").addEventListener("ended", async () => {
  if (current) await post(`/api/watched/${current.id}`, {value: 1});
  close_();
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && $("#player").classList.contains("on")) close_();
});

/* ---- jobs ---- */
let jobTimer = null;
function renderJobs(jobs) {
  const box = $("#jobs");
  box.innerHTML = "";
  for (const j of jobs) {
    const el = document.createElement("div");
    el.className = "job" + (j.state === "error" ? " error" : "");
    const pct = Math.round(100 * (j.fraction || 0));
    el.innerHTML = `<div class="t"></div><div class="d"></div>
      <div class="track"><i style="width:${pct}%"></i></div>`;
    el.querySelector(".t").textContent = j.title;
    el.querySelector(".d").textContent =
      j.state === "error" ? j.error : (j.state === "done" ? "done" : j.detail);
    if (j.state !== "queued" && j.state !== "running")
      el.onclick = () => { post("/api/jobs/clear"); refresh(); };
    box.appendChild(el);
  }
  const busy = jobs.some(j => j.state === "queued" || j.state === "running");
  clearInterval(jobTimer);
  if (busy) jobTimer = setInterval(pollJobs, 1200);
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
$("#chan").addEventListener("change", e => { state.channel = e.target.value; refresh(); });
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

refresh();
</script>
</body>
</html>
"""
