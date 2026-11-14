import os
import shutil
from contextlib import asynccontextmanager
from importlib.metadata import version
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import jobs
from . import library as lib

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app):
    jobs.start()
    yield


app = FastAPI(title="Audio Workstation", lifespan=lifespan)


def _song(song_id: str) -> Path:
    try:
        return lib.song_dir(song_id)
    except (KeyError, ValueError):
        raise HTTPException(404, "song not found")


def _name(name: str) -> str:
    try:
        return lib._check_name(name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ── models ──

class DownloadRequest(BaseModel):
    url: str = Field(pattern=r"^https?://", max_length=2000)


class MetaUpdate(BaseModel):
    title: str | None = Field(None, max_length=300)
    artist: str | None = Field(None, max_length=300)
    album: str | None = Field(None, max_length=300)
    year: str | None = Field(None, max_length=10)
    track: str | None = Field(None, max_length=10)
    genre: str | None = Field(None, max_length=100)


class CollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


# ── config ──

def config() -> dict:
    env = os.environ.get
    return {
        "speed": {"min": float(env("SPEED_MIN", "0.25")), "max": float(env("SPEED_MAX", "1.5")),
                  "step": float(env("SPEED_STEP", "0.05")), "default": float(env("SPEED_DEFAULT", "1.0"))},
        "split_model": jobs.MODEL,
        "mp3_bitrate": jobs.BITRATE,
        "library": env("LIBRARY", str(lib.ROOT)),
        "memory_limit": env("MEMORY_LIMIT", ""),
        "bind_address": env("BIND_ADDRESS", ""),
        "port": env("PORT", "8080"),
        "ytdlp_auto_update": env("YTDLP_AUTO_UPDATE", ""),
    }


@app.get("/api/config")
def get_config():
    return config()


# ── songs ──

def _with_status(song: dict) -> dict:
    job = next((j for j in reversed(list(jobs.JOBS.values()))
                if j["kind"] == "split" and j["target"] == song["id"]), None)
    song["job"] = job and {k: job[k] for k in ("status", "progress", "message")}
    return song


@app.get("/api/songs")
def list_songs():
    return [_with_status(s) for s in lib.list_songs()]


@app.get("/api/songs/{song_id}")
def get_song(song_id: str):
    return _with_status(lib.song_info(_song(song_id)))


@app.patch("/api/songs/{song_id}")
def update_song(song_id: str, body: MetaUpdate):
    folder = _song(song_id)
    lib.write_meta(folder, body.model_dump(exclude_none=True))
    return lib.song_info(folder)


@app.delete("/api/songs/{song_id}")
def delete_song(song_id: str):
    _song(song_id)
    if jobs.pending_split(song_id):
        raise HTTPException(409, "song is being split, try again when the job finishes")
    lib.delete_song(song_id)
    return {"ok": True}


@app.post("/api/songs/{song_id}/split")
def resplit(song_id: str):
    _song(song_id)
    if jobs.pending_split(song_id):
        raise HTTPException(409, "already queued")
    return jobs.submit("split", song_id)


# ── downloads & jobs ──

@app.post("/api/download")
def download(body: DownloadRequest):
    return jobs.submit("download", body.url)


@app.get("/api/jobs")
def list_jobs():
    return sorted(jobs.JOBS.values(), key=lambda j: j["created"], reverse=True)


@app.delete("/api/jobs/finished")
def clear_jobs():
    jobs.clear_finished()
    return {"ok": True}


# ── collections ──

@app.get("/api/collections")
def list_collections():
    return lib.list_collections()


@app.post("/api/collections")
def create_collection(body: CollectionRequest):
    return {"name": lib.create_collection(body.name)}


@app.delete("/api/collections/{name}")
def delete_collection(name: str):
    try:
        lib.delete_collection(_name(name))
    except FileNotFoundError:
        raise HTTPException(404, "collection not found")
    return {"ok": True}


@app.put("/api/collections/{name}/songs/{song_id}")
def add_to_collection(name: str, song_id: str):
    _song(song_id)
    lib.add_to_collection(_name(name), song_id)
    return {"ok": True}


@app.delete("/api/collections/{name}/songs/{song_id}")
def remove_from_collection(name: str, song_id: str):
    lib.remove_from_collection(_name(name), _name(song_id))
    return {"ok": True}


# ── system monitor ──

def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            p = Path(root, f)
            if not p.is_symlink():
                total += p.stat().st_size
    return total


def _read_int(path: str) -> int | None:
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None  # "max" (no limit) or not cgroup v2


@app.get("/api/system")
def system():
    disk = shutil.disk_usage(lib.ROOT)
    songs = [p for p in lib.SONGS.iterdir() if p.is_dir()]
    stem_count = sum(len(lib.stems(p)) for p in songs)
    load1, load5, load15 = os.getloadavg()
    return {
        "storage": {"library_bytes": _dir_size(lib.SONGS), "models_bytes": _dir_size(lib.ROOT / ".models"),
                    "disk_total": disk.total, "disk_free": disk.free,
                    "songs": len(songs), "stems": stem_count, "collections": len(lib.list_collections())},
        "memory": {"used": _read_int("/sys/fs/cgroup/memory.current"),
                   "limit": _read_int("/sys/fs/cgroup/memory.max")},
        "cpu": {"cores": os.cpu_count(), "load": [load1, load5, load15]},
        "versions": {p: version(p) for p in ("yt-dlp", "demucs", "torch")},
        "jobs": {s: sum(j["status"] == s for j in jobs.JOBS.values()) for s in ("queued", "running", "done", "error")},
        "config": config(),
    }


# ── files & pages ──

app.mount("/media", StaticFiles(directory=lib.SONGS, check_dir=False), name="media")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/song")
def song_page():
    return FileResponse(STATIC / "song.html")


@app.get("/monitor")
def monitor_page():
    return FileResponse(STATIC / "monitor.html")
