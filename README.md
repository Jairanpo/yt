# yt · local

A catalog-first local library for the YouTube channels, playlists and courses
you actually learn from, so you can block youtube.com outright and still reach
the videos you want.

Three ideas do the work:

1. **Cataloguing is cheap; downloading is not.** Indexing a channel pulls
   metadata only — one request per ~100 videos, no disk. A 500-video back
   catalogue becomes a searchable list in seconds. You then download only what
   you choose.
2. **The library is sealed.** `yt serve` binds to loopback and the page carries
   a CSP that forbids outbound requests. Thumbnails are cached server-side on
   first view. Once a video is on disk, watching it touches no network at all.
3. **Order carries meaning.** A channel is newest-first. A playlist is whatever
   order its author chose, because "Chapter 1" before "Chapter 2" is the entire
   point of a lesson series. Collections you build yourself keep your order.
   When a view's own order isn't the one you want, [sorting](#sorting) is a
   per-view setting the library remembers.

---

## Install

`yt-dlp`, `ffmpeg`, and Python 3.11+. No Python packages to install — the tool
is stdlib-only, and shells out to `yt-dlp` so you can update it independently
when an extractor breaks.

```bash
uv tool install yt-dlp        # or: pipx install yt-dlp
sudo apt install ffmpeg       # needed to merge video+audio streams

ln -s "$PWD/yt" ~/.local/bin/yt    # optional, drops the ./ prefix
yt status                          # confirms yt-dlp is visible and prints paths
```

Everything below assumes `yt` is on your PATH. Otherwise use `./yt`.

---

## Your first five minutes

**1. Track a channel.** Takes seconds and downloads nothing.

```console
$ yt add @3blue1brown
resolving https://www.youtube.com/@3blue1brown/videos …
added 3Blue1Brown — 151 videos catalogued (151 new). Nothing downloaded yet.
```

Accepts an `@handle`, a full channel URL, or a playlist URL. Add `--limit 20`
to index only the newest 20 instead of the whole back catalogue.

**1b. Or track a playlist.** Same command — it detects the kind from the URL.

```console
$ yt add "https://www.youtube.com/playlist?list=PLZHQObOWTQDPD3MizzM2xVFitgF8hE_ab"
added playlist Essence of linear algebra (3Blue1Brown) — 16 videos catalogued (16 new).
listed in the playlist's own order; yt list "Essence of linear algebra" to see it
```

**2. See what's there.**

```console
$ yt list 3blue1brown -n 5
○  GlYgs6v2YfU  2026-07-16     33:51  But what is cross-entropy? | Compression is Intelligenc…
○  l6DKRf-fAAM  ~2026-07       32:20  Reinventing Entropy | Compression is Intelligence Part 1
○  ldxFjLJ3rVY  ~2026-04       44:52  How (and why) to take a logarithm of an image
○  fsLh-NYhOoU  ~2026-03     1:00:24  The most beautiful formula not enough people understand
○  BHdbsHFs2P0  ~2026-02       29:40  Why you can't comb a hairy ball, and why we care

5 shown · ● = on disk, ○ = catalog only
```

Reading a row: **`○`** catalog-only, **`●`** downloaded, **`★`** starred, then
the video id, the date, the runtime, the title. A `~2026-04` date is a
month-precision estimate — see [About the dates](#about-the-dates).

**3. Download one.** By id, or by any distinctive part of the title.

```console
$ yt get "hairy ball"
↓ [1/1] Why you can't comb a hairy ball, and why we care
   ✓ 38.1MB  ~/Videos/yt/3Blue1Brown/2026-01-31 - Why_you_can_t_comb_a_hairy_ball [BHdbsHFs2P0].mp4
```

**4. Watch it.** Either in your player, or in the browser library.

```bash
yt watch "hairy ball"    # opens mpv/vlc; downloads first if not on disk yet
yt serve                 # web library at http://127.0.0.1:8420
```

---

## Finding things

Anywhere a video id is accepted you can type part of a title instead. Matching
is case-insensitive across titles and descriptions. If the phrase is ambiguous
the tool shows the candidates and stops rather than guessing:

```console
$ yt get "Laplace"
3 matches — narrow it down or pass the id:
  ●  FE-hM1kRK4Y  2025-11-05     23:05  Why Laplace transforms are so useful
  ○  j0wJBEZdwLs  ~2025-11       34:41  But what is a Laplace Transform?
  ○  -j8PzkZ70Lg  ~2025-11       27:49  The Physics of Euler's Formula | Laplace Transform Prel…
```

Either give more of the title (`yt get "Laplace transforms are"`) or paste the
id. Multi-word phrases don't need quoting, but quoting avoids surprises with
shell characters.

Filters compose, so `yt list` is the main way to navigate a big catalogue:

```bash
yt list                              # newest 40 across every channel
yt list veritasium -n 100            # one channel, more rows
yt list -q "entropy"                 # text search
yt list --downloaded                 # only what's on disk
yt list --missing --starred          # starred but not yet fetched
yt list --downloaded --unwatched     # your actual watch queue
yt list veritasium --sort oldest     # from the beginning — see Sorting
```

---

## Downloading

```bash
yt get <id|phrase>              # one video
yt get --audio "interview"      # audio only, m4a — good for talks
yt get --latest 3               # newest 3 not yet on disk, all channels
yt get --latest 3 veritasium    # newest 3 from one channel
yt get --starred                # everything you starred and haven't fetched
```

The **star-then-batch** pattern is the one worth building a habit around.
Triage cheaply whenever you like, then fetch in one go:

```bash
yt list 3blue1brown -n 60        # skim
yt star "cross-entropy"          # mark the keepers, no download yet
yt star "logarithm of an image"
yt get --starred                 # fetch them all when you're ready
```

Files land in `~/Videos/yt/<Channel>/<date> - <title> [<id>].mp4`, one folder
per channel. Quality caps at 1080p by default and prefers mp4/m4a so the
browser plays it without transcoding.

Freeing space keeps your curation intact — `yt rm` deletes the file but never
the catalog entry, so the video stays searchable and re-fetchable:

```console
$ yt rm "Laplace transforms are"
about to delete ~/Videos/yt/3Blue1Brown/2025-11-05 - Why_Laplace… [FE-hM1kRK4Y].mp4 (28.0MB)
proceed? [y/N] y
removed — catalog entry kept, re-fetch any time with yt get
```

Add `-y` to skip the prompt.

---

## The web library

```bash
yt serve                 # opens your browser at http://127.0.0.1:8420
yt serve -p 9000         # different port
yt serve --no-open       # don't launch a browser
```

Bound to loopback, so nothing else on your network can reach it. Ctrl-C stops.

- **Search box** filters titles and descriptions as you type. The dropdown
  groups everything you can narrow to: **Channels**, **Playlists**, and your
  **Collections**. Picking a playlist or collection switches the grid into that
  list's own order and numbers each card.
- **Sort dropdown** reorders the grid — newest, oldest, recently added, title,
  longest, shortest. Your choice is remembered for that view and shared with
  the CLI; see [Sorting](#sorting).
- **＋ collection** on any card adds it to one of your collections, or creates
  a new one on the spot.
- **Three chips** — Downloaded, Starred, Unwatched — combine with the search.
- **Cards** show a thumbnail, runtime, and a green *on disk* flag. The button
  reads **Watch** if the file is local and **Download** if it isn't; clicking
  the thumbnail or title does the same thing. **☆** stars, **✕** deletes the
  file (with a confirm) and keeps the catalog entry.
- **Downloads** run in the background — queue as many as you like and progress
  toasts appear bottom-right. Click a finished toast to dismiss it. You can
  keep browsing and watching while they run.
- **The player** opens over the page. Subtitles attach automatically when a
  `.vtt` sidecar exists. Seeking works (media is served with HTTP Range).
  Position is saved every five seconds and restored next time — cards show a
  resume bar. Finishing a video marks it watched. **Esc** closes.

---

## Playlists

A playlist is tracked exactly like a channel — `yt add` takes an `@handle`, a
channel URL, a playlist URL, or a bare `PL...` id and works out which it is.
The difference is what happens to ordering:

```console
$ yt list "linear algebra" -n 4
  1 ○  fNk_zzaMoSs  ~2016-09        9:52  Vectors | Chapter 1, Essence of linear algebra
  2 ○  k7RM-ot2NWY  ~2016-09        9:59  Linear combinations, span, and basis vectors | Chap…
  3 ○  kYB8IZa5AuE  ~2016-09       10:59  Linear transformations and matrices | Chapter 3, Es…
  4 ○  XkY2DOUCWMU  ~2016-09       10:04  Matrix multiplication as composition | Chapter 4, Es…
```

Chapter 1 first, with the position shown, rather than the newest-first ordering
a channel gets. The web library does the same, and `yt get --source "linear
algebra"` pulls the whole course down in one go.

A channel and a playlist from that channel are separate sources, and a video
can belong to both without being duplicated:

```console
$ yt sources
▸ channel  3Blue1Brown                           1/151   on disk  @3blue1brown
▤ playlist Essence of linear algebra             1/16    on disk  3Blue1Brown
```

`yt channels` and `yt playlists` narrow that list to one kind.

### Finding a creator's playlists

You rarely know a playlist's URL by heart. Give `yt playlists` a channel and it
lists what that creator has published, marking the ones you already track:

```console
$ yt playlists @3blue1brown
resolving https://www.youtube.com/@3blue1brown/playlists …

24 playlists on 3Blue1Brown  (▤ = already tracked)

 18   Neural networks                              PLZHQObOWTQDNU6R1_67000Dx_ZCJB-3pi
 19   Essence of calculus                          PLZHQObOWTQDMsr9K-rj53DwVRMYO3t5Yr
 20   Binary, Hanoi and Sierpinski                 PLZHQObOWTQDMRtm8h9bG9P06WINNoBnCR
 21 ▤ Essence of linear algebra                    PLZHQObOWTQDPD3MizzM2xVFitgF8hE_ab

add which? numbers like 1,3-5 · a = all · enter = none
add: 19,20

[1/2] Essence of calculus
added playlist Essence of calculus (3Blue1Brown) — 12 videos catalogued (12 new). Nothing downloaded yet.
[2/2] Binary, Hanoi and Sierpinski
added playlist Binary, Hanoi and Sierpinski (3Blue1Brown) — 3 videos catalogued (3 new). Nothing downloaded yet.
```

Nothing is tracked until you say so — a large channel can have dozens of
playlists, and you almost never want all of them, so the prompt takes just the
numbers you want: `19,20`, a range like `3-5`, `a` for all, or a bare Enter to
walk away having added nothing. Video counts aren't shown in the list because
counting would mean opening every playlist; each one reports its count as it is
added.

To skip the prompt — in a script, or when you already know the numbers — pass
them up front:

```console
$ yt playlists @3blue1brown --add 19,20
```

`--add` also takes `all`, and `--limit N` caps how much of each playlist gets
catalogued. Without a terminal to prompt on, `yt playlists <creator>` just
prints the list.

---

## Sorting

Every view arrives in the order that suits it — a playlist in its curated
order, a collection in yours, everything else newest-first. `--sort` overrides
that when you want a different question answered:

```console
$ yt list Chienowa --sort oldest -n 3     # start a channel from the beginning
$ yt list --sort longest                  # what's the long stuff in here?
$ yt list -c "ML basics" --sort shortest  # a 10-minute gap to fill
```

| Sort | Order |
| --- | --- |
| `default` | The view's own: curated for a playlist or collection, newest-first otherwise |
| `newest` / `oldest` | By upload date. Undated entries sort last |
| `added` | Most recently catalogued first — what showed up in the last `yt sync` |
| `title` | A–Z, case-insensitive |
| `longest` / `shortest` | By runtime |

Row numbers only appear under `default`, since they mean *position in this
playlist* — under any other sort they'd be inventing an order the source never
had.

**Remembering it.** Add `--save` and that sort sticks to that view:

```console
$ yt list Chienowa --sort oldest --save
sorted: saved for this view
$ yt list Chienowa                        # still oldest-first
```

The preference lives in the catalog, keyed to one channel, playlist or
collection — so a course you work through front-to-back stays that way while
the rest of your library stays newest-first. Saving against no particular view
(`yt list --sort title --save`) sets the fallback for every view that hasn't
chosen its own. `--sort default --save` clears a view's setting.

The web library's **sort dropdown** is the same setting: change it there and
the terminal agrees, and vice versa. Switching sources in the dropdown loads
that view's own remembered order. Its first entry is named for the view you are
in — *Playlist order (the author's)* on a playlist, *Collection order (yours)*
on a collection — so the running order the author published is always one pick
away from a date sort.

---

## Collections

Playlists come from YouTube. Collections are yours — any videos, from any
channel or playlist, in an order you control. This is the study-queue feature.

```console
$ yt collect new "ML basics"
created collection ML basics

$ yt collect add "ML basics" --source "linear algebra"    # a whole course at once
+16 from Essence of linear algebra → ML basics

$ yt collect add "ML basics" "cross-entropy"              # and one from elsewhere
+ But what is cross-entropy? | Compression is Intelligence Part 2 → ML basics
```

Reorder with `up` / `down` (add `--by N` to move several places at once), and
`yt collect show` prints the current order:

```console
$ yt collect up "ML basics" "cross-entropy" --by 20
  1 ○  GlYgs6v2YfU  ~2026-08       33:51  But what is cross-entropy? | Compression is Intell…
  2 ○  fNk_zzaMoSs  ~2016-09        9:52  Vectors | Chapter 1, Essence of linear algebra
```

| | |
| --- | --- |
| `yt collect` | list your collections |
| `yt collect new <name>` | create one |
| `yt collect show <name>` | print it in order |
| `yt collect add <name> <id\|phrase>` | add a video; or `--source <ch\|playlist>` for all of one |
| `yt collect rm <name> <id\|phrase>` | remove a video (the file is untouched) |
| `yt collect up\|down <name> <id\|phrase>` | reorder, `--by N` for bigger jumps |
| `yt collect drop <name>` | delete the collection; videos and files stay |

Collections compose with everything else — `yt list -c "ML basics"` to browse
one, `yt get -c "ML basics"` to download everything in it that isn't on disk
yet, and a **Collections** group in the web library's picker.

Dropping a collection or forgetting a source never deletes downloaded files.

---

## Keeping up with new uploads

`yt sync` re-indexes tracked channels. It only ever touches metadata:

```console
$ yt sync
✓ ▸ 3Blue1Brown                        151 catalogued  +143 new
✓ ▤ Essence of linear algebra           16 catalogued  no change

143 new video(s) across 2 source(s).
```

`▸` is a channel, `▤` a playlist. Add `--show-new` to print the new titles, or
a name to sync just one source. Note that `sync` indexes the *whole* source —
if you first used `yt add --limit 20`, the catalogue will grow past 20. That's
intended; metadata is nearly free. A full sync also drops videos that were
removed from a playlist upstream; a `--limit` run never prunes, since it hasn't
seen the tail.

Nightly, via cron:

```cron
0 7 * * *  cd /path/to/repo && ./yt sync
```

To pull files down automatically too, chain a fetch — `./yt sync && ./yt get
--latest 2` for the newest couple per run, or `./yt get --starred` if you'd
rather stay in control of what lands on disk.

---

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

---

## About the dates

Flat channel listings carry no publish date. Asking yt-dlp to approximate one
derives it from the "7 months ago" label, so the day-of-month is noise and the
result can be weeks off — in testing, a `~2026-08` estimate turned out to be
`2026-07-16`. Estimates therefore display as `~2026-07`, month precision with
the day withheld, and never as an exact date.

A date becomes exact once the video is downloaded, or when you ask directly:

```bash
yt info "cross-entropy" --refresh    # pulls exact metadata, prints the description
```

After that it displays in full, and a later approximation can't overwrite it.

---

## Command reference

| Command | What it does |
| --- | --- |
| `yt add <@handle\|url\|PL…>` | Track a channel or playlist and catalog it. `--limit N` for just the newest N. |
| `yt sync [source]` | Refresh catalogs; never downloads. `--show-new`, `--limit N`. |
| `yt list [source]` | Browse. `-c COLLECTION`, `-q TEXT`, `-n N`, `--downloaded`, `--missing`, `--starred`, `--unwatched`, `--sort KEY [--save]`. |
| `yt get <id\|phrase>` | Download. Also `--starred`, `--latest N`, `--source X`, `-c COLLECTION`, `--audio`. |
| `yt collect …` | Your own collections — see [Collections](#collections). |
| `yt watch <id\|phrase>` | Play in mpv/vlc, downloading first if needed. `--mark` marks it watched. |
| `yt star <id\|phrase>` | Toggle a star. `--on` / `--off` to force. |
| `yt rm <id\|phrase>` | Delete the file, keep the catalog entry. `-y` skips the prompt. |
| `yt info <id\|phrase>` | Details and description. `--refresh` re-fetches from YouTube. |
| `yt status` | Counts and disk use; also reconciles the catalog with what's on disk. |
| `yt serve` | The web library. `-p PORT`, `--no-open`, `-v`. |
| `yt sources` | List channels and playlists with on-disk counts. `--kind channel\|playlist`. |
| `yt channels` / `yt playlists` | The same list, narrowed to one kind. |
| `yt playlists <@handle\|url>` | List a creator's playlists and pick the ones to track by number. `--add 1,3-5\|all` skips the prompt. |
| `yt forget <source>` | Stop tracking. Downloaded files and collections stay. `-y` skips the prompt. |
| `yt config [--init]` | Show settings, or write a config file to edit. |
| `yt block` | How to block youtube.com without breaking downloads. |

---

## Config

`yt config --init` writes `~/.config/ytlocal/config.json`:

| Key | Default | Notes |
| --- | --- | --- |
| `media_dir` | `~/Videos/yt` | One subdirectory per channel. |
| `max_height` | `1080` | Prefers mp4/m4a so the browser plays it without transcoding. |
| `sub_langs` | `en,es` | Keep these exact. `en.*` also matches every auto-translated track — dozens of requests per video and a quick 429 from YouTube. |
| `port` | `8420` | Used by `yt serve` unless `-p` overrides it. |
| `player` | auto | mpv → vlc → xdg-open. |
| `ytdlp_args` | `[]` | Appended to every call, e.g. `["--cookies-from-browser","firefox"]`. |

`YTLOCAL_MEDIA`, `YTLOCAL_PORT`, `YTLOCAL_DATA`, and `YTLOCAL_CONFIG` override
at the environment level — handy for running a throwaway second library.

The catalog is plain SQLite at `~/.local/share/ytlocal/catalog.db`; query it
directly if you want something the CLI doesn't offer.

---

## Troubleshooting

**A download suddenly fails.** Upgrade yt-dlp first — YouTube changes break
extractors regularly, and that's why it's a separate binary here:

```bash
uv tool upgrade yt-dlp
```

**`HTTP Error 429: Too Many Requests`.** You're being rate-limited. If you
widened `sub_langs` to something like `en.*`, narrow it back — wildcards match
every auto-translated track, which is dozens of requests per video. Otherwise
wait a while, or add `["--sleep-requests","2"]` to `ytdlp_args`.

**Members-only or age-restricted videos.** Point yt-dlp at your browser
cookies via `ytdlp_args`: `["--cookies-from-browser","firefox"]`.

**Files deleted outside the tool.** Run `yt status` — it reconciles the catalog
with what's actually on disk and reports how many entries it cleared.

**Port already in use.** `yt serve -p 9001`, or set `port` in the config.

**Video won't play in the browser.** Rare, but a source with no mp4 variant can
end up in a codec Firefox won't decode. `yt watch <id>` plays it in mpv
regardless, which handles anything.

---

## Notes

Subtitles are fetched in a second, best-effort pass *after* the video lands, so
a rate-limit on subtitles can't throw away a finished download. Deleting a
video file never deletes its catalog entry. The catalog schema migrates itself
in place, so pulling a newer version won't cost you your library — download
state, stars and watch progress are keyed on video id and survive untouched.

Earlier versions filed a playlist under its owning channel's id, which merged
the two into one source. Existing catalogs are repaired automatically on next
run: the playlist is re-keyed and split back out.
