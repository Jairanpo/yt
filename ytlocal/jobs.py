"""Background download queue shared by the CLI and the web UI."""
import queue
import threading
import traceback

from ytlocal import db, ytdlp


class Job:
    __slots__ = ("vid", "title", "state", "fraction", "detail", "error")

    def __init__(self, vid, title):
        self.vid, self.title = vid, title
        self.state = "queued"     # queued | running | done | error
        self.fraction = None
        self.detail = ""
        self.error = None

    def as_dict(self):
        return {
            "id": self.vid, "title": self.title, "state": self.state,
            "fraction": self.fraction, "detail": self.detail, "error": self.error,
        }


class Downloader:
    """A small worker pool. Two workers keeps the pipe busy without hammering."""

    def __init__(self, cfg, media_dir, workers=2):
        self.cfg, self.media_dir = cfg, media_dir
        self.jobs = {}
        self.lock = threading.Lock()
        self.q = queue.Queue()
        for i in range(workers):
            threading.Thread(target=self._worker, name=f"dl-{i}", daemon=True).start()

    def enqueue(self, vid, title, audio_only=False):
        with self.lock:
            existing = self.jobs.get(vid)
            if existing and existing.state in ("queued", "running"):
                return existing
            job = Job(vid, title)
            self.jobs[vid] = job
        self.q.put((job, audio_only))
        return job

    def snapshot(self):
        with self.lock:
            return [j.as_dict() for j in self.jobs.values()]

    def active(self):
        with self.lock:
            return [j.as_dict() for j in self.jobs.values()
                    if j.state in ("queued", "running")]

    def forget_finished(self):
        with self.lock:
            for vid in [k for k, j in self.jobs.items() if j.state in ("done", "error")]:
                del self.jobs[vid]

    def forget(self, vid):
        """Drop one finished job. Running jobs stay: the UI hides them instead."""
        with self.lock:
            job = self.jobs.get(vid)
            if job is None or job.state in ("queued", "running"):
                return False
            del self.jobs[vid]
            return True

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
