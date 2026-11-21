# Architecture and developer guide

Read this before changing the code. It covers the layout, the data on disk, the API and the usual ways to add a feature.

## Layout

```
.env                  ← the single user config file (read by compose and passed into the container)
docker-compose.yml    ← one service; LIBRARY is a volume name or host path mounted at /library
Dockerfile            ← python:3.11-slim + ffmpeg + deno (for yt-dlp) + CPU torch + requirements
requirements.txt
app/
  main.py             ← FastAPI routes, request models, /api/system monitor, static pages
  jobs.py             ← in-memory job queue + single worker thread; download(), split(), mixdown()
  library.py          ← all filesystem logic: song folders, meta.json + ID3 tags, collections (symlinks), values cache
  static/
    common.js         ← api() fetch helper, formatting, shared header
    style.css         ← all styles; light/dark via prefers-color-scheme
    index.html        ← Library: download form (split + collection options), collections sidebar + dialog, metadata editor
    song.html         ← Player: per-track volume, speed, sync loop
    monitor.html      ← Monitor: storage, memory, CPU, jobs, active settings
tests/test_core.py    ← self-check for library + metadata logic (plain asserts, also pytest-compatible)
```

No build step for the frontend: plain HTML + vanilla JS, served as static files.

## Data model (on disk, no database)

- Song id = folder name under `/library/songs/`. It is created once from `Artist - Title` and never renamed, so collection symlinks stay valid. Editing the title only changes `meta.json` and the ID3 tags.
- `meta.json` keys: `title artist album year track genre` (user-editable), plus `source_url source_id duration split_model`.
- `source_id` is the YouTube video id and is used to skip duplicates on download.
- Stems are whatever `*.mp3` files exist in `stems/`. `library.STEM_ORDER` sets the display order.
- A collection is a folder under `/library/collections/` holding relative symlinks `../../songs/<id>`.
- `/library/.models` is the Demucs model cache (`TORCH_HOME`). `/library/.incoming/<job>` is a temporary download and mixdown area, wiped on startup.
- `/library/.values.json` caches every distinct artist/album/year plus the genre list (`mutagen._constants.GENRES`, 192 ID3 genres, merged with custom ones). `library.rebuild_values()` rewrites it after every `write_meta()` and `delete_song()`; `library.values()` reads it. The edit dialog's `<datalist>` dropdowns are filled from `/api/values`.

## Jobs

`jobs.submit(kind, target)` puts a dict in `JOBS` and on the queue. One daemon thread processes jobs in order.

- `download` (target = URL, options `split` and `collection`): yt-dlp Python API, best audio → MP3 at `MP3_BITRATE`, thumbnail → `cover.jpg` and embedded, `keepvideo=False`. For each entry it creates a song folder, writes metadata via `guess_meta()`, and submits a `split` unless `split` is false. Songs go into the chosen `collection`; without one, playlists/albums become their own collection.
- `split` (target = song id): runs `python -m demucs` as a subprocess, parses tqdm `NN%|` output for progress, moves results into `stems/`.

- `mixdown(folder, gains, out)` is not a job: `/api/songs/{id}/mix` calls it inline. It runs ffmpeg with a `volume` filter per track and `amix=normalize=0` (plain sum, which is how Demucs stems reconstruct the original), then streams the file back and deletes it.

Job state is in memory (resets on restart). `jobs.start()` re-queues songs that have `original.mp3` but no stems. `jobs.delete_jobs()` drops every non-running job; the worker skips a queued job whose id is no longer in `JOBS`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/config` | Speed range, model, storage and other active settings |
| GET | `/api/songs` | All songs with stems, collections and latest split job |
| GET | `/api/songs/{id}` | One song |
| PATCH | `/api/songs/{id}` | Update metadata (also writes ID3 tags) |
| DELETE | `/api/songs/{id}` | Delete folder and its collection links (409 while splitting) |
| POST | `/api/songs/{id}/split` | Queue a (re-)split |
| POST | `/api/songs/{id}/mix` | `{gains: {track: 0..1}}` → MP3 mixdown of the chosen tracks (file response) |
| POST | `/api/download` | `{url, split=true, collection=null}` → queue a download job |
| GET | `/api/jobs` | All jobs, newest first (the Monitor page shows 10 unless "View all") |
| DELETE | `/api/jobs` | Drop finished jobs and cancel queued ones |
| GET | `/api/values` | `{artist, album, year, genre}` lists for the edit dropdowns |
| GET | `/api/collections` | `{name: [song ids]}` |
| POST | `/api/collections` | `{name}` → create |
| DELETE | `/api/collections/{name}` | Delete (songs untouched) |
| PUT / DELETE | `/api/collections/{name}/songs/{id}` | Add / remove a song |
| GET | `/api/system` | Storage, cgroup memory, CPU load, versions, job counts, config |
| GET | `/media/{id}/...` | Raw files: `original.mp3`, `cover.jpg`, `stems/<stem>.mp3` |

Interactive API docs: `http://localhost:8080/docs`.

## Player sync (song.html)

Each track is an `HTMLAudioElement` with `preservesPitch = true`, routed `MediaElementSource → GainNode → destination`. Volume uses the GainNode because iOS ignores `audio.volume`. Each track keeps `vol` and `muted`; `applyGain()` sets the gain to `muted ? 0 : vol`. **Reset mix** restores the defaults (stems 100%, original 0%, speed 1.0). **Download backing track** posts the same `vol`/`muted` state as `gains` to `/mix`.
Every 200 ms, `sync()` compares each track to track 0: drift over 15 ms nudges that track's `playbackRate` by up to ±5%, drift over 250 ms jumps it.
If perfect sample-accurate sync is ever needed, the upgrade is decoding into `AudioBuffer`s and time-stretching in an AudioWorklet (more memory, more code).

## Adding a feature: where things go

- **New setting:** add it to `.env` with a comment, read it with `os.environ.get` in Python, expose it in `main.config()` if the UI needs it, and add a row to the README table.
- **New job type:** add a function in `jobs.py`, dispatch it in `_worker()`, and add an endpoint that calls `jobs.submit()`.
- **New per-song data:** store it in `meta.json` through `library.write_meta()`.
- **New page:** add `app/static/<page>.html`, include `common.js`, call `header()`, and add a route in `main.py` plus a link in `common.js`'s `header()`.
- **Upload local files:** create the song folder with `library.new_song_dir()`, save as `original.mp3`, call `write_meta()`, then `jobs.submit("split", id)`.
- **GPU:** install a CUDA torch in the Dockerfile and add a `deploy.resources.reservations.devices` block in compose. Demucs uses CUDA automatically when available.

## Conventions

- Keep it dependency-light: no frontend framework, no database.
- Every name from a URL goes through `library._check_name()` (no slashes, no dot-names).
- Run the self-check after changes: `docker compose run --rm audio-workstation python -m tests.test_core`.
- Update this file and the README when behavior or settings change.
