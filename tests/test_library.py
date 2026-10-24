"""Persistence and recovery checks; no class services or user data."""
import json

import pytest

from jukebox.library import Library, LibraryError
from jukebox.models import Track


def track(track_id="one", **updates):
    return Track(id=track_id, title="Original", style="Jazz", mood="Calm",
                 duration_seconds=30, is_vocal=False, **updates)


def test_new_library_is_empty_and_missing_lookup_is_none(tmp_path):
    library = Library(tmp_path / "data/library.json")
    assert library.list() == []
    assert library.get("missing") is None
    assert not library.path.exists()


def test_add_deduplicate_update_and_reload(tmp_path):
    path = tmp_path / "data/library.json"
    library = Library(path)
    first = track(audio_path="data/songs/one.mp3", cover_path="data/covers/one.png",
                  dj_commentary="A calm jazz introduction.", dj_audio_path="data/dj/one.mp3")
    library.add(first)
    library.add(track("two"))
    first.title = "Updated title"
    library.add(first)
    assert [t.id for t in library.list()] == ["one", "two"]
    reloaded = Library(path)
    assert reloaded.list() == library.list()
    assert reloaded.get("one") == first
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_library_owns_snapshots(tmp_path):
    library = Library(tmp_path / "library.json")
    original = track()
    saved = library.add(original)
    original.title = "External change"
    saved.title = "Returned change"
    library.get("one").title = "Lookup change"
    library.list()[0].title = "List change"
    assert library.get("one").title == "Original"


@pytest.mark.parametrize("payload", ["{", "[]", '{"version": 2, "tracks": []}',
                                   '{"version": 1, "tracks": [{}]}',
                                   '{"version": 1, "tracks": null}'])
def test_corrupt_or_unsupported_library_is_not_overwritten(tmp_path, payload):
    path = tmp_path / "library.json"
    path.write_text(payload)
    with pytest.raises(LibraryError, match="could not be loaded"):
        Library(path)
    assert path.read_text() == payload


def test_duplicate_ids_in_saved_file_are_reported(tmp_path):
    path = tmp_path / "library.json"
    path.write_text(json.dumps({"version": 1, "tracks": [track().to_dict()] * 2}))
    with pytest.raises(LibraryError):
        Library(path)


@pytest.mark.parametrize("track_id", ["", "   ", None, 4])
def test_invalid_id_is_not_saved(tmp_path, track_id):
    library = Library(tmp_path / "library.json")
    with pytest.raises(LibraryError):
        library.add(track(track_id))
    assert library.list() == []


def test_failed_replace_preserves_old_disk_and_memory(tmp_path, monkeypatch):
    library = Library(tmp_path / "library.json")
    library.add(track())
    before = library.path.read_bytes()

    def fail(*args):
        raise OSError("Simulated disk failure")

    monkeypatch.setattr("jukebox.library.os.replace", fail)
    with pytest.raises(LibraryError, match="could not be saved"):
        library.add(track("two"))
    assert library.path.read_bytes() == before
    assert [t.id for t in library.list()] == ["one"]
    assert list(tmp_path.glob(".library-*.tmp")) == []


def test_unicode_lyrics_and_sample_paths_survive_restart(tmp_path):
    library = Library(tmp_path / "library.json")
    song = track(audio_path="assets/samples/one.mp3", cover_path="assets/samples/one.png")
    song.is_vocal = True
    song.lyrics = "Café lights, an original refrain"
    library.add(song)
    assert Library(library.path).get("one") == song
