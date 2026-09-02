"""SQLite catalog. One row per known video; downloaded_path is NULL until fetched."""
import sqlite3
import time
from pathlib import Path

from ytlocal import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id          TEXT PRIMARY KEY,   -- yt-dlp channel_id, or the URL if unresolved
    handle      TEXT,               -- @handle when we know it
    name        TEXT,
    url         TEXT NOT NULL,      -- canonical /videos tab we sync from
    added_at    INTEGER NOT NULL,
    last_sync   INTEGER
);

CREATE TABLE IF NOT EXISTS videos (
    id              TEXT PRIMARY KEY,   -- 11-char YouTube id
    channel_id      TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    description     TEXT,
    duration        INTEGER,            -- seconds, NULL if unknown
    upload_date     TEXT,               -- YYYY-MM-DD, NULL until we know it
    date_approx     INTEGER NOT NULL DEFAULT 0,  -- 1 = month-precision guess only
    position        INTEGER NOT NULL,   -- 0 = newest in the channel listing
    first_seen      INTEGER NOT NULL,
    downloaded_path TEXT,
    downloaded_at   INTEGER,
    filesize        INTEGER,
    starred         INTEGER NOT NULL DEFAULT 0,
    watched         INTEGER NOT NULL DEFAULT 0,
    watched_at      INTEGER,
    progress        REAL NOT NULL DEFAULT 0  -- playback position in seconds
);

CREATE INDEX IF NOT EXISTS idx_videos_channel  ON videos(channel_id, position);
CREATE INDEX IF NOT EXISTS idx_videos_have     ON videos(downloaded_path);
CREATE INDEX IF NOT EXISTS idx_videos_starred  ON videos(starred);
"""


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(videos)")}
    if "date_approx" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN date_approx INTEGER NOT NULL DEFAULT 0")
        conn.commit()


def now() -> int:
    return int(time.time())


# --- channels -------------------------------------------------------------

def upsert_channel(conn, cid: str, url: str, name=None, handle=None) -> None:
    conn.execute(
        """INSERT INTO channels (id, handle, name, url, added_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               name   = COALESCE(excluded.name, channels.name),
               handle = COALESCE(excluded.handle, channels.handle),
               url    = excluded.url""",
        (cid, handle, name, url, now()),
    )
    conn.commit()


def channels(conn) -> list:
    return conn.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM videos v WHERE v.channel_id = c.id) AS n_total,
                  (SELECT COUNT(*) FROM videos v WHERE v.channel_id = c.id
                                              AND v.downloaded_path IS NOT NULL) AS n_have
             FROM channels c ORDER BY COALESCE(c.name, c.url)"""
    ).fetchall()


def find_channel(conn, needle: str):
    """Resolve a user-typed channel reference to a row, or None."""
    n = needle.strip().lstrip("@").lower()
    return conn.execute(
        """SELECT * FROM channels
            WHERE lower(id) = ? OR lower(handle) = ? OR lower(name) = ?
               OR lower(handle) LIKE ? OR lower(name) LIKE ? OR lower(url) LIKE ?
            ORDER BY length(COALESCE(name, url)) LIMIT 1""",
        (n, n, n, f"%{n}%", f"%{n}%", f"%{n}%"),
    ).fetchone()


def mark_synced(conn, cid: str) -> None:
    conn.execute("UPDATE channels SET last_sync = ? WHERE id = ?", (now(), cid))
    conn.commit()


def delete_channel(conn, cid: str) -> None:
    conn.execute("DELETE FROM videos WHERE channel_id = ?", (cid,))
    conn.execute("DELETE FROM channels WHERE id = ?", (cid,))
    conn.commit()


# --- videos ---------------------------------------------------------------

def upsert_videos(conn, cid: str, entries: list) -> tuple:
    """entries: dicts with id/title/duration/position/description/upload_date.

    Returns (n_new, n_seen). Existing rows keep their download + watch state;
    only catalog fields are refreshed.
    """
    known = {r[0] for r in conn.execute("SELECT id FROM videos WHERE channel_id = ?", (cid,))}
    new = 0
    for e in entries:
        if e["id"] not in known:
            new += 1
        conn.execute(
            """INSERT INTO videos (id, channel_id, title, description, duration,
                                   upload_date, date_approx, position, first_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   title       = excluded.title,
                   description = COALESCE(excluded.description, videos.description),
                   duration    = COALESCE(excluded.duration, videos.duration),
                   -- never let a fresh approximation overwrite an exact date
                   upload_date = CASE WHEN videos.date_approx = 0 AND videos.upload_date
                                        IS NOT NULL THEN videos.upload_date
                                      ELSE COALESCE(excluded.upload_date, videos.upload_date)
                                 END,
                   date_approx = CASE WHEN videos.date_approx = 0 AND videos.upload_date
                                        IS NOT NULL THEN 0 ELSE excluded.date_approx END,
                   position    = excluded.position""",
            (e["id"], cid, e["title"], e.get("description"), e.get("duration"),
             e.get("upload_date"), e.get("date_approx", 0), e["position"], now()),
        )
    conn.commit()
    return new, len(entries)


