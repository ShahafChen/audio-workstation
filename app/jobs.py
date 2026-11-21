"""Background job queue: download (yt-dlp) and split (Demucs), one job at a time."""
import itertools
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

import yt_dlp

from . import library as lib

MODEL = os.environ.get("SPLIT_MODEL", "htdemucs_6s")
BITRATE = os.environ.get("MP3_BITRATE", "320")

# shortcut: job history is in memory and resets on container restart; unfinished splits are re-queued at startup
JOBS: dict[str, dict] = {}
_queue: queue.Queue = queue.Queue()
_ids = itertools.count(1)


def submit(kind: str, target: str, **options) -> dict:
    job = {"id": str(next(_ids)), "kind": kind, "target": target, "status": "queued",
           "progress": 0, "message": "", "created": time.time(), "finished": None, **options}
    JOBS[job["id"]] = job
    _queue.put(job)
    return job


def delete_jobs():
    """Forget finished jobs and cancel queued ones; a running job keeps going."""
    for jid in [j["id"] for j in JOBS.values() if j["status"] != "running"]:
        del JOBS[jid]


def pending_split(song_id: str) -> bool:
    return any(j["kind"] == "split" and j["target"] == song_id and j["status"] in ("queued", "running")
               for j in JOBS.values())


def _worker():
    while True:
        job = _queue.get()
        if job["id"] not in JOBS:
            continue  # deleted while queued
        job["status"] = "running"
        try:
            (download if job["kind"] == "download" else split)(job)
            job["status"], job["progress"] = "done", 100
        except Exception as exc:  # keep the worker alive; the error shows in the monitor page
            job["status"], job["message"] = "error", str(exc)[-2000:]
        job["finished"] = time.time()


def start():
    lib.init()
    shutil.rmtree(lib.ROOT / ".incoming", ignore_errors=True)
    for song in lib.list_songs():
        if song["has_original"] and not song["stems"]:
            submit("split", song["id"])
    threading.Thread(target=_worker, daemon=True).start()


# ── metadata ──

def guess_meta(entry: dict, playlist_index: int | None = None) -> dict:
    """Best-effort tags from yt-dlp info. YouTube Music gives real tags; plain videos need title parsing."""
    title = entry.get("track") or entry.get("title") or entry.get("id", "")
    artist = entry.get("artist") or ", ".join(entry.get("artists") or [])
    if not entry.get("track") and " - " in title:
        artist_part, title = title.split(" - ", 1)
        artist = artist or artist_part
    title = re.sub(r"\s*[\(\[](official|lyric|audio|video|hd|4k|visualizer)[^\)\]]*[\)\]]", "", title,
                   flags=re.I).strip() or title
    artist = artist or (entry.get("uploader") or entry.get("channel") or "").removesuffix(" - Topic")
    year = entry.get("release_year") or (entry.get("upload_date") or "")[:4]
    track = entry.get("track_number") or (playlist_index if entry.get("album") else "")
    return {"title": title.strip(), "artist": artist.strip(), "album": entry.get("album") or "",
            "year": str(year or ""), "track": str(track or ""), "genre": entry.get("genre") or ""}


# ── download ──

