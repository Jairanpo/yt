"""Localhost web UI. Stdlib only; no network calls from the browser."""
import json
import mimetypes
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ytlocal import config, db, ytdlp
from ytlocal.jobs import Cataloguer, Downloader
from ytlocal.ui import PAGE
from ytlocal import toggl as tg

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
# A job card is either a download (keyed by video id) or a source being
# catalogued (keyed by what was typed into the Add box).
_JOB_ID_RE = re.compile(r"^(?:src:.{1,400}|[A-Za-z0-9_-]{11})$", re.S)
_HANDLE_RE = re.compile(r"^@?[A-Za-z0-9_.\-]{2,120}$")
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK = 256 * 1024

# Everything this library can actually track. A page that forbids outbound
# requests of its own has no business handing an arbitrary URL to yt-dlp
# because something got typed into a box.
YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com",
            "music.youtube.com", "youtu.be", "www.youtu.be"}


def _check_yt_ref(raw, what: str) -> str:
    """Trim and sanity-check anything the page offers as a thing to track.

    Raises ValueError with something worth showing the user.
    """
    ref = (raw or "").strip()
    if not ref:
        raise ValueError(what)
    if len(ref) > 400:
        raise ValueError("that is too long to be a channel or playlist")
    if "://" in ref or ref.lower().startswith("www."):
        url = ref if "://" in ref else "https://" + ref
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        if host not in YT_HOSTS:
            raise ValueError(f"{host or 'that'} is not YouTube — this library "
                             f"only tracks youtube.com")
    elif not _HANDLE_RE.match(ref):
        raise ValueError(what)
    return ref


def clean_source_ref(raw) -> str:
    """What the Add box accepts: a handle, a bare id, or a YouTube URL."""
    ref = _check_yt_ref(raw, "paste a channel handle (@name), a channel URL, "
                             "a playlist URL, a PL… id or a video link")
    if ytdlp.is_index(ytdlp.source_url(ref)):
        # The tab lists playlists, not videos, so syncing it would find
        # nothing. Browsing it is the thing to do instead, and this page can.
        raise ValueError("that is a creator's playlist index, not one source — "
                         "use Browse to pick from it")
    return ref


def clean_creator_ref(raw) -> str:
    """What Browse accepts: a creator, whose tabs we can then list."""
    ref = _check_yt_ref(raw, "paste a channel handle (@name) or a channel URL "
                             "to see its courses, live streams and playlists")
    if "list=" in ref or ref.startswith(("PL", "OLAK", "UU", "FL", "RD")):
        raise ValueError("that is one playlist, not a creator — Add tracks it "
                         "directly")
    return ref


# What an audio-only fetch leaves on disk, so a card can say so.
AUDIO_EXTS = (".m4a", ".mp3", ".opus", ".ogg", ".aac", ".flac", ".wav")


def row_to_json(r) -> dict:
    return {
        "id": r["id"],
        "title": r["title"],
        "channel": r["channel_name"] or r["channel_handle"] or "unknown",
        "date": r["upload_date"],
        "date_approx": bool(r["date_approx"]),
        "duration": r["duration"],
        "description": (r["description"] or "")[:4000],
        "have": r["downloaded_path"] is not None,
        "audio": (r["downloaded_path"] or "").endswith(AUDIO_EXTS),
        "size": r["filesize"],
        "starred": bool(r["starred"]),
        "watched": bool(r["watched"]),
        "hidden": bool(r["hidden"]),
        "unavailable": bool(r["unavailable"]),
        "progress": r["progress"],
        "marks": r["n_marks"],
    }


class Streams:
    """Resolved stream addresses, so a seek does not cost a yt-dlp run.

    The signed URLs live for about six hours; five keeps a margin. One lock per
    video stops the page's parallel video and audio requests from resolving
    the same thing twice.
    """
    TTL = 5 * 3600

    def __init__(self, cfg):
        self.cfg = cfg
        self._lock = threading.Lock()
        self._locks, self._hit = {}, {}

    def get(self, vid, fresh=False) -> dict:
        with self._lock:
            vlock = self._locks.setdefault(vid, threading.Lock())
        with vlock:
            hit = self._hit.get(vid)
            if fresh or not hit or time.time() - hit[0] > self.TTL:
                hit = (time.time(), ytdlp.stream_info(self.cfg, vid))
                self._hit[vid] = hit
            return hit[1]


