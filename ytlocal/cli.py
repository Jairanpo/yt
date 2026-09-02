"""Command line entry point."""
import argparse
import os
import shutil
import subprocess
import sys
import textwrap
import webbrowser
from pathlib import Path

from ytlocal import config, db, ytdlp
from ytlocal.jobs import Downloader

C = {"dim": "\033[2m", "b": "\033[1m", "acc": "\033[38;5;173m",
     "ok": "\033[38;5;71m", "err": "\033[38;5;167m", "r": "\033[0m"}
if not sys.stdout.isatty():
    C = dict.fromkeys(C, "")


def out(msg=""):
    print(msg, flush=True)


def die(msg, code=1):
    print(f"{C['err']}error:{C['r']} {msg}", file=sys.stderr)
    raise SystemExit(code)


def human_size(b):
    if not b:
        return "-"
    for unit, div in (("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if b >= div:
            return f"{b / div:.1f}{unit}"
    return f"{b}B"


def human_dur(s):
    if not s:
        return "--:--"
    s = int(s)
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def fmt_date(v):
    """Exact dates print in full; guesses print as ~YYYY-MM, day withheld."""
    if not v["upload_date"]:
        return "          "
    if v["date_approx"]:
        return f"~{v['upload_date'][:7]}  "
    return v["upload_date"]


def fmt_row(v, width=None):
    width = width or max(40, (shutil.get_terminal_size((100, 24)).columns) - 44)
    mark = f"{C['ok']}●{C['r']}" if v["downloaded_path"] else f"{C['dim']}○{C['r']}"
    star = "★" if v["starred"] else " "
    title = v["title"]
    if len(title) > width:
        title = title[: width - 1] + "…"
    return (f"{mark}{star} {C['dim']}{v['id']}{C['r']}  {fmt_date(v)}  "
            f"{human_dur(v['duration']):>8}  {title}")


# --- commands -------------------------------------------------------------

def cmd_add(args, cfg, conn):
    url = ytdlp.channel_url(args.channel)
    out(f"resolving {C['acc']}{url}{C['r']} …")
    meta, entries = ytdlp.sync_channel(cfg, url, limit=args.limit)
    cid = meta["channel_id"]
    db.upsert_channel(conn, cid, url, meta.get("name"), meta.get("handle"))
    new, total = db.upsert_videos(conn, cid, entries)
    db.mark_synced(conn, cid)
    name = meta.get("name") or meta.get("handle") or cid
    out(f"{C['ok']}added{C['r']} {C['b']}{name}{C['r']} — {total} videos catalogued "
        f"({new} new). Nothing downloaded yet.")
    out(f"{C['dim']}next: yt list \"{name}\"   ·   yt get <id|search text>{C['r']}")


def cmd_sync(args, cfg, conn):
    targets = db.channels(conn)
    if args.channel:
        row = db.find_channel(conn, args.channel)
        if not row:
            die(f"no tracked channel matching {args.channel!r} (see: yt channels)")
        targets = [row]
    if not targets:
        die("no channels tracked yet — start with: yt add @somechannel")

    grand_new = 0
    for ch in targets:
        name = ch["name"] or ch["handle"] or ch["url"]
        try:
            meta, entries = ytdlp.sync_channel(cfg, ch["url"], limit=args.limit)
        except ytdlp.YtdlpError as exc:
            out(f"{C['err']}✗{C['r']} {name}: {exc}")
            continue
        db.upsert_channel(conn, ch["id"], ch["url"], meta.get("name"), meta.get("handle"))
        new, total = db.upsert_videos(conn, ch["id"], entries)
        db.mark_synced(conn, ch["id"])
        grand_new += new
        flag = f"{C['acc']}+{new} new{C['r']}" if new else f"{C['dim']}no change{C['r']}"
        out(f"{C['ok']}✓{C['r']} {name:<34.34} {total:>5} catalogued  {flag}")
        if new and args.show_new:
            for v in db.query_videos(conn, channel=ch["id"], limit=new):
                out("    " + fmt_row(v))
    out(f"\n{grand_new} new video(s) across {len(targets)} channel(s).")


def cmd_list(args, cfg, conn):
    channel = None
    if args.channel:
        row = db.find_channel(conn, args.channel)
        if not row:
            die(f"no tracked channel matching {args.channel!r}")
        channel = row["id"]
    have = True if args.downloaded else (False if args.missing else None)
    rows = db.query_videos(conn, channel=channel, q=args.query, have=have,
                           starred=args.starred, unwatched=args.unwatched,
                           limit=args.number)
    if not rows:
        out("nothing matches.")
        return
    for v in rows:
        out(fmt_row(v))
    out(f"\n{C['dim']}{len(rows)} shown · ● = on disk, ○ = catalog only{C['r']}")


def _resolve_or_die(conn, needle, channel=None):
    row, hits = db.resolve_video(conn, needle, channel)
    if row:
        return row
    if not hits:
        die(f"nothing in the catalog matches {needle!r}. Try: yt sync")
    out(f"{C['b']}{len(hits)} matches — narrow it down or pass the id:{C['r']}")
    for v in hits[:15]:
        out("  " + fmt_row(v))
    raise SystemExit(2)


def _download_now(cfg, conn, rows, audio_only=False):
    media = config.media_dir(cfg)
    for i, v in enumerate(rows, 1):
        if v["downloaded_path"] and Path(v["downloaded_path"]).exists():
            out(f"{C['dim']}have already:{C['r']} {v['title']}")
            continue
        label = f"[{i}/{len(rows)}] {v['title'][:60]}"
        out(f"{C['acc']}↓{C['r']} {label}")

        def progress(frac, text):
            if sys.stderr.isatty():
                print(f"\r   {text:<60}", end="", file=sys.stderr, flush=True)

        try:
            res = ytdlp.download(cfg, v["id"], media, audio_only, progress)
        except ytdlp.YtdlpError as exc:
            if sys.stderr.isatty():
                print("\r" + " " * 66 + "\r", end="", file=sys.stderr)
            out(f"{C['err']}   failed:{C['r']} {exc}")
            continue
        if sys.stderr.isatty():
            print("\r" + " " * 66 + "\r", end="", file=sys.stderr)
        size = res["path"].stat().st_size if res["path"].exists() else None
        db.set_downloaded(conn, v["id"], res["path"], size, res.get("upload_date"),
                          res.get("description"), res.get("duration"))
        out(f"{C['ok']}   ✓{C['r']} {human_size(size)}  {C['dim']}{res['path']}{C['r']}")


def cmd_get(args, cfg, conn):
    if args.starred:
        rows = db.query_videos(conn, starred=True, have=False)
        if not rows:
            out("no starred videos left to download.")
            return
    elif args.latest:
        channel = None
        if args.target:
            ch = db.find_channel(conn, args.target[0])
            if not ch:
                die(f"no tracked channel matching {args.target[0]!r}")
            channel = ch["id"]
        rows = db.query_videos(conn, channel=channel, have=False, limit=args.latest)
    else:
        if not args.target:
            die("give a video id, a search phrase, --starred, or --latest N")
        rows = [_resolve_or_die(conn, " ".join(args.target))]
    _download_now(cfg, conn, rows, args.audio)


def cmd_watch(args, cfg, conn):
    v = _resolve_or_die(conn, " ".join(args.target))
    if not (v["downloaded_path"] and Path(v["downloaded_path"]).exists()):
        out(f"{C['dim']}not on disk yet — fetching first{C['r']}")
        _download_now(cfg, conn, [v])
        v = db.get_video(conn, v["id"])
    if not v["downloaded_path"]:
        die("download did not complete; nothing to play")

    player = cfg.get("player") or next(
        (p for p in ("mpv", "vlc", "xdg-open") if shutil.which(p)), None)
    if not player:
        die("no player found — install mpv, or set \"player\" in " + str(config.CONFIG_PATH))
    out(f"{C['acc']}▶{C['r']} {v['title']}  {C['dim']}({player}){C['r']}")
    subprocess.run([player, v["downloaded_path"]])
    if args.mark:
        db.set_flag(conn, v["id"], "watched", 1)


def cmd_rm(args, cfg, conn):
    v = _resolve_or_die(conn, " ".join(args.target))
    if not v["downloaded_path"]:
        out("that one is catalog-only already; nothing on disk to remove.")
        return
    path = Path(v["downloaded_path"])
    if not args.yes:
        out(f"about to delete {C['b']}{path}{C['r']} ({human_size(v['filesize'])})")
        if input("proceed? [y/N] ").strip().lower() not in ("y", "yes"):
            out("cancelled.")
            return
    for _lang, sub in ytdlp.sidecar_subs(path):
        sub.unlink(missing_ok=True)
    path.unlink(missing_ok=True)
    db.clear_downloaded(conn, v["id"])
    out(f"{C['ok']}removed{C['r']} — catalog entry kept, re-fetch any time with yt get")


def cmd_star(args, cfg, conn):
    v = _resolve_or_die(conn, " ".join(args.target))
    val = 0 if (v["starred"] and not args.on) else 1
    if args.off:
        val = 0
    db.set_flag(conn, v["id"], "starred", val)
    out(("★ starred " if val else "☆ unstarred ") + v["title"])


def cmd_channels(args, cfg, conn):
    rows = db.channels(conn)
    if not rows:
        out("no channels tracked. add one:  yt add @channel")
        return
    for c in rows:
        name = c["name"] or c["handle"] or c["url"]
        out(f"{C['b']}{name:<36.36}{C['r']} {c['n_have']:>4}/{c['n_total']:<5} on disk  "
            f"{C['dim']}{c['handle'] or c['url']}{C['r']}")


def cmd_forget(args, cfg, conn):
    ch = db.find_channel(conn, args.channel)
    if not ch:
        die(f"no tracked channel matching {args.channel!r}")
    name = ch["name"] or ch["url"]
    if not args.yes:
        out(f"drop {C['b']}{name}{C['r']} and its catalog entries? "
            f"{C['dim']}(downloaded files stay on disk){C['r']}")
        if input("proceed? [y/N] ").strip().lower() not in ("y", "yes"):
            out("cancelled.")
            return
    db.delete_channel(conn, ch["id"])
    out(f"forgot {name}")


def cmd_info(args, cfg, conn):
    v = _resolve_or_die(conn, " ".join(args.target))
    if args.refresh or not v["upload_date"] or not v["description"]:
        try:
            meta = ytdlp.fetch_info(cfg, v["id"])
            db.set_downloaded(conn, v["id"], v["downloaded_path"], v["filesize"],
                              meta["upload_date"], meta["description"], meta["duration"])
            v = db.get_video(conn, v["id"])
        except ytdlp.YtdlpError as exc:
            out(f"{C['dim']}(could not refresh metadata: {exc}){C['r']}")
    out(f"{C['b']}{v['title']}{C['r']}")
    shown = (f"{v['upload_date']} (approximate)" if v['date_approx']
             else v['upload_date']) if v['upload_date'] else 'date unknown'
    out(f"{C['dim']}{v['channel_name']} · {shown} · "
        f"{human_dur(v['duration'])} · {v['id']}{C['r']}")
    out(f"on disk: {v['downloaded_path'] or '(catalog only)'}")
    if v["downloaded_path"]:
        subs = ytdlp.sidecar_subs(Path(v["downloaded_path"]))
        out(f"size: {human_size(v['filesize'])}   subtitles: "
            f"{', '.join(l for l, _ in subs) or 'none'}")
    if v["description"]:
        out("")
        for para in (v["description"] or "").splitlines():
            out(textwrap.fill(para, 88) if para.strip() else "")


def cmd_status(args, cfg, conn):
    gone = db.prune_missing(conn)
    s = db.stats(conn)
    out(f"{C['b']}catalog{C['r']}   {s['total']} videos across {s['channels']} channels")
    out(f"{C['b']}on disk{C['r']}   {s['have']} files · {human_size(s['bytes'])}"
        f" · {s['unwatched']} unwatched")
    out(f"{C['b']}starred{C['r']}   {s['starred']}")
    out(f"{C['b']}media{C['r']}     {cfg['media_dir']}")
    out(f"{C['b']}catalog db{C['r']}{' ' * 1} {config.DB_PATH}")
    if gone:
        out(f"{C['dim']}({gone} file(s) had vanished from disk; catalog updated){C['r']}")
    try:
        out(f"{C['dim']}yt-dlp {ytdlp.check(cfg)}{C['r']}")
    except ytdlp.YtdlpError as exc:
        out(f"{C['err']}{exc}{C['r']}")


def cmd_serve(args, cfg, conn):
    from ytlocal import server
    conn.close()
    httpd = server.serve(cfg, args.port, verbose=args.verbose)
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    out(f"{C['acc']}▶{C['r']} library at {C['b']}{url}{C['r']}  {C['dim']}(ctrl-c to stop){C['r']}")
    out(f"{C['dim']}bound to loopback only — nothing else on your network can reach it{C['r']}")
    if not args.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        out("\nstopped.")
    finally:
        httpd.server_close()


def cmd_config(args, cfg, conn):
    if args.init:
        path = config.write_default_config()
        out(f"wrote defaults to {path}")
        return
    out(f"{C['dim']}config file: {config.CONFIG_PATH}"
        f"{'' if config.CONFIG_PATH.exists() else ' (not created — using defaults)'}{C['r']}")
    for k, v in cfg.items():
        out(f"  {k:<12} {v}")


def cmd_block(args, cfg, conn):
    out(textwrap.dedent(f"""\
        {C['b']}Blocking YouTube itself{C['r']}

        This tool never needs your browser to reach YouTube — only yt-dlp does,
        and it talks to Google directly rather than through the browser. So a
        hosts-file block leaves the whole workflow intact.

        Add to {C['acc']}/etc/hosts{C['r']} (needs sudo):

          0.0.0.0 www.youtube.com
          0.0.0.0 youtube.com
          0.0.0.0 m.youtube.com
          0.0.0.0 music.youtube.com

        {C['b']}Do not block{C['r']} googlevideo.com or i.ytimg.com — yt-dlp streams the
        actual media from googlevideo.com, and thumbnails come from i.ytimg.com.
        Blocking those breaks downloads.

        Your library then lives at http://127.0.0.1:{cfg['port']} via  yt serve.

        {C['dim']}Not applied automatically — editing /etc/hosts is your call.{C['r']}"""))


# --- parser ---------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="yt", description="Catalog-first local mirror for YouTube channels.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            typical flow:
              yt add @veritasium        catalog the channel (metadata only, seconds)
              yt list veritasium -n 20  see what is there
              yt get "black hole"       download the one you want
              yt serve                  browse + watch at localhost:8420
              yt sync                   pick up new uploads (cron-friendly)
            """))
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="track a channel and catalog its videos")
    a.add_argument("channel", help="@handle, channel URL, or playlist URL")
    a.add_argument("--limit", type=int, help="only catalog the newest N")
    a.set_defaults(fn=cmd_add)

    s = sub.add_parser("sync", help="refresh catalogs (no downloads)")
    s.add_argument("channel", nargs="?", help="one channel; default is all")
    s.add_argument("--limit", type=int, help="only check the newest N per channel")
    s.add_argument("--show-new", action="store_true", help="print new entries")
    s.set_defaults(fn=cmd_sync)

    l = sub.add_parser("list", help="browse the catalog")
    l.add_argument("channel", nargs="?")
    l.add_argument("-q", "--query", help="filter by text")
    l.add_argument("-n", "--number", type=int, default=40)
    l.add_argument("--downloaded", action="store_true", help="only files on disk")
    l.add_argument("--missing", action="store_true", help="only catalog-only entries")
    l.add_argument("--starred", action="store_true")
    l.add_argument("--unwatched", action="store_true")
    l.set_defaults(fn=cmd_list)

    g = sub.add_parser("get", help="download video(s) to disk")
    g.add_argument("target", nargs="*", help="video id or search phrase")
    g.add_argument("--audio", action="store_true", help="audio only (m4a)")
    g.add_argument("--starred", action="store_true", help="every starred video not yet on disk")
    g.add_argument("--latest", type=int, metavar="N", help="newest N not yet on disk")
    g.set_defaults(fn=cmd_get)

    w = sub.add_parser("watch", help="play (downloading first if needed)")
    w.add_argument("target", nargs="+")
    w.add_argument("--mark", action="store_true", help="mark watched afterwards")
    w.set_defaults(fn=cmd_watch)

    r = sub.add_parser("rm", help="delete a downloaded file, keep the catalog entry")
    r.add_argument("target", nargs="+")
    r.add_argument("-y", "--yes", action="store_true")
    r.set_defaults(fn=cmd_rm)

    st = sub.add_parser("star", help="toggle a star")
    st.add_argument("target", nargs="+")
    st.add_argument("--on", action="store_true")
    st.add_argument("--off", action="store_true")
    st.set_defaults(fn=cmd_star)

    sub.add_parser("channels", help="list tracked channels").set_defaults(fn=cmd_channels)

    f = sub.add_parser("forget", help="stop tracking a channel")
    f.add_argument("channel")
    f.add_argument("-y", "--yes", action="store_true")
    f.set_defaults(fn=cmd_forget)

    i = sub.add_parser("info", help="details for one video")
    i.add_argument("target", nargs="+")
    i.add_argument("--refresh", action="store_true", help="re-fetch metadata")
    i.set_defaults(fn=cmd_info)

    sub.add_parser("status", help="library summary").set_defaults(fn=cmd_status)

    sv = sub.add_parser("serve", help="start the local web library")
    sv.add_argument("-p", "--port", type=int)
    sv.add_argument("--no-open", action="store_true", help="do not launch a browser")
    sv.add_argument("-v", "--verbose", action="store_true")
    sv.set_defaults(fn=cmd_serve)

    c = sub.add_parser("config", help="show or create the config file")
    c.add_argument("--init", action="store_true")
    c.set_defaults(fn=cmd_config)

    sub.add_parser("block", help="how to block youtube.com without breaking this")\
        .set_defaults(fn=cmd_block)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    cfg = config.load()
    conn = db.connect()
    try:
        args.fn(args, cfg, conn)
    except ytdlp.YtdlpError as exc:
        die(str(exc))
    except KeyboardInterrupt:
        out("\ninterrupted.")
        return 130
    except BrokenPipeError:
        # `yt list | head` closes the pipe early; exit quietly. Redirecting to
        # devnull first stops Python's shutdown flush from raising again.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
