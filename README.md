# yt · local

A catalog-first local library for the YouTube channels you actually learn from,
so you can block youtube.com outright and still reach the videos you want.

Two ideas do the work:

1. **Cataloguing is cheap; downloading is not.** Indexing a channel pulls
   metadata only — one request per ~100 videos, no disk. A 500-video back
   catalogue becomes a searchable list in seconds. You then download only what
   you choose.
2. **The library is sealed.** `yt serve` binds to loopback and the page carries
   a CSP that forbids outbound requests. Thumbnails are cached server-side on
   first view. Once a video is on disk, watching it touches no network at all.

## Requirements

`yt-dlp`, `ffmpeg`, and Python 3.11+. No Python packages to install — the tool
is stdlib-only, and shells out to `yt-dlp` so you can update it independently
when an extractor breaks:

```bash
uv tool install yt-dlp     # or: pipx install yt-dlp
uv tool upgrade yt-dlp     # when a download suddenly fails, do this first
```

## Getting started

```bash
./yt add @3blue1brown          # catalog the channel — metadata only, seconds
./yt list 3blue1brown -n 20    # see what's there
./yt get "hairy ball"          # download the one you want, by title or id
./yt serve                     # browse and watch at http://127.0.0.1:8420
```

Put `yt` on your PATH (`ln -s "$PWD/yt" ~/.local/bin/yt`) to drop the `./`.

## Commands

| Command | What it does |
| --- | --- |
| `yt add <@handle\|url>` | Track a channel and catalog it. `--limit N` for just the newest N. |
| `yt sync [channel]` | Refresh catalogs; never downloads. Cron-friendly. `--show-new` lists what appeared. |
| `yt list [channel]` | Browse. `-q TEXT`, `--downloaded`, `--missing`, `--starred`, `--unwatched`, `-n N`. |
| `yt get <id\|phrase>` | Download. Also `--starred` (everything starred), `--latest N`, `--audio`. |
| `yt watch <id\|phrase>` | Play in mpv/vlc, downloading first if needed. |
| `yt star <id\|phrase>` | Mark things to fetch later, then `yt get --starred`. |
| `yt rm <id\|phrase>` | Delete the file, keep the catalog entry so you can re-fetch. |
| `yt info <id\|phrase>` | Details. `--refresh` pulls exact metadata from YouTube. |
| `yt status` | Counts, disk use, and it re-syncs the catalog with what's actually on disk. |
| `yt serve` | The web library. `-p PORT`, `--no-open`. |
| `yt channels` / `yt forget <ch>` | List / stop tracking. |
| `yt config [--init]` | Show settings, or write a config file to edit. |
| `yt block` | How to block youtube.com without breaking downloads. |

Anywhere an id is accepted you can type part of a title instead. If it's
ambiguous the tool prints the candidates and stops rather than guessing.

## Blocking YouTube

`yt-dlp` talks to Google directly, not through your browser, so a hosts-file
block leaves this tool fully working:

```
0.0.0.0 www.youtube.com
0.0.0.0 youtube.com
0.0.0.0 m.youtube.com
0.0.0.0 music.youtube.com
```

Do **not** block `googlevideo.com` (where media actually streams from) or
`i.ytimg.com` (thumbnails) — that breaks downloads. `yt block` prints this too.

## About the dates

Flat channel listings carry no publish date. Asking yt-dlp to approximate one
derives it from the "7 months ago" label, so the day-of-month is noise and the
result can be weeks off. Those are shown as `~2026-07` — month precision, day
withheld — and never as an exact date. A date becomes exact once the video is
downloaded or you run `yt info --refresh`, at which point it displays in full
and an approximation can no longer overwrite it.

## Staying current

```cron
0 7 * * *  cd /path/to/repo && ./yt sync
```

That refreshes catalogs only. To auto-fetch as well, star what you care about
and follow with `./yt get --starred`, or use `./yt get --latest 3 <channel>`.

## Config

`yt config --init` writes `~/.config/ytlocal/config.json`:

| Key | Default | Notes |
| --- | --- | --- |
| `media_dir` | `~/Videos/yt` | One subdirectory per channel. |
| `max_height` | `1080` | Prefers mp4/m4a so the browser plays it without transcoding. |
| `sub_langs` | `en,es` | Keep these exact. `en.*` also matches every auto-translated track — dozens of requests per video and a quick 429 from YouTube. |
| `port` | `8420` | |
| `player` | auto | mpv → vlc → xdg-open. |
| `ytdlp_args` | `[]` | Appended to every call, e.g. `["--cookies-from-browser","firefox"]` for members-only videos. |

Catalog lives at `~/.local/share/ytlocal/catalog.db` — plain SQLite, query it
directly if you want. Deleting a video file never deletes its catalog entry.

## Notes

Subtitles are fetched in a second, best-effort pass *after* the video lands, so
a rate-limit on subtitles can't throw away a finished download. Media is served
with HTTP Range support, so seeking works. Watch progress is saved every five
seconds and restored when you reopen a video.
