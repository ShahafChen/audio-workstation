"""Self-check for library + metadata logic. Run inside the container:
    docker compose run --rm audio-workstation python -m tests.test_core
"""
import os
import tempfile

os.environ["LIBRARY_DIR"] = tempfile.mkdtemp()

from app import library as lib  # noqa: E402
from app.jobs import guess_meta  # noqa: E402


def test_names():
    assert lib.safe_name('AC/DC: "Back"?') == "AC_DC_ _Back__"
    for bad in ["", ".", "..", "a/b", ".hidden"]:
        try:
            lib._check_name(bad)
            raise AssertionError(f"accepted {bad!r}")
        except ValueError:
            pass


def test_songs_and_collections():
    lib.init()
    a = lib.new_song_dir("Artist - Song")
    b = lib.new_song_dir("Artist - Song")
    assert (a.name, b.name) == ("Artist - Song", "Artist - Song (2)")
    (a / "stems").mkdir()
    for s in ["other", "vocals", "drums"]:
        (a / "stems" / f"{s}.mp3").touch()
    assert lib.stems(a) == ["vocals", "drums", "other"]

    lib.write_meta(a, {"title": "Song", "artist": "Artist", "source_id": "xyz"})
    assert lib.find_by_source("xyz") == a.name

    lib.add_to_collection("Faves", a.name)
    lib.add_to_collection("Faves", b.name)
    assert lib.list_collections() == {"Faves": sorted([a.name, b.name])}
    assert os.readlink(lib.COLLECTIONS / "Faves" / a.name) == f"../../songs/{a.name}"
    assert lib.song_info(a)["collections"] == ["Faves"]

    lib.delete_song(b.name)  # also removes its symlink
    assert lib.list_collections() == {"Faves": [a.name]}
    lib.remove_from_collection("Faves", a.name)
    lib.delete_collection("Faves")
    assert lib.list_collections() == {} and a.exists()


def test_guess_meta():
    music = {"id": "1", "title": "Come Together (Remastered)", "track": "Come Together", "artist": "The Beatles",
             "album": "Abbey Road", "release_year": 1969, "track_number": 1}
    assert guess_meta(music) == {"title": "Come Together", "artist": "The Beatles", "album": "Abbey Road",
                                 "year": "1969", "track": "1", "genre": ""}
    video = {"id": "2", "title": "Queen - Bohemian Rhapsody (Official Video Remastered)", "uploader": "Queen Official",
             "upload_date": "20080801"}
    m = guess_meta(video, playlist_index=4)
    assert (m["artist"], m["title"], m["year"], m["track"], m["album"]) == ("Queen", "Bohemian Rhapsody", "2008", "", "")
    topic = {"id": "3", "title": "Song", "uploader": "Band - Topic"}
    assert guess_meta(topic)["artist"] == "Band"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
