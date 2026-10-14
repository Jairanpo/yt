"""Thin subprocess wrapper around the yt-dlp binary.

Kept at arm's length on purpose: yt-dlp updates often, and shelling out means
`pip install -U yt-dlp` fixes extractor breakage without touching this code.
"""
import json
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.request
from pathlib import Path

from ytlocal import config

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
# Playlist ids are longer than a video id and carry a family prefix: PL for a
# user-made playlist, OLAK for an auto-generated album, UU/UL for a channel's
# uploads. Matching on the prefix keeps a channel's own id (UC...) out.
_PLAYLIST_ID_RE = re.compile(r"^(PL|OLAK|UU|UL|FL|RD)[A-Za-z0-9_-]{4,}$")


class YtdlpError(RuntimeError):
    pass


def base_cmd(cfg: dict) -> list:
    return [cfg["ytdlp"], "--ignore-config", "--no-warnings", *cfg.get("ytdlp_args", [])]


def check(cfg: dict) -> str:
    try:
        out = subprocess.run([cfg["ytdlp"], "--version"], capture_output=True, text=True,
                             timeout=30)
    except FileNotFoundError:
        raise YtdlpError(
            f"{cfg['ytdlp']!r} not found on PATH. Install it: uv tool install yt-dlp"
        )
    if out.returncode != 0:
        raise YtdlpError(f"yt-dlp --version failed: {out.stderr.strip()}")
    return out.stdout.strip()


_TAB_RE = re.compile(r"/(videos|streams|shorts|playlists|courses)$")
# Tabs that list playlists rather than videos: syncing one would find nothing.
INDEX_TABS = ("/playlists", "/courses")


def _channel_base(ref: str) -> str:
    """A channel URL with no tab on the end, from a handle, name or URL."""
    ref = ref.strip().rstrip("/")
    if not ref.startswith("http"):
        ref = "https://www.youtube.com/" + (ref if ref.startswith("@") else "@" + ref)
    return _TAB_RE.sub("", ref)


# One video, by any of the links YouTube hands out for it. A link that also
# names a playlist (watch?v=...&list=PL...) is taken as that playlist.
_VIDEO_URL_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})")
# Videos picked one link at a time have no listing on YouTube to page through,
# unlisted ones least of all. Their ids live in this URL instead, which is
# also a real YouTube address that plays them in a row.
PICKS_URL = "https://www.youtube.com/watch_videos?video_ids="
PICKS_PREFIX = "PICKS:"


def video_id(ref: str):
    """The id of the one video a link points at, or None."""
    if "list=" in ref:
        return None
    m = _VIDEO_URL_RE.search(ref.strip())
    return m.group(1) if m else None


def picks_url(ids) -> str:
    return PICKS_URL + ",".join(dict.fromkeys(ids))


def picked_ids(url: str) -> list:
    if not (url or "").startswith(PICKS_URL):
        return []
    return [v for v in url[len(PICKS_URL):].split(",") if _ID_RE.match(v)]


def is_picks(url: str) -> bool:
    return (url or "").startswith(PICKS_URL)


def merge_picks(old_url, new_url, entries) -> str:
    """The channel's picks so far, with the new one on the end.

    Renumbers `entries` to their place in the whole list, so a pick lands
    after the ones before it rather than at the top.
    """
    url = picks_url(picked_ids(old_url) + picked_ids(new_url))
    order = picked_ids(url)
    for e in entries:
        e["position"] = order.index(e["id"])
    return url


def source_url(ref: str) -> str:
    """Normalise whatever the user typed into a URL we can page through."""
    ref = ref.strip().rstrip("/")
    if is_picks(ref):
        return ref
    vid = video_id(ref)
    if vid:
        return picks_url([vid])
    if ref.startswith(("PL", "UU", "OLAK")):
        return f"https://www.youtube.com/playlist?list={ref}"
    if "list=" in ref:
        return ref
    # A tab the user named explicitly is left alone -- including /playlists
    # and /courses, which are not video listings at all and are caught by the
    # caller.
    if _TAB_RE.search(ref):
        return _channel_base(ref) + _TAB_RE.search(ref).group(0)
    return _channel_base(ref) + "/videos"