def download(job: dict):
    url = job["target"]
    incoming = lib.ROOT / ".incoming" / job["id"]
    incoming.mkdir(parents=True, exist_ok=True)

    def on_progress(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                job["progress"] = int(100 * d.get("downloaded_bytes", 0) / total)
            job["message"] = f"Downloading: {d.get('info_dict', {}).get('title', '')}"
        elif d["status"] == "finished":
            job["message"] = "Converting to MP3"

    def skip_existing(info, *, incomplete):
        if not incomplete and info.get("id") and lib.find_by_source(info["id"]):
            return "already in library"
        return None

    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(incoming / "%(id)s.%(ext)s"),
        "writethumbnail": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": BITRATE},
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
            {"key": "EmbedThumbnail", "already_have_thumbnail": True},
        ],
        "match_filter": skip_existing,
        "keepvideo": False,  # the source stream is deleted once the MP3 is extracted
        "ignoreerrors": True,  # one unavailable album track must not fail the whole album
        "progress_hooks": [on_progress],
        "quiet": True,
        "noprogress": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        if not info:
            raise RuntimeError("yt-dlp could not read this URL")
        is_playlist = "entries" in info
        entries = list(info.get("entries") or []) if is_playlist else [info]

        added = []
        for index, entry in enumerate(entries, 1):
            mp3 = entry and incoming / f"{entry['id']}.mp3"
            if not mp3 or not mp3.exists():
                continue  # skipped (already in library) or failed
            meta = guess_meta(entry, entry.get("playlist_index") or index)
            folder = lib.new_song_dir(f"{meta['artist']} - {meta['title']}" if meta["artist"] else meta["title"])
            shutil.move(mp3, folder / "original.mp3")
            cover = incoming / f"{entry['id']}.jpg"
            if cover.exists():
                shutil.move(cover, folder / "cover.jpg")
            lib.write_meta(folder, meta | {"source_url": entry.get("webpage_url") or url,
                                           "source_id": entry["id"], "duration": entry.get("duration")})
            added.append(folder.name)
            if job.get("split", True):
                submit("split", folder.name)

        # a collection chosen by the user wins; otherwise an album/playlist becomes its own collection
        collection = job.get("collection") or (
            is_playlist and added and lib.create_collection((info.get("title") or "Playlist").removeprefix("Album - ")))
        for song_id in added if collection else []:
            lib.add_to_collection(collection, song_id)
        skipped = len(entries) - len(added)
        job["message"] = f"Added {len(added)} song(s)" + (f", skipped {skipped} (already in library or unavailable)" if skipped else "")
        if not added and not skipped:
            raise RuntimeError("nothing was downloaded")
    finally:
        shutil.rmtree(incoming, ignore_errors=True)


# ── split ──

def split(job: dict):
    folder = lib.song_dir(job["target"])
    work = folder / ".split"
    shutil.rmtree(work, ignore_errors=True)
    cmd = [sys.executable, "-m", "demucs", "-n", MODEL, "--mp3", "--mp3-bitrate", BITRATE,
           "-o", str(work), "--filename", "{stem}.{ext}", str(folder / "original.mp3")]
    job["message"] = f"Splitting with {MODEL}"
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    tail = ""
    for chunk in iter(lambda: proc.stdout.read(256), b""):
        tail = (tail + chunk.decode(errors="replace"))[-4000:]
        percents = re.findall(r"(\d+)%\|", tail)
        if percents:
            job["progress"] = int(percents[-1])
    if proc.wait() != 0:
        shutil.rmtree(work, ignore_errors=True)
        raise RuntimeError(f"demucs failed:\n{tail}")

    out = work / MODEL
    shutil.rmtree(folder / "stems", ignore_errors=True)
    (folder / "stems").mkdir()
    for f in out.glob("*.mp3"):
        shutil.move(f, folder / "stems" / f.name)
    shutil.rmtree(work, ignore_errors=True)
    lib.write_meta(folder, {"split_model": MODEL})
    job["message"] = f"{len(lib.stems(folder))} tracks"


# ── mixdown (runs inline, a few seconds) ──

def mixdown(folder, gains: dict[str, float], out) -> None:
    """Sum the chosen tracks at the given volumes (0..1) into one MP3. Demucs stems sum back to the original."""
    inputs = [(folder / ("original.mp3" if name == "original" else f"stems/{name}.mp3"), g)
              for name, g in gains.items() if g > 0]
    if not inputs:
        raise ValueError("every track is muted")
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for path, _ in inputs:
        cmd += ["-i", str(path)]
    chain = "".join(f"[{i}:a]volume={g:.3f}[a{i}];" for i, (_, g) in enumerate(inputs))
    chain += "".join(f"[a{i}]" for i in range(len(inputs))) + f"amix=inputs={len(inputs)}:normalize=0[out]"
    cmd += ["-filter_complex", chain, "-map", "[out]", "-b:a", f"{BITRATE}k", str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-1000:]}")
