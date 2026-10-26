
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



def test_dj_playlist_advances_in_correct_order(tmp_path, monkeypatch):
    """DJ introductions and songs play in the correct sequence."""
    monkeypatch.chdir(tmp_path)

    library = Library()

    for number in [1, 2]:
        song_path = f"song-{number}.mp3"
        dj_path = f"dj-{number}.mp3"

        # Create dummy audio files without calling AI services.
        (tmp_path / song_path).write_bytes(b"test song")
        (tmp_path / dj_path).write_bytes(b"test dj")

        library.add(
            Track(
                id=f"track-{number}",
                title=f"Song {number}",
                style="pop",
                mood="happy",
                duration_seconds=30,
                is_vocal=False,
                audio_path=song_path,
                dj_audio_path=dj_path
            )
        )

    # Start with the first DJ introduction.
    audio, state, message = app.start_dj_set(
        ["track-1", "track-2"]
    )

    assert audio == "dj-1.mp3"
    assert state["phase"] == "speech"

    # Advance to Song 1.
    audio, state, message = app.advance_dj_set(state)
    assert audio == "song-1.mp3"
    assert state["phase"] == "song"

    # Advance to the second DJ introduction.
    audio, state, message = app.advance_dj_set(state)
    assert audio == "dj-2.mp3"
    assert state["phase"] == "speech"

    # Advance to Song 2.
    audio, state, message = app.advance_dj_set(state)
    assert audio == "song-2.mp3"
    assert state["phase"] == "song"

    # Finish the playlist.
    audio, state, message = app.advance_dj_set(state)
    assert audio is None
    assert state["phase"] is None
    assert "complete" in message.lower()



def test_dj_intro_uses_mocked_services(tmp_path, monkeypatch):
    """Generate and save DJ speech without calling AI endpoints."""
    monkeypatch.chdir(tmp_path)

    library = Library()
    library.add(
        Track(
            id="dj-test",
            title="Happy Pop",
            style="pop",
            mood="happy",
            duration_seconds=30,
            is_vocal=False,
            audio_path="song.mp3"
        )
    )

    def fake_commentary(track):
        return f"Coming up next: {track.title}!"

    def fake_speak(text, voice_ref_path=None):
        assert text == "Coming up next: Happy Pop!"
        assert voice_ref_path is None
        return "dj-intro.mp3"

    monkeypatch.setattr(
        app, "commentary_for_track", fake_commentary
    )
    monkeypatch.setattr(app, "speak", fake_speak)

    audio, message = app.generate_dj_intro(
        "dj-test", "Default Voice", None, ""
    )

    assert audio == "dj-intro.mp3"
    assert "ready" in message.lower()

    saved = Library().get("dj-test")
    assert saved.dj_audio_path == "dj-intro.mp3"



def test_dj_generation_preserves_newly_saved_songs(
    tmp_path, monkeypatch
):
    """DJ generation must not erase songs saved while it runs."""
    monkeypatch.chdir(tmp_path)

    Library().add(
        Track(
            id="song-a",
            title="Song A",
            style="pop",
            mood="happy",
            duration_seconds=30,
            is_vocal=False,
            audio_path="song-a.mp3"
        )
    )

    def fake_commentary(track):
        # Simulate another song being saved while the
        # DJ service is generating commentary.
        Library().add(
            Track(
                id="song-b",
                title="Song B",
                style="indie",
                mood="relaxed",
                duration_seconds=30,
                is_vocal=False,
                audio_path="song-b.mp3"
            )
        )
        return "Coming up next: Song A!"

    def fake_speak(text, voice_ref_path=None):
        return "dj-a.mp3"

    monkeypatch.setattr(
        app, "commentary_for_track", fake_commentary
    )
    monkeypatch.setattr(app, "speak", fake_speak)

    audio, message = app.generate_dj_intro(
        "song-a", "Default Voice", None, ""
    )

    assert audio == "dj-a.mp3"

    saved_library = Library()

    assert saved_library.get("song-a").dj_audio_path == "dj-a.mp3"
    assert saved_library.get("song-b") is not None, (
        "DJ generation erased another saved song!"
    )


