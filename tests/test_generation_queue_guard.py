"""In-flight guard must reject duplicate clicks BEFORE they enter the queue."""

import jukebox.app as app
from jukebox.app import (
    claim_generation_slot,
    create_song,
    release_generation_slot,
)


def test_second_click_is_rejected_at_claim_time():
    allowed1, _unused1, _unused2 = claim_generation_slot()
    allowed2, _unused3, _unused4 = claim_generation_slot()
    assert allowed1 is True
    assert allowed2 is False  # second click rejected at click time, not at run time
    release_generation_slot(True)


def test_rejected_click_does_not_generate_or_release():
    allowed1, _unused1, _unused2 = claim_generation_slot()
    allowed2, _unused3, _unused4 = claim_generation_slot()
    audio, cover, message = create_song("Pop", "Happy", "30", "Instrumental", allowed2)
    assert audio is None and cover is None
    assert "already in progress" in message
    # The lock must still be held by the first claim after the rejected call.
    allowed3, _unused5, _unused6 = claim_generation_slot()
    assert allowed3 is False
    release_generation_slot(True)


def test_claim_released_after_failed_generation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []

    def failing_generate(**kwargs):
        calls.append(1)
        raise app.SongGenerationError("Music service unavailable")

    monkeypatch.setattr(app, "generate_song", failing_generate)
    monkeypatch.setattr(app, "generate_cover", lambda track: track)

    allowed1, _unused1, _unused2 = claim_generation_slot()
    audio, cover, message = create_song("Pop", "Happy", "30", "Vocals", allowed1)
    assert audio is None
    assert "Music service unavailable" in message
    allowed_after, _unused3, _unused4 = claim_generation_slot()
    assert allowed_after is True  # lock released even though generation failed
    release_generation_slot(True)


def test_successful_generation_releases_slot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from jukebox.models import Track

    monkeypatch.setattr(
        app, "generate_song",
        lambda **kwargs: Track("t1", "T", "pop", "happy", 30, False, audio_path="a.mp3"),
    )
    monkeypatch.setattr(app, "generate_cover", lambda track: track)
    monkeypatch.setattr(app, "Library", lambda: _FakeLibrary())

    allowed1, _unused1, _unused2 = claim_generation_slot()
    audio, cover, message = create_song("Pop", "Happy", "30", "Instrumental", allowed1)
    assert message.startswith("✅")
    allowed_after, _unused3, _unused4 = claim_generation_slot()
    assert allowed_after is True  # released after success
    release_generation_slot(True)


class _FakeLibrary:
    def __init__(self):
        self._tracks = []

    def list(self):
        return list(self._tracks)

    def add(self, track):
        self._tracks.append(track)
        return track
