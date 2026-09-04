"""Thin subprocess wrapper around the yt-dlp binary.

Kept at arm's length on purpose: yt-dlp updates often, and shelling out means
`pip install -U yt-dlp` fixes extractor breakage without touching this code.
"""
import json
import re
import subprocess
import tempfile
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


_TAB_RE = re.compile(r"/(videos|streams|shorts|playlists)$")


def _channel_base(ref: str) -> str:
    """A channel URL with no tab on the end, from a handle, name or URL."""
    ref = ref.strip().rstrip("/")
    if not ref.startswith("http"):
        ref = "https://www.youtube.com/" + (ref if ref.startswith("@") else "@" + ref)
    return _TAB_RE.sub("", ref)


def source_url(ref: str) -> str:
    """Normalise whatever the user typed into a URL we can page through."""
    ref = ref.strip().rstrip("/")
    if ref.startswith(("PL", "UU", "OLAK")):
        return f"https://www.youtube.com/playlist?list={ref}"
    if "list=" in ref:
        return ref
    # A tab the user named explicitly is left alone -- including /playlists,
    # which is not a video listing at all and is caught by the caller.
    if _TAB_RE.search(ref):
        return _channel_base(ref) + _TAB_RE.search(ref).group(0)
    return _channel_base(ref) + "/videos"


# Kept as an alias: older call sites and muscle memory both say channel_url.
channel_url = source_url


def url_kind(url: str) -> str:
    return "playlist" if "list=" in url else "channel"


def playlists_url(ref: str) -> str:
    """Point whatever the user typed at that creator's playlists tab.

    /videos, /playlists, a bare handle and a full channel URL all name the
    same channel, so all four land on the same tab.
    """
    return _channel_base(ref) + "/playlists"


def list_playlists(cfg: dict, url: str):
    """Flat-list a channel's playlists tab. Returns (owner, [playlists]).

    The tab yields playlist entries, not videos: each carries a PL... id and a
    title but no video count, because counting would mean opening every one.
    """
    cmd = base_cmd(cfg) + ["--flat-playlist", "--dump-json", "--ignore-errors", url]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    owner, seen, found = None, set(), []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        pid = e.get("id") or _list_id(e.get("url") or "")
        if not pid or not _PLAYLIST_ID_RE.match(pid) or pid in seen:
            continue
        seen.add(pid)
        # On this tab the per-entry channel/uploader keys read "View full
        # playlist"; the owning channel is on the playlist_* keys instead.
        if owner is None:
            owner = (e.get("playlist_channel") or e.get("playlist_uploader")
                     or (e.get("playlist_title") or "").replace(" - Playlists", "")
                     or None)
        found.append({
            "id": pid,
            "title": e.get("title") or pid,
            "url": e.get("url") or f"https://www.youtube.com/playlist?list={pid}",
        })
    if not found:
        raise YtdlpError(
            f"no playlists found at {url}\n{(proc.stderr or '').strip()[:800]}"
        )
    return owner, found


def sync_source(cfg: dict, url: str, limit=None):
    """Flat-list a channel or playlist. Returns (meta, entries).

    Flat mode is one request per ~100 videos and carries no per-video cost, which
    is what makes cataloguing a whole back catalogue cheap. Entries keep the
    order the listing gave them: newest-first for a channel, curated order for
    a playlist.
    """
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
                meta = {
                    "kind": "playlist",
                    "source_id": e.get("playlist_id") or _list_id(url),
                    "name": e.get("playlist_title") or e.get("playlist"),
                    "owner": (e.get("playlist_channel") or e.get("playlist_uploader")
                              or e.get("channel")),
                    "handle": _handle_from(e),
                }
            else:
                meta = {
                    "kind": "channel",
                    "source_id": (e.get("channel_id") or e.get("playlist_channel_id")
                                  or e.get("playlist_id")),
                    "name": (e.get("channel") or e.get("playlist_channel")
                             or e.get("playlist_uploader") or e.get("uploader")),
                    "owner": None,
                    "handle": _handle_from(e),
                }
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
    }


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
