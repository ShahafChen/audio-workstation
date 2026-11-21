# 🎚 Audio Workstation

A free, self-hosted alternative to Moises that runs in one Docker container.
Paste a YouTube link, and it downloads the song as a high-quality MP3 and splits it into separate tracks: vocals, drums, bass, guitar, piano and other.
Then you open the song in your browser to mix the tracks and slow them down for practice.

It does what the StemDeck desktop app does, built on the same open-source engines:

- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** downloads from YouTube and YouTube Music.
- **[Demucs](https://github.com/facebookresearch/demucs)** is Meta's AI model that separates a song into tracks.

Everything runs on your machine. Nothing is uploaded anywhere.

---

## Contents

1. [Quick start](#quick-start)
2. [Using it](#using-it)
3. [Configuration](#configuration)
4. [Where your files live](#where-your-files-live)
5. [Monitor page](#monitor-page)
6. [Everyday commands](#everyday-commands)
7. [Troubleshooting](#troubleshooting)
8. [How it works](#how-it-works)
9. [yt-dlp settings used](#yt-dlp-settings-used)
10. [Legal note](#legal-note)

---

## Quick start

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) (macOS, Windows) or Docker Engine with the Compose plugin (Linux).

```bash
git clone https://github.com/ShahafChen/audio-workstation.git
cd audio-workstation
docker compose up -d --build
```

Open **http://localhost:8080**.

The first build takes several minutes because it downloads PyTorch.
The first split downloads the AI model once, about 80 MB.

> **Docker Desktop memory:** splitting a song needs about 3–4 GB of RAM.
> Make sure Docker Desktop has at least 6 GB in *Settings → Resources → Memory*.

---

## Using it

### Download a song, an album or a playlist

Paste a link into the box on the **Library** page and press **Download**. Any of these work:

| Link type | Example | Result |
|---|---|---|
| Single video | `https://www.youtube.com/watch?v=…` | One song |
| YouTube Music song | `https://music.youtube.com/watch?v=…` | One song with full tags |
| Album | `https://music.youtube.com/playlist?list=OLAK5uy_…` or `https://music.youtube.com/browse/MPREb_…` | Every track, plus a collection named after the album |
| Playlist | `https://www.youtube.com/playlist?list=…` | Every video, plus a collection named after the playlist |

Two options sit under the link box:

- **Split into tracks** (on by default). Turn it off to only download the MP3. You can split it later from the song page.
- **Add to** a collection. Pick one of your collections and every downloaded song lands in it. With *no collection*, an album or playlist link creates a collection named after the album or playlist.

Each song is downloaded at the best audio quality YouTube offers and saved as a 320 kbps MP3.
Only the audio stream is fetched; no video file is ever kept (see [yt-dlp settings used](#yt-dlp-settings-used)).
The video thumbnail is embedded as cover art.
Songs already in your library are skipped, so re-running an album link only fetches what is missing.

### Song details (metadata)

The app fills the MP3 tags (title, artist, album, year, track number) automatically when it can:

- **YouTube Music links give the best results.** They carry real artist, album, year and track-number data.
- **Plain YouTube videos** only have a video title. The app splits titles like `Artist - Song (Official Video)` into artist and title and drops the "(Official Video)" part.
- **Anything missing or wrong:** press **Edit** next to the song. Your changes are written into the MP3 file's tags too, so they show up in any music player.
- **Searchable dropdowns:** the Artist, Album and Year fields suggest every value already in your library as you type, and Genre suggests the 192 standard MP3 (ID3) genres plus any genre you typed before. You can always type a new value instead.

To find an album link, search for the album on [music.youtube.com](https://music.youtube.com), open it, and copy the URL from the address bar.

### Play and practice

Click a song title to open its page.

- **Play** starts all tracks at the same moment and keeps them locked together.
- **Volume per track:** each track has its own slider from 0% to 100% and a **mute** box. Mute the vocals for karaoke, or solo the bass by muting the others.
- **Original** is the full mix. It starts at 0% when tracks exist, so you hear only the separate tracks.
- **Speed** goes from 0.25x to 1.5x in steps of 0.05x. Use the dropdown or the − and + buttons. The pitch stays the same when you slow down.
- **Reset mix** puts every track back to 100%, unmutes everything, and sets the speed to 1.0x.
- **Download backing track** mixes the tracks exactly as you set them (volumes and mutes) into one MP3 and saves it to your computer. Mute the vocals and you get a karaoke version; keep only drums and bass and you get a rhythm section to play over. Speed is not applied to the file.
- **Space** plays and pauses. The bar under the buttons seeks.
- **Split** / **Split again** runs the separation, for example for a song downloaded without splitting, or after you switch to a better model.
- **Download MP3** saves the original song.
- **Delete song** removes the song, its tracks and its entries in every collection. This is the only place a song can be deleted.

### Collections

Collections group songs, like playlists. A song can be in any number of collections.

- The list on the left of the Library page shows **All songs**, then every collection with its song count, then **+ New collection**.
- Click a collection to see only its songs. **Delete collection** appears at the top while one is selected.
- **Collections** next to a song opens a small window with a checkbox per collection. Tick to add, untick to remove.
- The **Add to** dropdown under the download box puts new downloads straight into a collection.

Deleting a collection never deletes songs.
On disk, a collection is just a folder of shortcuts (symlinks) pointing at the song folders.

---

## Configuration

**Everything is configured in one file: [`.env`](.env).**
Edit it, then apply the change:

```bash
docker compose up -d --build
```

| Setting | Default | What it does |
|---|---|---|
| `PORT` | `8080` | Port for the web UI. |
| `BIND_ADDRESS` | `127.0.0.1` | `127.0.0.1` means only this computer can open the UI. `0.0.0.0` lets phones and other devices on your network open it. There is no login, so only use `0.0.0.0` on a network you trust. |
| `LIBRARY` | `audio-workstation-library` | Where songs are stored. See [Where your files live](#where-your-files-live). |
| `MEMORY_LIMIT` | `6g` | Maximum RAM for the container. |
| `MP3_BITRATE` | `320` | MP3 quality in kbps for the original and the tracks. |
| `YTDLP_AUTO_UPDATE` | `true` | Updates yt-dlp each time the container starts. YouTube changes often and old versions stop working, so keep this on. |
| `SPLIT_MODEL` | `htdemucs_6s` | Which AI model splits songs. See below. |
| `SPEED_MIN` | `0.25` | Slowest speed in the speed menu. |
| `SPEED_MAX` | `1.5` | Fastest speed in the speed menu. |
| `SPEED_STEP` | `0.05` | Gap between speed choices. |
| `SPEED_DEFAULT` | `1.0` | Speed selected when a song page opens. |

### Split models

| `SPLIT_MODEL` | Tracks | Speed | Notes |
|---|---|---|---|
| `htdemucs_6s` | vocals, drums, bass, guitar, piano, other | normal | Default. The guitar and piano tracks are less clean than the others. |
| `htdemucs` | vocals, drums, bass, other | a bit faster | Guitar and piano end up in "other". |
| `htdemucs_ft` | vocals, drums, bass, other | about 4x slower | Best quality for 4 tracks. |

Changing the model affects new splits only. To redo an existing song, open it and press **Split again**.

On a modern laptop CPU, the default model takes roughly one to three minutes per song.

---

## Where your files live

Every song gets its own folder:

```
library/
├── songs/
│   └── The Beatles - Come Together/
│       ├── original.mp3        ← full song, tagged, with cover art
│       ├── cover.jpg
│       ├── meta.json           ← title, artist, album, source URL…
│       └── stems/
│           ├── vocals.mp3
│           ├── drums.mp3
│           ├── bass.mp3
│           ├── guitar.mp3
│           ├── piano.mp3
│           └── other.mp3
├── collections/
│   └── Abbey Road/
│       └── The Beatles - Come Together → ../../songs/The Beatles - Come Together
├── .models/                    ← downloaded AI models (cache)
└── .values.json                ← every artist/album/year/genre in the library, for the edit dropdowns
```

The `LIBRARY` setting in `.env` decides where that `library/` folder is.

**Option 1: inside Docker (default).**
`LIBRARY=audio-workstation-library` stores everything in a Docker-managed volume.
Nothing to set up, but the files are not visible in Finder or Explorer.
They survive restarts and rebuilds. They are deleted only by `docker compose down -v`.

**Option 2: shared with your computer.**
Set `LIBRARY` to a folder path and the files appear on your computer, ready to use in any music player or DAW:

```bash
LIBRARY=./library                          # a folder next to docker-compose.yml
LIBRARY=/Users/you/Music/AudioWorkstation  # any absolute path (macOS)
LIBRARY=/home/you/Music/AudioWorkstation   # any absolute path (Linux)
```

The folder is created if it does not exist.
On Docker Desktop for macOS, folders under `/Users` are shared by default.

> Switching from option 1 to option 2 does not move existing songs. Copy them out first:
> `docker run --rm -v audio-workstation-library:/from -v "$PWD/library":/to alpine cp -a /from/. /to/`

---

## Monitor page

**Monitor** in the top bar shows:

- **Library:** total size, number of songs, tracks and collections, and the size of the model cache.
- **Disk:** free and used space where the library is stored.
- **Container memory:** current use against the `MEMORY_LIMIT`.
- **CPU load:** 1, 5 and 15 minute averages, and how many jobs are running, queued or failed.
- **Jobs:** the 10 most recent downloads and splits, with live progress and full error text for failures. **View all jobs** shows the whole list. **Delete all jobs** clears the history and cancels anything still queued; a running job finishes.
- **Settings:** the active configuration and the versions of yt-dlp, Demucs and PyTorch.

Job history lives in memory and resets when the container restarts.
Songs that were downloaded but not split yet are re-queued automatically on startup.

---

## Everyday commands

```bash
docker compose up -d --build     # start, or apply .env changes
docker compose logs -f           # watch logs
docker compose restart           # restart (also updates yt-dlp)
docker compose down              # stop (your songs are kept)
docker compose down -v           # stop AND delete the Docker volume with all songs (option 1 only)
git pull && docker compose up -d --build   # update the app
```

Run the built-in self-check:

```bash
docker compose run --rm audio-workstation python -m tests.test_core
```

---

## Troubleshooting

**A download fails with "Sign in to confirm you're not a bot" or "HTTP Error 403".**
YouTube changed something. Restart the container to pull the newest yt-dlp: `docker compose restart`.
If that is not enough, wait a day for a yt-dlp release and restart again.

**A split fails, or the container restarts in the middle of one.**
It most likely ran out of memory. Raise `MEMORY_LIMIT` in `.env` and the memory in Docker Desktop settings, then run `docker compose up -d`.

**Tracks drift apart or crackle at very slow speeds.**
The browser does the time-stretching. Chrome and Edge give the best results. Firefox may mute audio below 0.25x.

**My phone cannot open the page.**
Set `BIND_ADDRESS=0.0.0.0` in `.env`, run `docker compose up -d`, and open `http://<your-computer-ip>:8080`.

**Port 8080 is already in use.**
Change `PORT` in `.env`.

**Album tracks have no album name.**
Plain YouTube playlists carry no album data. Use the album link from music.youtube.com, or fill in the details with **Edit**.

---

## How it works

```
Browser ──HTTP──▶ FastAPI (one container) ──▶ job worker ──▶ yt-dlp  (download + MP3 + cover art)
                     │                            └────────▶ Demucs  (split into tracks)
                     └── serves /media/… straight from the library folder
```

- One Python process serves the web pages, the JSON API and the audio files.
- A single background worker runs one job at a time, so a big album never overloads the machine.
- The song page loads every track as its own audio element and routes each through a volume control.
  A small loop keeps all tracks locked to the first one.
- There is no database. The folders on disk are the source of truth.

Developer documentation, including the API and how to add features, is in [docs/architecture.md](docs/architecture.md).

---

## yt-dlp settings used

All downloading is done by [yt-dlp](https://github.com/yt-dlp/yt-dlp) through its Python API, in `app/jobs.py` (`download()`). These are the options it is called with:

| Option | Value | Why |
|---|---|---|
| `format` | `bestaudio/best` | Fetch the best audio-only stream. Only if a video has no separate audio stream does it fall back to the best combined stream, which is then converted to audio. |
| `outtmpl` | `/library/.incoming/<job>/<video id>.<ext>` | Downloads land in a temporary folder that is deleted when the job ends, even on failure. |
| `writethumbnail` | `true` | Save the video thumbnail so it can become cover art. |
| `postprocessors` → `FFmpegExtractAudio` | `preferredcodec: mp3`, `preferredquality: MP3_BITRATE` (default 320) | Convert the downloaded stream to MP3 at the bitrate from `.env`. |
| `postprocessors` → `FFmpegThumbnailsConvertor` | `format: jpg`, `when: before_dl` | Turn the WebP thumbnail into `cover.jpg`. |
| `postprocessors` → `EmbedThumbnail` | `already_have_thumbnail: true` | Embed the cover inside the MP3 and keep the separate `cover.jpg`. |
| `keepvideo` | `false` | Delete the downloaded source stream once the MP3 exists. The video is never stored. |
| `ignoreerrors` | `true` | One unavailable track in an album or playlist does not fail the rest. |
| `match_filter` | skip when the video id is already in the library | Re-running an album link only fetches missing songs. |
| `progress_hooks` | internal | Feeds the progress bar on the Monitor page. |
| `quiet`, `noprogress` | `true` | Keep the container log readable. |

The app reads these fields from the information yt-dlp returns for each video, to fill the song's tags:
`track` or `title` (title), `artist` / `artists` / `uploader` / `channel` (artist; a trailing " - Topic" is removed), `album`, `release_year` or `upload_date` (year), `track_number` or the playlist position (track number), `genre`, `webpage_url` (source link), `id` (used to detect duplicates), `duration`, and the playlist `title` (name of the auto-created collection).

Two things outside the options list also matter:

- `YTDLP_AUTO_UPDATE=true` in `.env` runs `pip install -U yt-dlp` on every container start, because YouTube changes often.
- The image contains the [Deno](https://deno.com) JavaScript runtime, which yt-dlp uses to solve YouTube's player challenges.

---

## Legal note

Download only content you have the right to download.
Saving copyrighted music from YouTube may break YouTube's Terms of Service or copyright law where you live.
This project is meant for personal practice with music you own or that is freely licensed.
