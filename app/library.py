"""On-disk library: one folder per song, collections are folders of symlinks.

/library/songs/<Song>/original.mp3, cover.jpg, meta.json, stems/<stem>.mp3
/library/collections/<Name>/<Song> -> ../../songs/<Song>
"""
import json
import os
import re
import shutil
from pathlib import Path

from mutagen._constants import GENRES
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError

ROOT = Path(os.environ.get("LIBRARY_DIR", "/library"))
SONGS = ROOT / "songs"
COLLECTIONS = ROOT / "collections"
VALUES_FILE = ROOT / ".values.json"  # cache of every artist/album/year/genre in the library, for the edit dropdowns
STEM_ORDER = ["vocals", "drums", "bass", "guitar", "piano", "other"]
META_FIELDS = ["title", "artist", "album", "year", "track", "genre"]
ID3_KEYS = {"title": "title", "artist": "artist", "album": "album", "year": "date",
            "track": "tracknumber", "genre": "genre"}


def init():
    SONGS.mkdir(parents=True, exist_ok=True)
    COLLECTIONS.mkdir(parents=True, exist_ok=True)
    if not VALUES_FILE.exists():
        rebuild_values()


def safe_name(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(text)).strip(" .")
    return text[:120] or "untitled"


def _check_name(name: str) -> str:
    # trust boundary: names come from URLs, never allow path tricks
    if not name or name in (".", "..") or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"invalid name: {name!r}")
    return name


def song_dir(song_id: str) -> Path:
    path = SONGS / _check_name(song_id)
    if not path.is_dir():
        raise KeyError(song_id)
    return path


def new_song_dir(name: str) -> Path:
    base = safe_name(name)
    path, i = SONGS / base, 2
    while path.exists():
        path, i = SONGS / f"{base} ({i})", i + 1
    path.mkdir(parents=True)
    return path


def read_meta(path: Path) -> dict:
    try:
        return json.loads((path / "meta.json").read_text())
    except (OSError, ValueError):
        return {}


def write_meta(path: Path, updates: dict) -> dict:
    meta = read_meta(path) | updates
    (path / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    tags = {k: str(v) for k, v in meta.items() if k in ID3_KEYS and v not in (None, "")}
    original = path / "original.mp3"
    if original.exists():
        try:
            id3 = EasyID3(original)
        except ID3NoHeaderError:
            id3 = EasyID3()
        for key, value in tags.items():
            id3[ID3_KEYS[key]] = value
        id3.save(original)
    rebuild_values()
    return meta


def rebuild_values() -> dict:
    found = {k: set() for k in ("artist", "album", "year", "genre")}
    for p in SONGS.iterdir():
        for key, value in read_meta(p).items():
            if key in found and value:
                found[key].add(str(value))
    values = {k: sorted(v, key=str.lower) for k, v in found.items()}
    values["genre"] = sorted(set(GENRES) | found["genre"], key=str.lower)
    VALUES_FILE.write_text(json.dumps(values, ensure_ascii=False))
    return values


def values() -> dict:
    try:
        return json.loads(VALUES_FILE.read_text())
    except (OSError, ValueError):
        return rebuild_values()


def stems(path: Path) -> list[str]:
    found = {p.stem for p in (path / "stems").glob("*.mp3")}
    return [s for s in STEM_ORDER if s in found] + sorted(found - set(STEM_ORDER))


def song_collections(song_id: str) -> list[str]:
    return sorted(c.name for c in COLLECTIONS.iterdir() if (c / song_id).is_symlink())


def song_info(path: Path) -> dict:
    return {
        "id": path.name,
        **{f: "" for f in META_FIELDS},
        **read_meta(path),
        "stems": stems(path),
        "has_original": (path / "original.mp3").exists(),
        "has_cover": (path / "cover.jpg").exists(),
        "collections": song_collections(path.name),
    }


def list_songs() -> list[dict]:
    dirs = [p for p in SONGS.iterdir() if p.is_dir() and not p.name.startswith(".")]
    return sorted((song_info(p) for p in dirs), key=lambda s: (s["artist"].lower(), s["album"].lower(),
                                                                str(s["track"]).zfill(3), s["title"].lower()))


def find_by_source(source_id: str) -> str | None:
    for p in SONGS.iterdir():
        if read_meta(p).get("source_id") == source_id:
            return p.name
    return None


def delete_song(song_id: str):
    shutil.rmtree(song_dir(song_id))
    for link in COLLECTIONS.glob(f"*/{song_id}"):
        link.unlink()
    rebuild_values()


# ── collections ──

def list_collections() -> dict[str, list[str]]:
    return {c.name: sorted(l.name for l in c.iterdir() if l.is_symlink() and l.exists())
            for c in sorted(COLLECTIONS.iterdir()) if c.is_dir()}


def create_collection(name: str) -> str:
    name = _check_name(safe_name(name))
    (COLLECTIONS / name).mkdir(exist_ok=True)
    return name


def delete_collection(name: str):
    folder = COLLECTIONS / _check_name(name)
    for link in folder.iterdir():
        link.unlink()  # only symlinks live here; the songs themselves are untouched
    folder.rmdir()


def add_to_collection(name: str, song_id: str):
    song_dir(song_id)
    folder = COLLECTIONS / _check_name(name)
    folder.mkdir(exist_ok=True)
    link = folder / song_id
    if not link.is_symlink():
        link.symlink_to(Path("..", "..", "songs", song_id))  # relative, so it also works on the host


def remove_from_collection(name: str, song_id: str):
    link = COLLECTIONS / _check_name(name) / _check_name(song_id)
    if link.is_symlink():
        link.unlink()
