
"""Tests for the Gradio application using mocked AI services."""

from jukebox import app
from jukebox.library import Library
from jukebox.models import Track
from jukebox.music import SongGenerationError


def test_create_song_saves_audio_and_cover(tmp_path, monkeypatch):
    """A generated song and its cover should enter the library."""
    monkeypatch.chdir(tmp_path)
    captured = {}

    def fake_generate_song(style, mood, duration_seconds, is_vocal):
        captured.update(
            style=style,
            mood=mood,
            duration=duration_seconds,
            vocal=is_vocal
        )
        return Track(
            id="test-song",
            title="Happy Pop",
            style=style,
            mood=mood,
            duration_seconds=duration_seconds,
            is_vocal=is_vocal,
            audio_path="song.mp3"
        )

    def fake_generate_cover(track):
        track.cover_path = "cover.png"
        return track

    monkeypatch.setattr(app, "generate_song", fake_generate_song)
    monkeypatch.setattr(app, "generate_cover", fake_generate_cover)

    audio, cover, message = app.create_song(
        "Pop", "Happy", 60, "Instrumental"
    )

    assert audio == "song.mp3"
    assert cover == "cover.png"
    assert "saved" in message.lower()

    assert captured == {
        "style": "pop",
        "mood": "happy",
        "duration": 60,
        "vocal": False
    }

    saved_song = Library().get("test-song")
    assert saved_song is not None
    assert saved_song.audio_path == audio
    assert saved_song.cover_path == cover


def test_song_generation_failure_shows_error(tmp_path, monkeypatch):
    """A failed generation should show an understandable message."""
    monkeypatch.chdir(tmp_path)

    def fake_failure(**kwargs):
        raise SongGenerationError("Music service unavailable")

    monkeypatch.setattr(app, "generate_song", fake_failure)

    audio, cover, message = app.create_song(
        "Pop", "Happy", 60, "Vocals"
    )

    assert audio is None
    assert cover is None
    assert "Music service unavailable" in message
