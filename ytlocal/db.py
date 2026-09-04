"""SQLite catalog.

A *source* is something we sync from: a channel or a playlist. A *collection*
is a local grouping you build yourself. Both are many-to-many against videos --
one video can sit in a channel, two playlists and a collection at once, which a
single foreign key on videos could not express.
"""
import re
import sqlite3
import time
from pathlib import Path

from ytlocal import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id          TEXT PRIMARY KEY,   -- channel id (UC...) or playlist id (PL...)
    kind        TEXT NOT NULL DEFAULT 'channel',   -- 'channel' | 'playlist'
    handle      TEXT,               -- @handle for channels
    name        TEXT,
    owner       TEXT,               -- for playlists: the channel that owns it
    url         TEXT NOT NULL,
    added_at    INTEGER NOT NULL,
    last_sync   INTEGER
);

CREATE TABLE IF NOT EXISTS videos (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    description     TEXT,
    duration        INTEGER,
    upload_date     TEXT,
    date_approx     INTEGER NOT NULL DEFAULT 0,
    first_seen      INTEGER NOT NULL,
    downloaded_path TEXT,
    downloaded_at   INTEGER,
    filesize        INTEGER,
    starred         INTEGER NOT NULL DEFAULT 0,
    watched         INTEGER NOT NULL DEFAULT 0,
    watched_at      INTEGER,
    progress        REAL NOT NULL DEFAULT 0,
    -- private, deleted or region-locked: YouTube lists the slot but gives no
    -- title, so there is nothing to show and nothing to fetch. Maintained by
    -- sync, and cleared again if the video ever comes back.
    unavailable     INTEGER NOT NULL DEFAULT 0,
    -- 0 visible · 1 hidden by you · 2 hidden by sync for being unavailable.
    -- Keeping those apart is what lets sync tidy up after itself without ever
    -- overruling a call you made by hand.
    hidden          INTEGER NOT NULL DEFAULT 0
);

-- position is the video's index within that source. For a playlist this is
-- the curated order the author chose, which is the whole point of a playlist.
CREATE TABLE IF NOT EXISTS source_videos (
    source_id  TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    video_id   TEXT NOT NULL REFERENCES videos(id)  ON DELETE CASCADE,
    position   INTEGER NOT NULL,
    PRIMARY KEY (source_id, video_id)
);

CREATE TABLE IF NOT EXISTS collections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_items (
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    video_id      TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    rank          INTEGER NOT NULL,
    added_at      INTEGER NOT NULL,
    PRIMARY KEY (collection_id, video_id)
);