class Handler(BaseHTTPRequestHandler):
    server_version = "ytlocal"
    protocol_version = "HTTP/1.1"

    # --- plumbing ---------------------------------------------------------

    def log_message(self, fmt, *args):
        if self.server.verbose:
            super().log_message(fmt, *args)

    def _send(self, code, body=b"", ctype="application/octet-stream", extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # The whole point is a sealed library: no outbound requests from the page.
        # The Toggl timer does not need an exception here -- the page asks this
        # server to start it, and the server is what talks to Toggl.
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; "
                         "media-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self' 'unsafe-inline'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj), "application/json; charset=utf-8")

    def _fail(self, code, msg):
        # The client may already be gone (the usual cause of a 500 here is a
        # reset mid-stream); never let the error path raise a second time.
        try:
            self._json({"error": msg}, code)
        except ConnectionError:
            self.close_connection = True

    @property
    def conn(self):
        if not hasattr(self, "_conn"):
            self._conn = db.connect()
        return self._conn

    @property
    def cfg(self):
        return self.server.cat.cfg

    def finish(self):
        try:
            if hasattr(self, "_conn"):
                self._conn.close()
        finally:
            super().finish()

    # --- routing ----------------------------------------------------------

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path, qs = url.path, urllib.parse.parse_qs(url.query)
        try:
            if path == "/":
                return self._send(200, PAGE, "text/html; charset=utf-8")
            if path == "/api/state":
                return self._api_state(qs)
            if path.startswith("/api/collections/"):
                vid = path[len("/api/collections/"):]
                if not _ID_RE.match(vid):
                    return self._fail(400, "bad id")
                return self._json({"collections": [
                    {"id": c["id"], "name": c["name"]}
                    for c in db.collections_for(self.conn, vid)]})
            if path.startswith("/api/subs/"):
                return self._sub_langs(path[len("/api/subs/"):])
            if path == "/api/toggl/status":
                return self._toggl_status()
            if path == "/api/jobs":
                return self._json({"jobs": self._jobs()})
            if path.startswith("/thumb/"):
                return self._thumb(path[7:])
            if path.startswith("/api/marks/"):
                vid = path[len("/api/marks/"):]
                if not _ID_RE.match(vid):
                    return self._fail(400, "bad id")
                return self._json({"marks": db.marks(self.conn, vid)})
            if path.startswith("/api/chapters/"):
                return self._chapters(path[len("/api/chapters/"):])
            if path.startswith("/api/stream/"):
                return self._stream_meta(path[len("/api/stream/"):])
            if path.startswith("/stream/"):
                return self._stream(path[len("/stream/"):])
            if path.startswith("/media/"):
                return self._media(path[7:])
            if path.startswith("/subs/"):
                return self._subs(path[6:])
            return self._fail(404, "not found")
        except ConnectionError:
            # Reset/broken pipe: the browser seeked away or closed the tab
            # mid-stream. Normal for <video>; nothing left to reply to.
            self.close_connection = True
        except Exception as exc:  # noqa: BLE001
            self._fail(500, str(exc))

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        try:
            if url.path == "/api/jobs/clear":
                jid = (self._body().get("id") or "").strip()
                if jid:
                    if not _JOB_ID_RE.match(jid):
                        return self._fail(400, "bad job id")
                    return self._json({"ok": self.server.dl.forget(jid)
                                             or self.server.cat.forget(jid)})
                self.server.dl.forget_finished()
                self.server.cat.forget_finished()
                return self._json({"ok": True})
            if url.path == "/api/sources/browse":
                # Held open while yt-dlp lists the tab: a few seconds, and the
                # sheet says so. Capped, so a wedged listing cannot hang the
                # request thread for good.
                try:
                    ref = clean_creator_ref(self._body().get("creator"))
                except ValueError as exc:
                    return self._fail(400, str(exc))
                try:
                    owner, found = ytdlp.browse(self.server.cat.cfg, ref, timeout=180)
                except ytdlp.YtdlpError as exc:
                    return self._fail(502, str(exc))
                db.mark_courses(self.conn, (pl["id"] for pl in found
                                             if pl["section"] == "course"))
                tracked = {r["id"] for r in db.sources(self.conn, "playlist")}
                return self._json({
                    "creator": owner or ref,
                    "playlists": [{"id": pl["id"], "title": pl["title"],
                                   "section": pl["section"],
                                   "tracked": pl["id"] in tracked}
                                  for pl in found],
                })
            if url.path == "/api/toggl/start":
                body = self._body()
                row = db.get_video(self.conn, body.get("video") or "")
                if not row:
                    return self._fail(404, "unknown video")
                chan = row["channel_name"] or row["channel_handle"] or "unknown"
                m = db.toggl_map(self.conn).get(chan, {})
                tags = [t.strip() for t in (m.get("tags") or "").split(",") if t.strip()]
                try:
                    entry, missing = tg.start(self.cfg, m.get("name") or chan,
                                              m.get("project") or None, tags)
                except tg.TogglError as exc:
                    return self._fail(502, str(exc))
                return self._json({"ok": True, "running": tg.as_json(entry),
                                   "project_missing": m.get("project") if missing else None})
            if url.path == "/api/toggl/stop":
                body = self._body()
                try:
                    running = tg.current(self.cfg) if not body.get("id") else None
                    eid = body.get("id") or (running or {}).get("id")
                    if not eid:
                        return self._json({"ok": True, "running": {}})
                    tg.stop(self.cfg, eid, body.get("workspace"))
                except tg.TogglError as exc:
                    # Most often the timer was already stopped in Toggl itself:
                    # answer with what is really running instead of an error.
                    try:
                        now = tg.current(self.cfg)
                    except tg.TogglError:
                        return self._fail(502, str(exc))
                    if (now or {}).get("id") == eid:
                        return self._fail(502, str(exc))
                    return self._json({"ok": True, "running": tg.as_json(now)})
                return self._json({"ok": True, "running": {}})
            if len(parts) == 3 and parts[0] == "api":
                action, vid = parts[1], parts[2]
                if not _ID_RE.match(vid):
                    return self._fail(400, "bad video id")
                return self._action(action, vid)
            if url.path == "/api/sources":
                # Tracking a channel or playlist is a handful of network
                # round-trips, so it goes on the queue and reports itself
                # through the same job cards a download uses. `refs` is the
                # batch a browse produces; the queue runs them one at a time.
                # A browsed pick arrives as {ref, section}: only Browse can
                # tell a course from any other playlist.
                body = self._body()
                raw = body.get("refs")
                if raw is None:
                    raw = [body.get("ref")]
                if not isinstance(raw, list):
                    return self._fail(400, "refs must be a list")
                if not 1 <= len(raw) <= 50:
                    return self._fail(400, "pick between 1 and 50 at a time")
                picks = [r if isinstance(r, dict) else {"ref": r} for r in raw]
                try:
                    refs = [(clean_source_ref(r.get("ref")),
                             r.get("section") if r.get("section") == "course" else None)
                            for r in picks]
                except ValueError as exc:
                    return self._fail(400, str(exc))
                jobs = [self.server.cat.enqueue(r, section=sec).as_dict()
                        for r, sec in refs]
                return self._json({"ok": True, "job": jobs[0], "jobs": jobs})
            if url.path == "/api/collections":
                body = self._body()
                name = (body.get("name") or "").strip()
                if not name:
                    return self._fail(400, "name required")
                c = db.create_collection(self.conn, name)
                return self._json({"ok": True, "id": c["id"], "name": c["name"]})
            if url.path == "/api/shelve":
                body = self._body()
                sid = body.get("source") or ""
                if not self.conn.execute("SELECT 1 FROM sources WHERE id = ?",
                                         (sid,)).fetchone():
                    return self._fail(404, "unknown source")
                value = bool(body.get("value", True))
                db.set_shelved(self.conn, [sid], value)
                return self._json({"ok": True, "shelved": value})
            if url.path == "/api/toggl":
                body = self._body()
                try:
                    db.set_toggl(self.conn, body.get("channel"),
                                 body.get("name"), body.get("project"),
                                 body.get("tags"))
                except ValueError as exc:
                    return self._fail(400, str(exc))
                return self._json({"ok": True, "channels": db.toggl_channels(self.conn)})
            if url.path == "/api/topic":
                body = self._body()
                try:
                    db.set_topic(self.conn, body.get("creator"), body.get("topic"))
                except ValueError as exc:
                    return self._fail(400, str(exc))
                return self._json({"ok": True})
            if url.path == "/api/sort":
                body = self._body()
                sort = body.get("sort") or "default"
                if sort not in db.SORTS:
                    return self._fail(400, f"unknown sort {sort!r}")
                coll = body.get("collection")
                db.set_sort(self.conn, sort, source=body.get("source") or None,
                            collection=int(coll) if coll else None)
                return self._json({"ok": True, "sort": sort})
            return self._fail(404, "not found")
        except ConnectionError:
            self.close_connection = True
        except Exception as exc:  # noqa: BLE001
            self._fail(500, str(exc))

    def _jobs(self) -> list:
        """Every card the page should show. Sources first: they gate the rest."""
        return self.server.cat.snapshot() + self.server.dl.snapshot()

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    # --- endpoints --------------------------------------------------------

    def _api_state(self, qs):
        def one(key, default=None):
            return qs.get(key, [default])[0]

        have = {"1": True, "0": False}.get(one("have"))
        source = one("source") or None
        collection = int(one("collection")) if one("collection") else None
        # No sort in the query string means "whatever this view was last set
        # to" -- the preference lives in the catalog, not in the page.
        sort = one("sort") or db.get_sort(self.conn, source, collection)
        if sort not in db.SORTS:
            sort = "default"
        rows = db.query_videos(
            self.conn,
            source=source,
            collection=collection,
            q=(one("q") or "").strip() or None,
            have=have,
            starred=one("starred") == "1",
            unwatched=one("unwatched") == "1",
            hidden=one("hidden") == "1",
            limit=int(one("limit", "300")),
            offset=int(one("offset", "0")),
            sort=sort,
        )
        # Sources arrive grouped under their creator, channel first, then its
        # courses, live streams and playlists. `group` names the creator a
        # source hangs under, so the picker can nest them without guessing --
        # playlist titles alone repeat across creators.
        topics = db.topics(self.conn)
        srcs = [
            {"id": s["id"], "kind": s["kind"], "section": s["section"],
             "name": s["name"] or s["handle"] or s["url"],
             "creator": g["creator"] or s["creator"], "handle": s["handle"],
             "group": g["key"], "topic": topics.get(g["key"], ""),
             "owner": s["owner"],
             "shelved": bool(s["shelved"]),
             "total": s["n_total"], "have": s["n_have"], "seen": s["n_seen"]}
            for g in db.by_creator(db.sources(self.conn))
            for s in ([g["channel"]] if g["channel"] else []) + g["items"]
        ]
        colls = [
            {"id": c["id"], "name": c["name"], "total": c["n_total"],
             "have": c["n_have"], "seen": c["n_seen"]}
            for c in db.collections(self.conn)
        ]
        # A playlist or collection is shown in its own order, so the UI must not
        # re-sort it; say so explicitly rather than making the page guess. Under
        # an explicit sort the position numbers would be fiction, so drop them.
        is_playlist = False
        if source:
            row = self.conn.execute(
                "SELECT kind FROM sources WHERE id = ?", (source,)).fetchone()
            is_playlist = bool(row and row["kind"] == "playlist")
        ordered = bool(collection) or is_playlist
        # "default" means something different in every view, so name the thing
        # it actually does here -- otherwise the author's running order reads
        # as an anonymous fallback and nobody finds their way back to it.
        sort_labels = {k: v[0] for k, v in db.SORTS.items()}
        if collection:
            sort_labels["default"] = "Collection order (yours)"
        elif is_playlist:
            sort_labels["default"] = "Playlist order (the author's)"
        return self._json({
            "videos": [row_to_json(r) for r in rows],
            "sources": srcs,
            "collections": colls,
            "ordered": ordered and sort == "default",
            "sort": sort,
            "sorts": [{"key": k, "label": sort_labels[k]} for k in db.SORTS],
            "stats": db.stats(self.conn),
            "jobs": self._jobs(),
            # One row per creator, not per video: the player looks the current
            # video's channel up in here when it lays out the Toggl mount.
            "toggl": db.toggl_map(self.conn),
            "toggl_channels": db.toggl_channels(self.conn),
        })

    def _toggl_status(self):
        """Whether the button should be there at all, and what is running."""
        if not tg.configured(self.cfg):
            return self._json({"configured": False, "running": {}})
        try:
            return self._json({"configured": True,
                               "running": tg.as_json(tg.current(self.cfg))})
        except tg.TogglError as exc:
            # Configured but unreachable is worth saying out loud rather than
            # quietly looking the same as "not set up".
            return self._json({"configured": True, "running": {}, "error": str(exc)})

    def _action(self, action, vid):
        # Read the body even when refusing: left unread on a kept-alive
        # connection, it would be parsed as the start of the next request.
        body = self._body()
        row = db.get_video(self.conn, vid)
        if not row:
            return self._fail(404, "unknown video")
        if action == "get":
            job = self.server.dl.enqueue(vid, row["title"], bool(body.get("audio")))
            return self._json({"ok": True, "job": job.as_dict()})
        if action == "star":
            val = 0 if row["starred"] else 1
            db.set_flag(self.conn, vid, "starred", val)
            return self._json({"ok": True, "starred": bool(val)})
        if action == "watched":
            val = int(body.get("value", 0 if row["watched"] else 1))
            db.set_flag(self.conn, vid, "watched", val)
            return self._json({"ok": True, "watched": bool(val)})
        if action == "hidden":
            # Unhiding by hand writes 0, which sync then leaves alone -- a
            # private video you insist on seeing stays seen.
            val = int(body.get("value", 0 if row["hidden"] else 1))
            db.set_flag(self.conn, vid, "hidden", val)
            return self._json({"ok": True, "hidden": bool(val)})
        if action == "marks":
            # One endpoint, three verbs: add {t, note}, note {id, note}, drop {id}.
            if "t" in body:
                db.add_mark(self.conn, vid, float(body["t"]), body.get("note", ""))
            elif body.get("drop"):
                db.delete_mark(self.conn, vid, body["drop"])
            elif "id" in body:
                db.edit_mark(self.conn, vid, body["id"], body.get("note", ""))
            else:
                return self._fail(400, "say t, id or drop")
            return self._json({"ok": True, "marks": db.marks(self.conn, vid)})
        if action == "progress":
            db.set_flag(self.conn, vid, "progress", float(body.get("value", 0)))
            return self._json({"ok": True})
        if action == "collect":
            cid = body.get("collection")
            if cid is None:
                return self._fail(400, "collection required")
            if body.get("remove"):
                db.collection_remove(self.conn, int(cid), vid)
            else:
                db.collection_add(self.conn, int(cid), vid)
            return self._json({"ok": True, "collections": [
                {"id": c["id"], "name": c["name"]}
                for c in db.collections_for(self.conn, vid)]})
        if action == "remove":
            if row["downloaded_path"]:
                p = Path(row["downloaded_path"])
                for extra in ytdlp.sidecar_subs(p):
                    extra[1].unlink(missing_ok=True)
                p.unlink(missing_ok=True)
            db.clear_downloaded(self.conn, vid)
            return self._json({"ok": True})
        return self._fail(404, "unknown action")

    def _thumb(self, vid):
        if not _ID_RE.match(vid):
            return self._fail(400, "bad id")
        dest = config.THUMB_DIR / f"{vid}.jpg"
        # Lazily cached: the first view pulls it, every later view is local.
        if not dest.exists() and not ytdlp.fetch_thumb(vid, dest):
            return self._send(200, PLACEHOLDER, "image/svg+xml",
                              {"Cache-Control": "no-store"})
        return self._serve_file(dest, "image/jpeg", cache="public, max-age=604800")

    def _media(self, vid):
        if not _ID_RE.match(vid):
            return self._fail(400, "bad id")
        row = db.get_video(self.conn, vid)
        if not row or not row["downloaded_path"]:
            return self._fail(404, "not downloaded")
        path = Path(row["downloaded_path"])
        if not path.exists():
            db.clear_downloaded(self.conn, vid)
            return self._fail(404, "file missing from disk")
        ctype = mimetypes.guess_type(path.name)[0] or "video/mp4"
        return self._serve_file(path, ctype, ranges=True)

    # --- streaming without downloading -----------------------------------
    #
    # The page plays a stream through MediaSource: it reads each track's index,
    # then asks for the byte ranges it needs. Every one of those requests comes
    # here and is relayed to YouTube, so the page itself stays sealed.

    def _stream_meta(self, vid):
        if not _ID_RE.match(vid):
            return self._fail(400, "bad id")
        try:
            info = self.server.streams.get(vid)
        except ytdlp.YtdlpError as exc:
            return self._fail(502, str(exc))
        if db.get_video(self.conn, vid):
            db.set_chapters(self.conn, vid, info["chapters"])
            # Catalogue listings often lack a length, and without one a
            # streamed video's card cannot show how far in you are.
            db.fill_duration(self.conn, vid, info["duration"])
        return self._json({"duration": info["duration"],
                           "chapters": info["chapters"],
                           "videos": {h: t["mime"] for h, t in info["videos"].items()},
                           "default": info["default"],
                           "audio": info["audio"]["mime"]})

    def _stream(self, rest):
        # /stream/<id>/audio, or /stream/<id>/video/<height>
        vid, _, kind = rest.partition("/")
        kind, _, height = kind.partition("/")
        if (not _ID_RE.match(vid) or kind not in ("video", "audio")
                or (kind == "video") != height.isdigit()):
            return self._fail(400, "bad stream")
        rng = self.headers.get("Range") or ""
        if not _RANGE_RE.match(rng):
            return self._fail(400, "a byte range is required")
        for fresh in (False, True):
            try:
                info = self.server.streams.get(vid, fresh=fresh)
            except ytdlp.YtdlpError as exc:
                return self._fail(502, str(exc))
            track = info["audio"] if kind == "audio" else info["videos"].get(int(height))
            if not track:
                return self._fail(404, "no such quality")
            req = urllib.request.Request(track["url"],
                                         headers={**track["headers"], "Range": rng})
            try:
                resp = urllib.request.urlopen(req, timeout=30)
                break
            except urllib.error.HTTPError as exc:
                # 403 is what an expired signature looks like: resolve again once.
                if exc.code != 403 or fresh:
                    return self._fail(502, f"YouTube answered {exc.code}")
        with resp:
            self.send_response(resp.status)
            self.send_header("Content-Type", "video/mp4" if kind == "video" else "audio/mp4")
            for h in ("Content-Length", "Content-Range"):
                if resp.headers.get(h):
                    self.send_header(h, resp.headers[h])
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command == "HEAD":
                return
            while buf := resp.read(CHUNK):
                self.wfile.write(buf)

    def _chapters(self, vid):
        """Looked up once per video, the first time its player opens."""
        if not _ID_RE.match(vid):
            return self._fail(400, "bad id")
        row = db.get_video(self.conn, vid)
        if not row:
            return self._fail(404, "unknown video")
        if row["chapters"] is not None:
            return self._json({"chapters": json.loads(row["chapters"])})
        try:
            found = ytdlp.fetch_info(self.cfg, vid)["chapters"]
        except ytdlp.YtdlpError:
            # Offline or rate-limited: say none for now, and ask again next time.
            return self._json({"chapters": []})
        db.set_chapters(self.conn, vid, found)
        return self._json({"chapters": found})

    def _sub_langs(self, vid):
        """Queried lazily when the player opens, so listing stays glob-free."""
        if not _ID_RE.match(vid):
            return self._fail(400, "bad id")
        row = db.get_video(self.conn, vid)
        if not row or not row["downloaded_path"]:
            return self._json({"langs": []})
        langs = [l for l, _ in ytdlp.sidecar_subs(Path(row["downloaded_path"]))]
        return self._json({"langs": langs})

    def _subs(self, rest):
        vid, _, lang = rest.partition("/")
        if not _ID_RE.match(vid):
            return self._fail(400, "bad id")
        row = db.get_video(self.conn, vid)
        if not row or not row["downloaded_path"]:
            return self._fail(404, "not downloaded")
        for have_lang, p in ytdlp.sidecar_subs(Path(row["downloaded_path"])):
            if have_lang == lang:
                return self._serve_file(p, "text/vtt; charset=utf-8")
        return self._fail(404, "no such subtitle track")

    # --- file streaming with Range support (seeking needs this) -----------

    def _serve_file(self, path: Path, ctype: str, ranges=False, cache=None):
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        headers = {"Accept-Ranges": "bytes" if ranges else "none"}
        if cache:
            headers["Cache-Control"] = cache

        if ranges:
            m = _RANGE_RE.match(self.headers.get("Range") or "")
            if m:
                lo, hi = m.group(1), m.group(2)
                if lo:
                    start = int(lo)
                    end = int(hi) if hi else size - 1
                elif hi:  # suffix range: last N bytes
                    start = max(0, size - int(hi))
                if start >= size:
                    return self._send(416, b"", ctype,
                                      {"Content-Range": f"bytes */{size}"})
                end = min(end, size - 1)
                status = 206
                headers["Content-Range"] = f"bytes {start}-{end}/{size}"

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as fh:
            fh.seek(start)
            left = length
            while left > 0:
                buf = fh.read(min(CHUNK, left))
                if not buf:
                    break
                self.wfile.write(buf)
                left -= len(buf)


PLACEHOLDER = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180">'
    '<rect width="320" height="180" fill="#2a2a30"/>'
    '<text x="160" y="96" fill="#6b6b78" font-family="sans-serif" font-size="14"'
    ' text-anchor="middle">no thumbnail</text></svg>'
).encode()


def serve(cfg, port=None, host="127.0.0.1", verbose=False):
    port = int(port or cfg["port"])
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    httpd.dl = Downloader(cfg, config.media_dir(cfg))
    httpd.cat = Cataloguer(cfg)
    httpd.streams = Streams(cfg)
    httpd.verbose = verbose
    return httpd