# Kept as an alias: older call sites and muscle memory both say channel_url.
channel_url = source_url


def url_kind(url: str) -> str:
    return "playlist" if "list=" in url or is_picks(url) else "channel"


def is_index(url: str) -> bool:
    return url.endswith(INDEX_TABS)


def live_playlist_id(channel_id: str):
    """YouTube's own playlist of a channel's past streams.

    Every channel has a family of hidden playlists derived from its UC... id;
    UULV... is the one holding its live broadcasts, the same list the Live tab
    shows. Tracking that id makes Live a playlist like any other, and keeps it
    from colliding with the channel, which the /streams tab would share an id
    with.
    """
    if channel_id and channel_id.startswith("UC"):
        return "UULV" + channel_id[2:]
    return None


def _flat(cfg, url, timeout=None, end=None):
    """One flat listing of a tab: (entries, stderr). A missing tab is empty."""
    cmd = base_cmd(cfg) + ["--flat-playlist", "--dump-json", "--ignore-errors"]
    if end:
        cmd += ["--playlist-end", str(int(end))]
    try:
        proc = subprocess.run(cmd + [url], capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        raise YtdlpError(f"timed out after {timeout}s listing {url}")
    entries = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries, proc.stderr or ""


# What Browse offers, in the order it offers it: a course is the most
# deliberate lesson series a creator publishes, so it comes first.
SECTIONS = ("course", "live", "playlist")


def browse(cfg: dict, ref: str, timeout=None):
    """Everything a creator has that can be tracked as a playlist.

    Returns (owner, [items]); each item carries a section -- course, live or
    playlist. The Courses and Playlists tabs yield playlist entries (a PL...
    id and a title, no video count, because counting would mean opening every
    one). The Live tab yields videos, so it is offered as the one playlist
    that holds them all. A channel without one of the tabs simply has nothing
    in that section.

    The three tabs are listed side by side, so browsing costs about as long as
    the slowest of them rather than all three. `timeout` is for callers that
    cannot wait forever -- the web UI browses with a request thread held open,
    where a wedged yt-dlp would hang the tab.
    """
    base = _channel_base(ref)
    jobs = {"course": (base + "/courses", None), "playlist": (base + "/playlists", None),
            "live": (base + "/streams", 1)}
    with ThreadPoolExecutor(len(jobs)) as pool:
        futs = {k: pool.submit(_flat, cfg, url, timeout, end)
                for k, (url, end) in jobs.items()}
        got = {k: f.result() for k, f in futs.items()}

    owner = channel_id = None
    for entries, _ in got.values():
        for e in entries:
            # On these tabs the per-entry channel/uploader keys read "View full
            # playlist"; the owning channel is on the playlist_* keys instead.
            owner = owner or (e.get("playlist_channel") or e.get("playlist_uploader")
                              or (e.get("playlist_title") or "").rsplit(" - ", 1)[0]
                              or None)
            channel_id = channel_id or e.get("playlist_channel_id")
            if not channel_id and (e.get("playlist_id") or "").startswith("UC"):
                channel_id = e["playlist_id"]

    seen, found = set(), []
    for section in ("course", "playlist"):
        for e in got[section][0]:
            pid = e.get("id") or _list_id(e.get("url") or "")
            # A course is usually on the Playlists tab as well; it is shown
            # once, as the course it is.
            if not pid or not _PLAYLIST_ID_RE.match(pid) or pid in seen:
                continue
            seen.add(pid)
            found.append({
                "id": pid, "section": section, "title": e.get("title") or pid,
                "url": e.get("url") or f"https://www.youtube.com/playlist?list={pid}",
            })
    live = live_playlist_id(channel_id)
    if live and any(_ID_RE.match(e.get("id") or "") for e in got["live"][0]):
        found.append({"id": live, "section": "live", "title": "Live streams",
                      "url": f"https://www.youtube.com/playlist?list={live}"})
    if not found:
        why = got["playlist"][1].strip()[:800]
        raise YtdlpError(f"no courses, live streams or playlists found at {base}"
                         + (f"\n{why}" if why else ""))
    found.sort(key=lambda it: SECTIONS.index(it["section"]))
    return owner, found


def sync_source(cfg: dict, url: str, limit=None):
    """Flat-list a channel or playlist. Returns (meta, entries).

    Flat mode is one request per ~100 videos and carries no per-video cost, which
    is what makes cataloguing a whole back catalogue cheap. Entries keep the
    order the listing gave them: newest-first for a channel, curated order for
    a playlist.
    """
    if is_picks(url):
        return _sync_picks(cfg, picked_ids(url))
    kind = url_kind(url)
    cmd = base_cmd(cfg) + [
        "--flat-playlist", "--dump-json", "--ignore-errors",
        "--extractor-args", "youtubetab:approximate_date",
    ]
    if limit:
        cmd += ["--playlist-end", str(int(limit))]
    cmd.append(url)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    entries, meta = [], {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        vid = e.get("id") or ""
        if not _ID_RE.match(vid):
            continue
        if not meta:
            # In flat mode YouTube puts the identity on the playlist_* keys; the
            # per-entry channel_*/uploader_* keys come back as None. Note that
            # for a playlist, playlist_channel_id is the *owning channel* --
            # keying a playlist by it merges it into that channel.
            if kind == "playlist":
                pid = e.get("playlist_id") or _list_id(url)
                meta = {
                    "kind": "playlist",
                    "source_id": pid,
                    "name": e.get("playlist_title") or e.get("playlist"),
                    "owner": (e.get("playlist_channel") or e.get("playlist_uploader")
                              or e.get("channel")),
                    "handle": _handle_from(e),
                    # The channel it hangs under in the library. A live
                    # playlist names it in its own id, should the listing not.
                    "channel_id": (e.get("playlist_channel_id")
                                   or ("UC" + pid[4:] if (pid or "").startswith("UULV")
                                       else None)),
                    "section": "live" if (pid or "").startswith("UULV") else None,
                }
            else:
                cid = (e.get("channel_id") or e.get("playlist_channel_id")
                       or e.get("playlist_id"))
                name = (e.get("channel") or e.get("playlist_channel")
                        or e.get("playlist_uploader") or e.get("uploader"))
                meta = {
                    "kind": "channel", "source_id": cid, "name": name,
                    "owner": None, "handle": _handle_from(e),
                    "channel_id": cid, "section": None,
                }
                if url.endswith("/streams") and live_playlist_id(cid):
                    # The Live tab shares the channel's id; filed under it, it
                    # would overwrite the channel. It is the live playlist.
                    meta.update(kind="playlist", source_id=live_playlist_id(cid),
                                name="Live streams", owner=name, section="live")
        date = _fmt_date(e.get("upload_date"))
        entries.append({
            "id": vid,
            # A private, deleted or region-locked entry keeps its slot in the
            # listing but arrives with no title at all -- nothing to show and
            # nothing to download.
            "unavailable": not e.get("title"),
            "title": e.get("title") or vid,
            "duration": int(e["duration"]) if e.get("duration") else None,
            "description": e.get("description") or None,
            "upload_date": date,
            # Flat listings carry no true publish date. approximate_date derives
            # one from the "N months ago" label, so the day-of-month is noise --
            # good enough to sort by, not something to present as exact.
            "date_approx": 1 if date else 0,
            "position": len(entries),
        })

    if not entries:
        raise YtdlpError(
            f"no videos found at {url}\n{(proc.stderr or '').strip()[:800]}"
        )
    if not meta.get("source_id"):
        meta["source_id"] = _list_id(url) or url
    return meta, entries


def _sync_picks(cfg: dict, ids: list):
    """Full metadata for hand-picked videos. Returns (meta, entries) as
    sync_source does, filed under one per-channel source.

    Costs a request per video rather than one per hundred, which is fine for
    a handful picked by hand -- and in return the dates are exact.
    """
    # Formats are a download's concern; when YouTube withholds them (its bot
    # check does) the title and date still come through.
    cmd = base_cmd(cfg) + ["--dump-json", "--skip-download", "--no-playlist",
                           "--ignore-errors", "--ignore-no-formats-error"]
    proc = subprocess.run(cmd + [f"https://www.youtube.com/watch?v={v}" for v in ids],
                          capture_output=True, text=True)
    infos = {}
    for line in proc.stdout.splitlines():
        if line.strip().startswith("{"):
            try:
                info = json.loads(line)
            except json.JSONDecodeError:
                continue
            infos[info.get("id")] = info
    if not infos:
        raise YtdlpError(f"could not read {', '.join(ids)}\n"
                         f"{(proc.stderr or '').strip()[:800]}")
    first = next(iter(infos.values()))
    cid = first.get("channel_id") or _channel_id_of(cfg, first.get("uploader_id"))
    owner = first.get("channel") or first.get("uploader")
    meta = {"kind": "playlist", "source_id": PICKS_PREFIX + (cid or first["id"]),
            "name": "Picked videos", "owner": owner, "handle": _handle_from(first),
            "channel_id": cid, "section": "picks"}
    entries = []
    for pos, vid in enumerate(ids):
        info = infos.get(vid)
        if info is None:
            # Gone private or deleted since it was picked: keep the slot,
            # hidden, the way a playlist keeps one.
            entries.append({"id": vid, "unavailable": True, "title": vid,
                            "duration": None, "description": None,
                            "upload_date": None, "date_approx": 0, "position": pos})
            continue
        entries.append({
            "id": vid, "unavailable": False, "title": info.get("title") or vid,
            "duration": int(info["duration"]) if info.get("duration") else None,
            "description": info.get("description") or None,
            "upload_date": _fmt_date(info.get("upload_date")),
            "date_approx": 0, "position": pos,
        })
    return meta, entries


def _channel_id_of(cfg: dict, handle):
    """A channel's UC... id from its @handle, for when a video's page left it
    out. Without it the picks could not be filed under the channel."""
    if not handle:
        return None
    entries, _ = _flat(cfg, _channel_base(handle) + "/videos", timeout=120, end=1)
    return next((e.get("playlist_channel_id") or e.get("channel_id")
                 for e in entries), None)


def _list_id(url: str):
    m = re.search(r"[?&]list=([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else None


def _handle_from(entry: dict):
    for key in ("playlist_uploader_id", "uploader_id", "channel_url",
                "uploader_url", "playlist_webpage_url"):
        val = entry.get(key) or ""
        m = re.search(r"@([\w.\-]+)", val)
        if m:
            return "@" + m.group(1)
    return None


def _fmt_date(raw):
    if raw and len(str(raw)) == 8 and str(raw).isdigit():
        s = str(raw)
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return None


def fetch_info(cfg: dict, vid: str) -> dict:
    """Full metadata for one video, no download. Used to backfill dates."""
    cmd = base_cmd(cfg) + ["--dump-json", "--skip-download",
                           f"https://www.youtube.com/watch?v={vid}"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise YtdlpError((proc.stderr or "metadata fetch failed").strip()[:500])
    info = json.loads(proc.stdout.splitlines()[0])
    return {
        "title": info.get("title"),
        "description": info.get("description"),
        "duration": int(info["duration"]) if info.get("duration") else None,
        "upload_date": _fmt_date(info.get("upload_date")),
        "chapters": chapters(info),
    }


def chapters(info: dict) -> list:
    """The creator's sections, from the timestamps they listed. Often none."""
    return [{"start": round(float(c["start_time"]), 2),
             "end": round(float(c["end_time"]), 2),
             "title": c.get("title") or ""}
            for c in info.get("chapters") or []]


def format_selector(max_height: int, audio_only=False) -> str:
    if audio_only:
        return "bestaudio[ext=m4a]/bestaudio"
    h = int(max_height)
    # Prefer mp4/m4a so the <video> tag in the web UI plays it without transcoding.
    return (
        f"bv*[height<=?{h}][ext=mp4]+ba[ext=m4a]/"
        f"b[height<=?{h}][ext=mp4]/"
        f"bv*[height<=?{h}]+ba/b[height<=?{h}]/b"
    )


def stream_selector(max_height: int) -> str:
    # YouTube no longer serves one file with both picture and sound, so a
    # stream is always a pair the page stitches back together. Plain https
    # (not HLS) H.264 + AAC is what every browser's MediaSource can take, and
    # those files carry the byte index that makes seeking possible.
    h = int(max_height)
    return (f"bv*[height<=?{h}][ext=mp4][vcodec^=avc1][protocol=https]"
            f"+ba[ext=m4a][protocol=https]")


def stream_info(cfg: dict, vid: str) -> dict:
    """Where to read a video from without downloading it.

    Returns {duration, video, audio}; each track is {url, headers, mime, size}.
    The URLs are signed and expire after a few hours.
    """
    cmd = base_cmd(cfg) + ["-j", "--no-playlist",
                           "-f", stream_selector(cfg["max_height"]),
                           f"https://www.youtube.com/watch?v={vid}"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise YtdlpError((proc.stderr or "no streamable format").strip()[:500])
    info = json.loads(proc.stdout.splitlines()[0])
    out = {"duration": info.get("duration"), "chapters": chapters(info)}
    for f in info.get("requested_formats") or []:
        kind = "audio" if f.get("vcodec") in (None, "none") else "video"
        codec = f["acodec"] if kind == "audio" else f["vcodec"]
        out[kind] = {"url": f["url"], "headers": f.get("http_headers") or {},
                     "mime": f'{kind}/mp4; codecs="{codec}"',
                     "size": f.get("filesize")}
    if "video" not in out or "audio" not in out:
        raise YtdlpError("no separate H.264 + AAC streams to play")
    return out


def output_template(media_dir: Path) -> str:
    return str(media_dir / (
        "%(channel,uploader|Unknown)s/"
        "%(upload_date>%Y-%m-%d,release_date>%Y-%m-%d|0000-00-00)s"
        " - %(title).120B [%(id)s].%(ext)s"
    ))


def download(cfg: dict, vid: str, media_dir: Path, audio_only=False,
             on_progress=None) -> dict:
    """Download one video. Returns {path, upload_date, duration, description}.

    on_progress(fraction|None, human_str) is called as bytes land.
    """
    sink = Path(tempfile.mkstemp(prefix="ytlocal-", suffix=".tsv")[1])
    try:
        cmd = base_cmd(cfg) + [
            "--no-simulate", "--newline", "--no-playlist",
            "-f", format_selector(cfg["max_height"], audio_only),
            "-o", output_template(media_dir),
            "--restrict-filenames",
            "--no-mtime",
            "--retries", "5", "--fragment-retries", "10",
            "--progress-template",
            "PROG\t%(progress.downloaded_bytes)s\t"
            "%(progress.total_bytes,progress.total_bytes_estimate)s\t"
            "%(progress.speed)s\t%(progress.eta)s",
            "--print-to-file",
            "after_move:%(id)s\t%(filepath)s\t%(upload_date)s\t%(duration)s\t%(description)j",
            str(sink),
        ]
        if audio_only:
            cmd += ["-x", "--audio-format", "m4a"]
        else:
            cmd += ["--merge-output-format", "mp4"]
        cmd.append(f"https://www.youtube.com/watch?v={vid}")

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, bufsize=1)
        tail = []
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line.startswith("PROG\t"):
                if on_progress:
                    on_progress(*_parse_progress(line))
            elif line.strip():
                tail.append(line.strip())
                del tail[:-20]
        proc.wait()
        stderr = (proc.stderr.read() or "").strip()
        if proc.returncode != 0:
            raise YtdlpError((stderr or "\n".join(tail[-5:]) or "download failed")[:800])

        result = _read_sink(sink, vid)
        if not result:
            raise YtdlpError("yt-dlp reported success but produced no file path")
        if cfg.get("sub_langs") and not audio_only:
            if on_progress:
                on_progress(1.0, "fetching subtitles")
            fetch_subs(cfg, vid, media_dir)
        return result
    finally:
        sink.unlink(missing_ok=True)


def fetch_subs(cfg: dict, vid: str, media_dir: Path) -> bool:
    """Best-effort subtitle pass, run only after the video is safely on disk.

    Deliberately a separate invocation: YouTube rate-limits subtitle requests
    hard, and a 429 here used to abort the whole download. Reusing the same
    output template lands the .vtt files on the video's stem.
    """
    cmd = base_cmd(cfg) + [
        "--skip-download", "--no-playlist",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", cfg["sub_langs"], "--convert-subs", "vtt",
        "--restrict-filenames", "--no-mtime",
        "-o", output_template(media_dir),
        f"https://www.youtube.com/watch?v={vid}",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _parse_progress(line: str):
    parts = line.split("\t")
    got, total, speed, eta = (parts + ["NA"] * 5)[1:5]

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    got, total, speed, eta = num(got), num(total), num(speed), num(eta)
    frac = (got / total) if got and total else None
    bits = []
    if frac is not None:
        bits.append(f"{frac * 100:5.1f}%")
    if got:
        bits.append(f"{got / 1e6:.0f}MB" + (f"/{total / 1e6:.0f}MB" if total else ""))
    if speed:
        bits.append(f"{speed / 1e6:.1f}MB/s")
    if eta:
        bits.append(f"eta {int(eta // 60)}m{int(eta % 60):02d}s")
    return frac, "  ".join(bits) or "working"


def _read_sink(sink: Path, vid: str):
    for line in sink.read_text(errors="replace").splitlines():
        cols = line.split("\t")
        if len(cols) < 2 or cols[0] != vid:
            continue
        path = Path(cols[1])
        desc = None
        if len(cols) > 4 and cols[4] not in ("", "NA", "null"):
            try:
                desc = json.loads(cols[4])
            except json.JSONDecodeError:
                desc = None
        return {
            "path": path,
            "upload_date": _fmt_date(cols[2]) if len(cols) > 2 else None,
            "duration": int(float(cols[3])) if len(cols) > 3 and cols[3].replace(".", "").isdigit() else None,
            "description": desc,
        }
    return None


def thumb_url(vid: str) -> str:
    return f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"


def fetch_thumb(vid: str, dest: Path) -> bool:
    """Cache a thumbnail locally so the web UI never reaches out to Google."""
    if dest.exists() and dest.stat().st_size > 0:
        return True
    req = urllib.request.Request(thumb_url(vid), headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    if not data:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def sidecar_subs(path: Path) -> list:
    """VTT files yt-dlp wrote next to the video, as (lang, Path)."""
    if not path:
        return []
    stem, out = path.with_suffix("").name, []
    for cand in sorted(path.parent.glob(f"{glob_escape(stem)}.*.vtt")):
        lang = cand.name[len(stem) + 1:-4]
        out.append((lang, cand))
    return out


def glob_escape(s: str) -> str:
    return s.replace("[", "[[]")