-- One remembered sort per view. scope is 'global', 'source:<id>' or
-- 'collection:<id>'; a view with no row of its own falls back to global.
CREATE TABLE IF NOT EXISTS view_prefs (
    scope   TEXT PRIMARY KEY,
    sort    TEXT NOT NULL,
    set_at  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sv_source  ON source_videos(source_id, position);
CREATE INDEX IF NOT EXISTS idx_sv_video   ON source_videos(video_id);
CREATE INDEX IF NOT EXISTS idx_ci_coll    ON collection_items(collection_id, rank);
CREATE INDEX IF NOT EXISTS idx_videos_have ON videos(downloaded_path);
"""

PLAYLIST_RE = re.compile(r"[?&]list=([A-Za-z0-9_-]+)")

# Sort keys, in the order a dropdown should offer them. "default" means the
# order the view was built for -- curated for a playlist or collection,
# newest-first everywhere else -- and is the only one that numbers its rows.
# Every explicit sort puts unknowns (no date, no duration) last rather than
# letting NULL sort first, and breaks ties on id so paging stays stable.
SORTS = {
    "default":  ("This view's own order", None),
    "newest":   ("Newest first",  "(v.upload_date IS NULL), v.upload_date DESC"),
    "oldest":   ("Oldest first",  "(v.upload_date IS NULL), v.upload_date ASC"),
    "added":    ("Recently added", "v.first_seen DESC"),
    "title":    ("Title A\u2013Z", "v.title COLLATE NOCASE ASC"),
    "longest":  ("Longest first", "(v.duration IS NULL), v.duration DESC"),
    "shortest": ("Shortest first", "(v.duration IS NULL), v.duration ASC"),
}
SORT_KEYS = list(SORTS)


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    _migrate_legacy(conn)          # manages the foreign_keys pragma itself
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _add_missing_columns(conn)
    _repair_playlist_ids(conn)
    return conn


def now() -> int:
    return int(time.time())


# --- migration ------------------------------------------------------------

def _tables(conn) -> set:
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _migrate_legacy(conn) -> None:
    """Lift a pre-collections catalog (channels + videos.channel_id) forward.

    Download state, stars and watch progress are keyed on video id, so they
    survive untouched; only the shape of the source relation changes.
    """
    tables = _tables(conn)
    if "channels" not in tables or "sources" in tables:
        return
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(videos)")}
    # Rebuilding `videos` means dropping it, and DROP TABLE runs an implicit
    # DELETE: with foreign_keys ON that cascades into source_videos and erases
    # the mapping this function just built. Off for the duration.
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(SCHEMA)

    conn.execute(
        """INSERT OR IGNORE INTO sources (id, kind, handle, name, url, added_at, last_sync)
           SELECT id,
                  CASE WHEN url LIKE '%list=%' THEN 'playlist' ELSE 'channel' END,
                  handle, name, url, added_at, last_sync
             FROM channels""")
    if "channel_id" in cols:
        conn.execute(
            """INSERT OR IGNORE INTO source_videos (source_id, video_id, position)
               SELECT channel_id, id, position FROM videos""")
        # Rebuild videos without the single-source columns.
        conn.executescript("""
            CREATE TABLE videos_new (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT,
                duration INTEGER, upload_date TEXT,
                date_approx INTEGER NOT NULL DEFAULT 0, first_seen INTEGER NOT NULL,
                downloaded_path TEXT, downloaded_at INTEGER, filesize INTEGER,
                starred INTEGER NOT NULL DEFAULT 0, watched INTEGER NOT NULL DEFAULT 0,
                watched_at INTEGER, progress REAL NOT NULL DEFAULT 0);
        """)
        approx = "date_approx" if "date_approx" in cols else "0"
        conn.execute(f"""
            INSERT INTO videos_new SELECT id, title, description, duration,
                   upload_date, {approx}, first_seen, downloaded_path, downloaded_at,
                   filesize, starred, watched, watched_at, progress FROM videos""")
        conn.execute("DROP TABLE videos")
        conn.execute("ALTER TABLE videos_new RENAME TO videos")
    conn.execute("DROP TABLE channels")
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    # Anything the rebuild orphaned would show up here; nothing should.
    bad = conn.execute("PRAGMA foreign_key_check").fetchall()
    if bad:
        raise sqlite3.IntegrityError(
            f"catalog migration left {len(bad)} orphaned row(s); "
            f"database untouched at {config.DB_PATH}")


def _add_missing_columns(conn) -> None:
    """CREATE TABLE IF NOT EXISTS never adds a column to a catalog that exists."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(videos)")}
    for col in ("unavailable", "hidden"):
        if col not in have:
            conn.execute(
                f"ALTER TABLE videos ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
    if "unavailable" not in have:
        # A pre-existing catalog stored these with the id standing in for the
        # missing title. Name them for what they are on the way through, and
        # hide them the way a sync would have.
        conn.execute(
            "UPDATE videos SET unavailable = 1, hidden = 2 WHERE title = id")
    conn.commit()


def _repair_playlist_ids(conn) -> None:
    """Re-key playlist sources that were filed under their owning channel's id.

    Flat playlist entries expose playlist_channel_id (the *channel* that owns
    the playlist), so an earlier version keyed playlists by it -- which merged
    a playlist into its own channel. Recover the real id from the URL.
    """
    todo = []
    for row in conn.execute(
        "SELECT id, url FROM sources WHERE url LIKE '%list=%'").fetchall():
        m = PLAYLIST_RE.search(row["url"])
        if not m or m.group(1) == row["id"]:
            continue
        pid = m.group(1)
        if conn.execute("SELECT 1 FROM sources WHERE id = ?", (pid,)).fetchone():
            continue          # a correctly-keyed row already exists; leave it
        todo.append((row["id"], pid))
    if not todo:
        return
    # The parent id and its children have to move together. Re-keying the
    # source first would momentarily orphan source_videos and trip the
    # constraint, so enforcement is off across the pair of updates.
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for old_id, pid in todo:
            conn.execute("UPDATE sources SET id = ?, kind = 'playlist' WHERE id = ?",
                         (pid, old_id))
            conn.execute("UPDATE source_videos SET source_id = ? WHERE source_id = ?",
                         (pid, old_id))
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


# --- sources --------------------------------------------------------------

def upsert_source(conn, sid, url, kind="channel", name=None, handle=None,
                  owner=None) -> None:
    conn.execute(
        """INSERT INTO sources (id, kind, handle, name, owner, url, added_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               kind   = excluded.kind,
               name   = COALESCE(excluded.name, sources.name),
               handle = COALESCE(excluded.handle, sources.handle),
               owner  = COALESCE(excluded.owner, sources.owner),
               url    = excluded.url""",
        (sid, kind, handle, name, owner, url, now()))
    conn.commit()


def sources(conn, kind=None) -> list:
    sql = """SELECT s.*,
                (SELECT COUNT(*) FROM source_videos sv WHERE sv.source_id = s.id)
                    AS n_total,
                (SELECT COUNT(*) FROM source_videos sv JOIN videos v ON v.id = sv.video_id
                  WHERE sv.source_id = s.id AND v.downloaded_path IS NOT NULL)
                    AS n_have
               FROM sources s"""
    args = []
    if kind:
        sql += " WHERE s.kind = ?"
        args.append(kind)
    sql += " ORDER BY s.kind, COALESCE(s.name, s.url)"
    return conn.execute(sql, args).fetchall()


def find_source(conn, needle: str):
    n = needle.strip().lstrip("@").lower()
    return conn.execute(
        """SELECT * FROM sources
            WHERE lower(id) = ? OR lower(handle) = ? OR lower(name) = ?
               OR lower(handle) LIKE ? OR lower(name) LIKE ? OR lower(url) LIKE ?
            ORDER BY (lower(name) = ?) DESC, length(COALESCE(name, url)) LIMIT 1""",
        (n, n, n, f"%{n}%", f"%{n}%", f"%{n}%", n)).fetchone()


def mark_synced(conn, sid: str) -> None:
    conn.execute("UPDATE sources SET last_sync = ? WHERE id = ?", (now(), sid))
    conn.commit()


def delete_source(conn, sid: str) -> None:
    conn.execute("DELETE FROM source_videos WHERE source_id = ?", (sid,))
    conn.execute("DELETE FROM sources WHERE id = ?", (sid,))
    conn.execute("DELETE FROM view_prefs WHERE scope = ?", (f"source:{sid}",))
    # Videos left in no source at all and never downloaded are noise.
    conn.execute(
        """DELETE FROM videos WHERE downloaded_path IS NULL AND starred = 0
             AND id NOT IN (SELECT video_id FROM source_videos)
             AND id NOT IN (SELECT video_id FROM collection_items)""")
    conn.commit()


# --- videos ---------------------------------------------------------------

def upsert_videos(conn, sid: str, entries: list, prune=False) -> tuple:
    """Returns (n_new, n_seen). n_new counts videos new *to this source*."""
    known = {r[0] for r in conn.execute(
        "SELECT video_id FROM source_videos WHERE source_id = ?", (sid,))}
    seen = set()
    new = 0
    for e in entries:
        vid = e["id"]
        seen.add(vid)
        if vid not in known:
            new += 1
        conn.execute(
            """INSERT INTO videos (id, title, description, duration, upload_date,
                                   date_approx, first_seen, unavailable, hidden)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   title       = excluded.title,
                   unavailable = excluded.unavailable,
                   -- Auto-hide one that has just gone dark, un-hide one that
                   -- has come back, and never touch a choice you made yourself.
                   hidden      = CASE
                       WHEN excluded.unavailable = 1 AND videos.unavailable = 0
                            AND videos.hidden = 0 THEN 2
                       WHEN excluded.unavailable = 0 AND videos.hidden = 2 THEN 0
                       ELSE videos.hidden END,
                   description = COALESCE(excluded.description, videos.description),
                   duration    = COALESCE(excluded.duration, videos.duration),
                   -- never let a fresh guess overwrite a confirmed date
                   upload_date = CASE WHEN videos.date_approx = 0
                                       AND videos.upload_date IS NOT NULL
                                      THEN videos.upload_date
                                      ELSE COALESCE(excluded.upload_date,
                                                    videos.upload_date) END,
                   date_approx = CASE WHEN videos.date_approx = 0
                                       AND videos.upload_date IS NOT NULL
                                      THEN 0 ELSE excluded.date_approx END""",
            (vid, e["title"], e.get("description"), e.get("duration"),
             e.get("upload_date"), e.get("date_approx", 0), now(),
             int(bool(e.get("unavailable"))), 2 if e.get("unavailable") else 0))
        conn.execute(
            """INSERT INTO source_videos (source_id, video_id, position)
               VALUES (?, ?, ?)
               ON CONFLICT(source_id, video_id) DO UPDATE SET position = excluded.position""",
            (sid, vid, e["position"]))
    if prune:
        # Only safe on a full sync; a --limit run has not seen the tail.
        stale = known - seen
        for vid in stale:
            conn.execute(
                "DELETE FROM source_videos WHERE source_id = ? AND video_id = ?",
                (sid, vid))
    conn.commit()
    return new, len(entries)


_SEL = """SELECT v.*,
    -- The label is who made it. If we only know the video through a playlist,
    -- that playlist's owner is the creator -- not the playlist's title.
    (SELECT CASE WHEN s.kind = 'channel' THEN s.name
                 ELSE COALESCE(s.owner, s.name) END
       FROM source_videos sv2 JOIN sources s ON s.id = sv2.source_id
      WHERE sv2.video_id = v.id ORDER BY (s.kind = 'channel') DESC, s.name
      LIMIT 1) AS channel_name,
    (SELECT s.handle FROM source_videos sv2 JOIN sources s ON s.id = sv2.source_id
      WHERE sv2.video_id = v.id ORDER BY (s.kind = 'channel') DESC, s.name
      LIMIT 1) AS channel_handle
  FROM videos v"""


def get_video(conn, vid: str):
    return conn.execute(_SEL + " WHERE v.id = ?", (vid,)).fetchone()


def query_videos(conn, source=None, collection=None, q=None, have=None,
                 starred=None, unwatched=False, hidden=False, limit=None, offset=0,
                 sort=None) -> list:
    """Rows for one view. `sort` is a key from SORTS; None means "default"."""
    args, joins, where = [], "", []
    playlist_order = False
    explicit = SORTS[sort][1] if sort and sort in SORTS else None

    if source:
        row = conn.execute("SELECT kind FROM sources WHERE id = ?", (source,)).fetchone()
        playlist_order = bool(row and row["kind"] == "playlist")
        joins += " JOIN source_videos sv ON sv.video_id = v.id AND sv.source_id = ?"
        args.append(source)
    if collection:
        joins += (" JOIN collection_items ci ON ci.video_id = v.id"
                  " AND ci.collection_id = ?")
        args.append(collection)
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
    # Hidden is the whole of visibility: unavailable only explains why.
    where.append("v.hidden != 0" if hidden else "v.hidden = 0")

    sql = _SEL + joins
    if where:
        sql += " WHERE " + " AND ".join(where)

    if explicit:
        # An explicit sort overrides curated order -- that is what it is for.
        sql += f" ORDER BY {explicit}, v.id"
    elif collection:
        sql += " ORDER BY ci.rank ASC"
    elif playlist_order:
        # A playlist's curated order is the reason it exists -- Chapter 1 first.
        sql += " ORDER BY sv.position ASC"
    else:
        if q:
            sql += " ORDER BY (CASE WHEN v.title LIKE ? THEN 0 ELSE 1 END),"
            args.append(f"%{q}%")
        else:
            sql += " ORDER BY"
        sql += " COALESCE(v.upload_date, '') DESC, v.first_seen DESC"
    if limit:
        sql += " LIMIT ? OFFSET ?"
        args += [int(limit), int(offset)]
    return conn.execute(sql, args).fetchall()


def resolve_video(conn, needle: str, source=None, collection=None):
    needle = needle.strip()
    if len(needle) == 11 and all(c.isalnum() or c in "-_" for c in needle):
        row = get_video(conn, needle)
        if row:
            return row, []
    hits = query_videos(conn, source=source, collection=collection, q=needle, limit=25)
    if not hits:
        # Naming a hidden video is how you unhide it, so it has to be findable.
        hits = query_videos(conn, source=source, collection=collection, q=needle,
                            hidden=True, limit=25)
    if len(hits) == 1:
        return hits[0], []
    return None, hits


def video_sources(conn, vid: str) -> list:
    return conn.execute(
        """SELECT s.*, sv.position FROM sources s
             JOIN source_videos sv ON sv.source_id = s.id
            WHERE sv.video_id = ? ORDER BY (s.kind = 'channel') DESC, s.name""",
        (vid,)).fetchall()


def set_downloaded(conn, vid, path, size, upload_date=None, description=None,
                   duration=None) -> None:
    conn.execute(
        """UPDATE videos SET downloaded_path = ?, downloaded_at = ?, filesize = ?,
                 upload_date = COALESCE(?, upload_date),
                 date_approx = CASE WHEN ? IS NOT NULL THEN 0 ELSE date_approx END,
                 description = COALESCE(?, description),
                 duration    = COALESCE(?, duration)
            WHERE id = ?""",
        (str(path) if path else None, now() if path else None, size,
         upload_date, upload_date, description, duration, vid))
    conn.commit()


def clear_downloaded(conn, vid: str) -> None:
    conn.execute("UPDATE videos SET downloaded_path = NULL, downloaded_at = NULL,"
                 " filesize = NULL WHERE id = ?", (vid,))
    conn.commit()


def set_flag(conn, vid: str, field: str, value) -> None:
    assert field in {"starred", "watched", "progress", "hidden"}
    extra = ", watched_at = ?" if field == "watched" else ""
    args = [value, now(), vid] if field == "watched" else [value, vid]
    conn.execute(f"UPDATE videos SET {field} = ?{extra} WHERE id = ?", args)
    conn.commit()


# --- collections ----------------------------------------------------------

def collections(conn) -> list:
    return conn.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM collection_items ci
                    WHERE ci.collection_id = c.id) AS n_total,
                  (SELECT COUNT(*) FROM collection_items ci JOIN videos v
                          ON v.id = ci.video_id
                    WHERE ci.collection_id = c.id
                      AND v.downloaded_path IS NOT NULL) AS n_have
             FROM collections c ORDER BY c.name""").fetchall()


def find_collection(conn, needle: str):
    n = needle.strip().lower()
    return conn.execute(
        "SELECT * FROM collections WHERE lower(name) = ? OR lower(name) LIKE ?"
        " ORDER BY length(name) LIMIT 1", (n, f"%{n}%")).fetchone()


def create_collection(conn, name: str):
    conn.execute("INSERT OR IGNORE INTO collections (name, created_at) VALUES (?, ?)",
                 (name.strip(), now()))
    conn.commit()
    return find_collection(conn, name.strip())


def delete_collection(conn, cid: int) -> None:
    conn.execute("DELETE FROM collection_items WHERE collection_id = ?", (cid,))
    conn.execute("DELETE FROM collections WHERE id = ?", (cid,))
    conn.execute("DELETE FROM view_prefs WHERE scope = ?", (f"collection:{cid}",))
    conn.commit()


def collection_add(conn, cid: int, vid: str) -> bool:
    nxt = conn.execute(
        "SELECT COALESCE(MAX(rank), -1) + 1 FROM collection_items WHERE collection_id = ?",
        (cid,)).fetchone()[0]
    cur = conn.execute(
        "INSERT OR IGNORE INTO collection_items (collection_id, video_id, rank, added_at)"
        " VALUES (?, ?, ?, ?)", (cid, vid, nxt, now()))
    conn.commit()
    return cur.rowcount > 0


def collection_remove(conn, cid: int, vid: str) -> bool:
    cur = conn.execute(
        "DELETE FROM collection_items WHERE collection_id = ? AND video_id = ?",
        (cid, vid))
    conn.commit()
    return cur.rowcount > 0


def collection_move(conn, cid: int, vid: str, delta: int) -> bool:
    """Nudge one entry up or down within its collection."""
    rows = conn.execute(
        "SELECT video_id FROM collection_items WHERE collection_id = ? ORDER BY rank",
        (cid,)).fetchall()
    ids = [r[0] for r in rows]
    if vid not in ids:
        return False
    i = ids.index(vid)
    j = max(0, min(len(ids) - 1, i + delta))
    if i == j:
        return False
    ids.insert(j, ids.pop(i))
    for rank, v in enumerate(ids):
        conn.execute(
            "UPDATE collection_items SET rank = ? WHERE collection_id = ? AND video_id = ?",
            (rank, cid, v))
    conn.commit()
    return True


def collections_for(conn, vid: str) -> list:
    return conn.execute(
        """SELECT c.id, c.name FROM collections c
             JOIN collection_items ci ON ci.collection_id = c.id
            WHERE ci.video_id = ? ORDER BY c.name""", (vid,)).fetchall()


# --- remembered sort ------------------------------------------------------

def sort_scope(source=None, collection=None) -> str:
    if collection:
        return f"collection:{collection}"
    if source:
        return f"source:{source}"
    return "global"


def get_sort(conn, source=None, collection=None) -> str:
    """The sort this view should use: its own, else the global one, else default.

    A per-view row wins so that one channel you read oldest-first stays that
    way without dragging the rest of the library with it.
    """
    scopes = [sort_scope(source, collection)]
    if scopes[0] != "global":
        scopes.append("global")
    for scope in scopes:
        row = conn.execute("SELECT sort FROM view_prefs WHERE scope = ?",
                           (scope,)).fetchone()
        if row and row["sort"] in SORTS:
            return row["sort"]
    return "default"


def set_sort(conn, sort: str, source=None, collection=None) -> None:
    """Remember (or, for 'default', forget) the sort for one view."""
    if sort not in SORTS:
        raise ValueError(f"unknown sort {sort!r}")
    scope = sort_scope(source, collection)
    if sort == "default":
        # Storing 'default' would shadow a global preference the user set on
        # purpose; clearing the row is what "back to normal" actually means.
        conn.execute("DELETE FROM view_prefs WHERE scope = ?", (scope,))
    else:
        conn.execute(
            """INSERT INTO view_prefs (scope, sort, set_at) VALUES (?, ?, ?)
               ON CONFLICT(scope) DO UPDATE SET sort = excluded.sort,
                                                set_at = excluded.set_at""",
            (scope, sort, now()))
    conn.commit()


# --- misc -----------------------------------------------------------------

def stats(conn) -> dict:
    # Counts describe the catalog you actually see; hidden rows are their own
    # tally rather than a silent addition to the total.
    row = conn.execute(
        """SELECT COUNT(*) AS total,
                  SUM(downloaded_path IS NOT NULL) AS have,
                  SUM(COALESCE(filesize, 0))       AS bytes,
                  SUM(starred)                     AS starred,
                  SUM(downloaded_path IS NOT NULL AND watched = 0) AS unwatched
             FROM videos WHERE hidden = 0""").fetchone()
    d = {k: (row[k] or 0) for k in row.keys()}
    d["hidden"] = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE hidden != 0").fetchone()[0]
    d["channels"] = conn.execute(
        "SELECT COUNT(*) FROM sources WHERE kind = 'channel'").fetchone()[0]
    d["playlists"] = conn.execute(
        "SELECT COUNT(*) FROM sources WHERE kind = 'playlist'").fetchone()[0]
    d["collections"] = conn.execute("SELECT COUNT(*) FROM collections").fetchone()[0]
    return d


def prune_missing(conn) -> int:
    gone = 0
    for row in conn.execute(
        "SELECT id, downloaded_path FROM videos WHERE downloaded_path IS NOT NULL"
    ).fetchall():
        if not Path(row["downloaded_path"]).exists():
            clear_downloaded(conn, row["id"])
            gone += 1
    return gone
