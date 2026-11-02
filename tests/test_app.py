
"""Tests for the Gradio application using mocked AI services."""

from unittest.mock import Mock

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


def test_song_is_saved_when_cover_generation_fails(
    tmp_path, monkeypatch
):
    """A successful song must survive a failed cover request."""
    monkeypatch.chdir(tmp_path)

    def fake_generate_song(**kwargs):
        return Track(
            id="cover-failure-test",
            title="Happy Pop",
            style="pop",
            mood="happy",
            duration_seconds=30,
            is_vocal=False,
            audio_path="song.mp3"
        )

    def fake_generate_cover(track):
        raise app.CoverGenerationError(
            "Cover service unavailable"
        )

    monkeypatch.setattr(
        app, "generate_song", fake_generate_song
    )
    monkeypatch.setattr(
        app, "generate_cover", fake_generate_cover
    )

    audio, cover, message = app.create_song(
        "Pop", "Happy", 30, "Instrumental"
    )

    assert audio == "song.mp3"
    assert cover is None
    assert "cover" in message.lower()

    saved = Library().get("cover-failure-test")

    assert saved is not None, (
        "Song was lost when album-cover generation failed!"
    )
    assert saved.audio_path == "song.mp3"
    assert saved.cover_path is None



def test_retry_cover_keeps_original_song(
    tmp_path, monkeypatch
):
    """Retry failed artwork without generating a new song."""
    monkeypatch.chdir(tmp_path)

    original = Track(
        id="coverless-song",
        title="Happy Pop",
        style="pop",
        mood="happy",
        duration_seconds=30,
        is_vocal=False,
        audio_path="original-song.mp3"
    )
    Library().add(original)

    attempts = []

    def fake_cover(track):
        attempts.append(track.id)

        if len(attempts) == 1:
            raise app.CoverGenerationError(
                "Temporary cover service outage"
            )

        track.cover_path = "recovered-cover.png"
        return track

    def no_new_music(*args, **kwargs):
        raise AssertionError(
            "Retry must not generate a new song!"
        )

    monkeypatch.setattr(app, "generate_cover", fake_cover)
    monkeypatch.setattr(app, "generate_song", no_new_music)

    # First retry fails, but the song survives.
    cover, message = app.retry_cover("coverless-song")
    assert cover is None
    assert Library().get("coverless-song").audio_path == (
        "original-song.mp3"
    )

    # Second retry succeeds for the SAME song.
    cover, message = app.retry_cover("coverless-song")

    assert cover == "recovered-cover.png"
    assert attempts == ["coverless-song", "coverless-song"]

    saved = Library().get("coverless-song")
    assert saved.audio_path == "original-song.mp3"
    assert saved.cover_path == "recovered-cover.png"
    assert len(Library().list()) == 1


# --- Professor QA findings: F1 (AI DJ picker must not auto-select) ---------