def get_video(conn, vid: str):
    return conn.execute(
        """SELECT v.*, c.name AS channel_name, c.handle AS channel_handle
             FROM videos v JOIN channels c ON c.id = v.channel_id
            WHERE v.id = ?""",
        (vid,),
    ).fetchone()


def query_videos(conn, channel=None, q=None, have=None, starred=None,
                 unwatched=False, limit=None, offset=0) -> list:
    where, args = [], []
    if channel:
        where.append("v.channel_id = ?")
        args.append(channel)
    if q:
        where.append("(v.title LIKE ? OR COALESCE(v.description,'') LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    if have is True:
        where.append("v.downloaded_path IS NOT NULL")
    elif have is False:
        where.append("v.downloaded_path IS NULL")
    if starred:
        where.append("v.starred = 1")
    if unwatched:
        where.append("v.watched = 0")

    sql = """SELECT v.*, c.name AS channel_name, c.handle AS channel_handle
               FROM videos v JOIN channels c ON c.id = v.channel_id"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    # Rank exact-ish title hits first when searching, then newest-first. Channel
    # listings arrive reverse-chronological, so position stands in for date when
    # upload_date is unknown (flat sync often omits it).
    if q:
        sql += " ORDER BY (CASE WHEN v.title LIKE ? THEN 0 ELSE 1 END),"
        args.append(f"%{q}%")
    else:
        sql += " ORDER BY"
    sql += " COALESCE(v.upload_date, '') DESC, v.position ASC"
    if limit:
        sql += " LIMIT ? OFFSET ?"
        args += [int(limit), int(offset)]
    return conn.execute(sql, args).fetchall()


def resolve_video(conn, needle: str, channel=None):
    """Return (row, candidates). Exact id wins; otherwise search by title."""
    needle = needle.strip()
    if len(needle) == 11 and all(c.isalnum() or c in "-_" for c in needle):
        row = get_video(conn, needle)
        if row:
            return row, []
    hits = query_videos(conn, channel=channel, q=needle, limit=25)
    if len(hits) == 1:
        return hits[0], []
    return None, hits


def set_downloaded(conn, vid: str, path, size, upload_date=None, description=None,
                   duration=None) -> None:
    conn.execute(
        """UPDATE videos SET downloaded_path = ?, downloaded_at = ?, filesize = ?,
                             upload_date = COALESCE(?, upload_date),
                             date_approx = CASE WHEN ? IS NOT NULL THEN 0
                                                ELSE date_approx END,
                             description = COALESCE(?, description),
                             duration    = COALESCE(?, duration)
            WHERE id = ?""",
        (str(path) if path else None, now() if path else None, size,
         upload_date, upload_date, description, duration, vid),
    )
    conn.commit()


def clear_downloaded(conn, vid: str) -> None:
    conn.execute(
        "UPDATE videos SET downloaded_path = NULL, downloaded_at = NULL, filesize = NULL"
        " WHERE id = ?", (vid,))
    conn.commit()


def set_flag(conn, vid: str, field: str, value) -> None:
    assert field in {"starred", "watched", "progress"}
    extra = ", watched_at = ?" if field == "watched" else ""
    args = [value, now(), vid] if field == "watched" else [value, vid]
    conn.execute(f"UPDATE videos SET {field} = ?{extra} WHERE id = ?", args)
    conn.commit()


def stats(conn) -> dict:
    row = conn.execute(
        """SELECT COUNT(*) AS total,
                  SUM(downloaded_path IS NOT NULL) AS have,
                  SUM(COALESCE(filesize, 0))       AS bytes,
                  SUM(starred)                     AS starred,
                  SUM(downloaded_path IS NOT NULL AND watched = 0) AS unwatched
             FROM videos"""
    ).fetchone()
    d = {k: (row[k] or 0) for k in row.keys()}
    d["channels"] = conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
    return d


def prune_missing(conn) -> int:
    """Clear download state for files that vanished from disk."""
    gone = 0
    for row in conn.execute(
        "SELECT id, downloaded_path FROM videos WHERE downloaded_path IS NOT NULL"
    ).fetchall():
        if not Path(row["downloaded_path"]).exists():
            clear_downloaded(conn, row["id"])
            gone += 1
    return gone
