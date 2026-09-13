"""Background queues shared by the CLI and the web UI: downloads, and adding
a source from the web page.
"""
import queue
import threading
import traceback

from ytlocal import db, ytdlp


class Job:
    __slots__ = ("vid", "title", "kind", "state", "fraction", "detail", "error",
                 "result")

    def __init__(self, vid, title, kind="download"):
        self.vid, self.title, self.kind = vid, title, kind
        self.state = "queued"     # queued | running | done | error
        self.fraction = None
        self.detail = ""
        self.error = None
        # Whatever the finished job wants to hand back -- for a catalog job the
        # source it created, so the page can jump straight into it.
        self.result = None

    def as_dict(self):
        return {
            "id": self.vid, "title": self.title, "kind": self.kind,
            "state": self.state, "fraction": self.fraction, "detail": self.detail,
            "error": self.error, "result": self.result,
        }


class _Queue:
    """The bookkeeping both queues share: a job registry the page can poll.

    Jobs are kept after they finish so the card can say how it went, and are
    dropped when the user dismisses one or asks to clear them.
    """

    def __init__(self, workers, name):
        self.jobs = {}
        self.lock = threading.Lock()
        self.q = queue.Queue()
        for i in range(workers):
            threading.Thread(target=self._worker, name=f"{name}-{i}",
                             daemon=True).start()

    def _claim(self, key, title, kind):
        """Register a job, or hand back the live one already doing that work."""
        with self.lock:
            existing = self.jobs.get(key)
            if existing and existing.state in ("queued", "running"):
                return existing, False
            job = Job(key, title, kind)
            self.jobs[key] = job
            return job, True

    def snapshot(self):
        with self.lock:
            return [j.as_dict() for j in self.jobs.values()]

    def active(self):
        with self.lock:
            return [j.as_dict() for j in self.jobs.values()
                    if j.state in ("queued", "running")]

    def forget_finished(self):
        with self.lock:
            for key in [k for k, j in self.jobs.items()
                        if j.state in ("done", "error")]:
                del self.jobs[key]

    def forget(self, key):
        """Drop one finished job. Running jobs stay: the UI hides them instead."""
        with self.lock:
            job = self.jobs.get(key)
            if job is None or job.state in ("queued", "running"):
                return False
            del self.jobs[key]
            return True

    def _worker(self):
        raise NotImplementedError


class Downloader(_Queue):
    """A small worker pool. Two workers keeps the pipe busy without hammering."""

    def __init__(self, cfg, media_dir, workers=2):
        self.cfg, self.media_dir = cfg, media_dir
        super().__init__(workers, "dl")

    def enqueue(self, vid, title, audio_only=False):
        job, fresh = self._claim(vid, title, "download")
        if fresh:
            self.q.put((job, audio_only))
        return job

    def _worker(self):
        while True:
            job, audio_only = self.q.get()
            conn = None
            try:
                job.state, job.detail = "running", "starting"

                def progress(frac, text, _job=job):
                    _job.fraction, _job.detail = frac, text

                res = ytdlp.download(self.cfg, job.vid, self.media_dir,
                                     audio_only=audio_only, on_progress=progress)
                size = res["path"].stat().st_size if res["path"].exists() else None
                # Each worker opens its own connection; sqlite objects are not
                # safe to share across threads.
                conn = db.connect()
                db.set_downloaded(conn, job.vid, res["path"], size,
                                  res.get("upload_date"), res.get("description"),
                                  res.get("duration"))
                job.state, job.fraction, job.detail = "done", 1.0, "done"
            except Exception as exc:  # noqa: BLE001 - surfaced to the user via the job
                job.state = "error"
                job.error = str(exc) or traceback.format_exc(limit=2)
                job.detail = "failed"
            finally:
                if conn is not None:
                    conn.close()
                self.q.task_done()


class Cataloguer(_Queue):
    """Tracks a channel or playlist asked for from the web page.

    One worker, unlike downloads: cataloguing is a handful of metadata requests
    that finish in seconds, and two of them running at once would only race
    each other over the same rows.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        super().__init__(1, "catalog")

    def enqueue(self, ref, limit=None):
        ref = ref.strip()
        # Keyed on what was asked for, so double-clicking Add joins the job
        # already running rather than starting a second pass over it.
        job, fresh = self._claim(f"src:{ref.lower()}", ref, "source")
        if fresh:
            self.q.put((job, ref, limit))
        return job

    def _worker(self):
        while True:
            job, ref, limit = self.q.get()
            conn = None
            try:
                job.state, job.detail = "running", "resolving…"
                url = ytdlp.source_url(ref)
                meta, entries = ytdlp.sync_source(self.cfg, url, limit=limit)
                job.detail = f"{len(entries)} found — filing"
                sid = meta["source_id"]
                conn = db.connect()
                db.upsert_source(conn, sid, url, meta.get("kind") or ytdlp.url_kind(url),
                                 meta.get("name"), meta.get("handle"),
                                 meta.get("owner"))
                new, total, _ = db.upsert_videos(conn, sid, entries,
                                                 prune=limit is None)
                db.mark_synced(conn, sid)
                # Now that it has a name, the card can stop calling it by
                # whatever was typed into the box.
                job.title = meta.get("name") or meta.get("handle") or sid
                job.result = {"source_id": sid, "kind": meta.get("kind"),
                              "name": job.title, "new": new, "total": total}
                job.state, job.fraction = "done", 1.0
                job.detail = (f"{total} catalogued · {new} new" if new
                              else f"{total} catalogued · nothing new")
            except Exception as exc:  # noqa: BLE001 - surfaced to the user via the job
                job.state = "error"
                job.error = str(exc) or traceback.format_exc(limit=2)
                job.detail = "failed"
            finally:
                if conn is not None:
                    conn.close()
                self.q.task_done()