def test_dj_intro_requires_selected_song(tmp_path, monkeypatch):
    """Generating an intro without a chosen song is refused before any service call."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        app, "commentary_for_track",
        Mock(side_effect=AssertionError("No commentary without a selection")),
    )
    monkeypatch.setattr(
        app, "speak",
        Mock(side_effect=AssertionError("No speech without a selection")),
    )
    audio, message = app.generate_dj_intro(
        None, "Default Voice", None, ""
    )
    assert audio is None
    assert "Please select a song first" in message


def _dropdown_config(demo, elem_id=None, label=None):
    config = demo.get_config_file()
    for component in config["components"]:
        props = component.get("props", {})
        if elem_id and props.get("elem_id") == elem_id:
            return props
        if label and props.get("label") == label:
            return props
    raise AssertionError(f"dropdown {elem_id or label} not found in app config")


def test_dj_song_dropdown_starts_unselected(tmp_path, monkeypatch):
    """A non-empty DJ picker must render with NO song selected at build time."""
    monkeypatch.chdir(tmp_path)
    Library().add(
        Track("qa-f1", "First Song", "Pop", "Happy", 30, False,
              audio_path="first.mp3")
    )
    demo = app.build_app()
    props = _dropdown_config(demo, elem_id="dj-song-picker")
    assert props.get("value") is None  # omitted when None: behave as unselected
    assert props["choices"]  # the guard is reachable only when choices exist


def test_refresh_dj_songs_keeps_no_selection(tmp_path, monkeypatch):
    """Refreshing the DJ picker must not re-select a song, even with choices."""
    monkeypatch.chdir(tmp_path)
    Library().add(
        Track("qa-f1b", "Later Song", "Rock", "Sad", 45, False,
              audio_path="later.mp3")
    )
    songs, _playlist = app.refresh_dj_songs()
    assert songs["choices"] == [("Later Song", "qa-f1b")]
    assert songs["value"] is None


# --- Professor QA findings: F4 (library removal guard vs visible selection) --

def test_library_dropdown_starts_unselected(tmp_path, monkeypatch):
    """The library picker must not show a song that is not actually selected.

    The remove guard refuses an empty selection for safety; the dropdown must
    therefore render unselected instead of displaying the first saved song.
    """
    monkeypatch.chdir(tmp_path)
    Library().add(
        Track("qa-f4a", "Alpha Song", "Pop", "Happy", 30, False,
              audio_path="alpha.mp3")
    )
    Library().add(
        Track("qa-f4b", "Beta Song", "Rock", "Sad", 45, False,
              audio_path="beta.mp3")
    )
    demo = app.build_app()
    props = _dropdown_config(demo, label="Choose Any Saved Song")
    assert props.get("value") is None
    assert len(props["choices"]) == 2


# --- Professor QA findings: F2 (new songs missing from AI DJ picker) --------

def test_generated_song_appears_in_dj_refresh(tmp_path, monkeypatch):
    """A song created this session is listed by the DJ picker refresh."""
    monkeypatch.chdir(tmp_path)

    def fake_generate_song(**kwargs):
        return Track("qa-f2", "Fresh Song", "pop", "happy", 30, False,
                     audio_path="fresh.mp3")

    monkeypatch.setattr(app, "generate_song", fake_generate_song)
    monkeypatch.setattr(app, "generate_cover", lambda track: track)

    audio, _cover, message = app.create_song(
        "Pop", "Happy", 30, "Instrumental"
    )
    assert audio == "fresh.mp3" and "saved" in message.lower()

    songs, _playlist = app.refresh_dj_songs()
    assert ("Fresh Song", "qa-f2") in songs["choices"]


def _component_config(config, elem_id=None, label=None):
    for component in config["components"]:
        props = component.get("props", {})
        if elem_id and props.get("elem_id") == elem_id:
            return component
        if label and props.get("label") == label:
            return component
    raise AssertionError(f"component {elem_id or label} not found in app config")


def test_create_and_retry_refresh_the_dj_picker(tmp_path, monkeypatch):
    """After every generation attempt the DJ picker choices are refreshed.

    A song generated mid-session must be DJ-able without clicking
    Refresh Available Songs first.
    """
    monkeypatch.chdir(tmp_path)
    Library().add(
        Track("seed-1", "Seed Song", "Pop", "Happy", 30, False,
              audio_path="seed.mp3")
    )
    config = app.build_app().get_config_file()
    dj_song_id = _component_config(
        config, elem_id="dj-song-picker"
    )["id"]
    playlist_id = _component_config(
        config, label="Choose Your Playlist Songs"
    )["id"]

    by_index = config["dependencies"]
    for api_name in ("create_song", "create_song_1"):
        start = next(
            i for i, dep in enumerate(by_index)
            if dep.get("api_name") == api_name
        )
        follow_up = by_index[start + 1]
        assert follow_up["targets"] == [(None, "then")], (
            f"{api_name} has no chained follow-up event"
        )
        assert dj_song_id in follow_up["outputs"], (
            f"{api_name} does not refresh the DJ song picker"
        )
        assert playlist_id in follow_up["outputs"], (
            f"{api_name} does not refresh the DJ playlist picker"
        )


def test_demo_import_refreshes_the_dj_picker(tmp_path, monkeypatch):
    """Loading the demo songs also refreshes the AI DJ song choices."""
    monkeypatch.chdir(tmp_path)
    config = app.build_app().get_config_file()
    dj_song_id = _component_config(
        config, elem_id="dj-song-picker"
    )["id"]
    playlist_id = _component_config(
        config, label="Choose Your Playlist Songs"
    )["id"]
    demo_start = next(
        i for i, dep in enumerate(config["dependencies"])
        if dep.get("api_name") == "import_demo_tracks"
    )
    follow_ups = [
        dep for dep in config["dependencies"][demo_start + 1:]
        if dep["targets"] == [(None, "then")]
    ]
    assert any(
        dj_song_id in dep["outputs"] and playlist_id in dep["outputs"]
        for dep in follow_ups
    ), "importing demo songs does not refresh the DJ picker"


# --- Professor QA findings: F3 (no duplicate generation while in flight) -----

import threading


def test_second_generation_refused_while_in_flight(tmp_path, monkeypatch):
    """A Generate/Retry click during a running generation is blocked."""
    monkeypatch.chdir(tmp_path)
    started = threading.Event()
    release = threading.Event()
    calls = []

    def blocking_generate(**kwargs):
        calls.append(1)
        started.set()
        assert release.wait(5)
        return Track("qa-f3", "In Flight Song", "pop", "happy", 30, False,
                     audio_path="in-flight.mp3")

    monkeypatch.setattr(app, "generate_song", blocking_generate)
    monkeypatch.setattr(app, "generate_cover", lambda track: track)

    outcomes = {}

    def run_first():
        outcomes["first"] = app.create_song(
            "Pop", "Happy", 30, "Instrumental"
        )

    thread = threading.Thread(target=run_first)
    thread.start()
    try:
        assert started.wait(5), "first generation did not start"

        audio, cover, message = app.create_song(
            "Pop", "Happy", 30, "Instrumental"
        )
        assert audio is None and cover is None
        assert "already" in message.lower()
        assert len(calls) == 1, "a duplicate pipeline was spawned"
    finally:
        release.set()
        thread.join(5)

    assert not thread.is_alive()
    assert outcomes["first"][2].startswith("✅")


def test_inflight_guard_releases_after_failure(tmp_path, monkeypatch):
    """A failed generation must not leave the next attempt blocked."""
    monkeypatch.chdir(tmp_path)
    calls = []

    def failing_generate(**kwargs):
        calls.append(1)
        raise app.SongGenerationError("Music service unavailable")

    monkeypatch.setattr(app, "generate_song", failing_generate)

    _audio, _cover, message = app.create_song(
        "Pop", "Happy", 30, "Vocals"
    )
    assert "Music service unavailable" in message

    _audio, _cover, message = app.create_song(
        "Pop", "Happy", 30, "Vocals"
    )
    assert len(calls) == 2, "guard stayed locked after a failure"

