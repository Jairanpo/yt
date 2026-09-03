"""Localhost web UI. Stdlib only; no network calls from the browser."""
import json
import mimetypes
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ytlocal import config, db, ytdlp
from ytlocal.jobs import Downloader
from ytlocal.ui import PAGE

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK = 256 * 1024


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
        "size": r["filesize"],
        "starred": bool(r["starred"]),
        "watched": bool(r["watched"]),
        "progress": r["progress"],
    }


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
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; "
                         "media-src 'self'; style-src 'self' 'unsafe-inline'; "
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
            if path == "/api/jobs":
                return self._json({"jobs": self.server.dl.snapshot()})
            if path.startswith("/thumb/"):
                return self._thumb(path[7:])
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
            if len(parts) == 3 and parts[0] == "api":
                action, vid = parts[1], parts[2]
                if not _ID_RE.match(vid):
                    return self._fail(400, "bad video id")
                return self._action(action, vid)
            if url.path == "/api/collections":
                body = self._body()
                name = (body.get("name") or "").strip()
                if not name:
                    return self._fail(400, "name required")
                c = db.create_collection(self.conn, name)
                return self._json({"ok": True, "id": c["id"], "name": c["name"]})
            if url.path == "/api/jobs/clear":
                self.server.dl.forget_finished()
                return self._json({"ok": True})
            return self._fail(404, "not found")
        except ConnectionError:
            self.close_connection = True
        except Exception as exc:  # noqa: BLE001
            self._fail(500, str(exc))

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
        collection = one("collection") or None
        rows = db.query_videos(
            self.conn,
            source=source,
            collection=int(collection) if collection else None,
            q=(one("q") or "").strip() or None,
            have=have,
            starred=one("starred") == "1",
            unwatched=one("unwatched") == "1",
            limit=int(one("limit", "300")),
            offset=int(one("offset", "0")),
        )
        srcs = [
            {"id": s["id"], "kind": s["kind"],
             "name": s["name"] or s["handle"] or s["url"],
             "owner": s["owner"], "total": s["n_total"], "have": s["n_have"]}
            for s in db.sources(self.conn)
        ]
        colls = [
            {"id": c["id"], "name": c["name"], "total": c["n_total"],
             "have": c["n_have"]}
            for c in db.collections(self.conn)
        ]
        # A playlist or collection is shown in its own order, so the UI must not
        # re-sort it; say so explicitly rather than making the page guess.
        ordered = bool(collection)
        if source and not ordered:
            row = self.conn.execute(
                "SELECT kind FROM sources WHERE id = ?", (source,)).fetchone()
            ordered = bool(row and row["kind"] == "playlist")
        return self._json({
            "videos": [row_to_json(r) for r in rows],
            "sources": srcs,
            "collections": colls,
            "ordered": ordered,
            "stats": db.stats(self.conn),
            "jobs": self.server.dl.snapshot(),
        })

    def _action(self, action, vid):
        row = db.get_video(self.conn, vid)
        if not row:
            return self._fail(404, "unknown video")
        body = self._body()
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
    httpd.verbose = verbose
    return httpd
