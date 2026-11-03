"""Empty-library messaging: explain the cause instead of generic guards."""

from jukebox.app import load_library, select_saved_song, remove_and_refresh


def test_load_library_explains_empty_library(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    covers, message = load_library()
    assert covers == []
    assert "no saved songs" in message.lower()
    assert "generate" in message.lower()


def test_load_library_counts_songs(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    from jukebox.models import Track
    from jukebox.library import Library
    monkeypatch.chdir(tmp_path)
    record = Track(
        id="t1", title="Test Song", style="Pop", mood="Happy",
        duration_seconds=30, is_vocal=True, lyrics="words", audio_path="a.mp3",
        cover_path="c.png",
    )
    Library().add(record)
    covers, message = load_library()
    assert covers == [("c.png", "Test Song")]
    assert "1 saved song" in message


def test_select_song_explains_empty_library(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    audio, message = select_saved_song(None)
    assert audio is None
    assert "no saved songs" in message.lower()


def test_remove_explains_empty_library(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    results = remove_and_refresh(None, [])
    assert results[0].__class__.__name__ == "str"
    assert "no saved songs" in results[0].lower()
