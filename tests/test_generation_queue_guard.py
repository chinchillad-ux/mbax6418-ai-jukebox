"""In-flight generation guard: request-owned lock, no shared state.

A duplicate click/request either fails to acquire the generation lock (and is
rejected immediately) or owns it and releases it in finally. There is no
shared boolean a rapid second request could corrupt.
"""

import threading

import jukebox.app as app
from jukebox.app import create_song


def test_second_generation_rejected_while_in_flight(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    started = threading.Event()
    release = threading.Event()
    calls = []

    def blocking_generate(**kwargs):
        calls.append(1)
        started.set()
        assert release.wait(5)
        from jukebox.models import Track
        return Track("qa-f3", "In Flight Song", "pop", "happy", 30, False,
                     audio_path="in-flight.mp3")

    monkeypatch.setattr(app, "generate_song", blocking_generate)
    monkeypatch.setattr(app, "generate_cover", lambda track: track)
    outcomes = {}

    def run_first():
        outcomes["first"] = create_song("Pop", "Happy", 30, "Instrumental")

    thread = threading.Thread(target=run_first)
    thread.start()
    try:
        assert started.wait(5), "first generation did not start"
        audio, cover, message = create_song("Pop", "Happy", 30, "Instrumental")
        assert audio is None and cover is None
        assert "already" in message.lower()
        assert len(calls) == 1, "a duplicate pipeline was spawned"
    finally:
        release.set()
        thread.join(5)

    assert not thread.is_alive()
    assert outcomes["first"][2].startswith("✅")


def test_lock_released_after_failure(tmp_path, monkeypatch):
    """A failed generation must not leave the next attempt blocked."""
    monkeypatch.chdir(tmp_path)

    def failing_generate(**kwargs):
        raise app.SongGenerationError("Music service unavailable")

    monkeypatch.setattr(app, "generate_song", failing_generate)

    _audio, _cover, message = create_song("Pop", "Happy", 30, "Vocals")
    assert "Music service unavailable" in message

    calls = []

    def counting_generate(**kwargs):
        calls.append(1)
        from jukebox.models import Track
        return Track("qa-r", "Next Song", "pop", "happy", 30, False,
                     audio_path="next.mp3")

    monkeypatch.setattr(app, "generate_song", counting_generate)
    monkeypatch.setattr(app, "generate_cover", lambda track: track)
    monkeypatch.setattr(app, "Library", lambda: _FakeLibrary())

    _audio, _cover, message = create_song("Pop", "Happy", 30, "Instrumental")
    assert len(calls) == 1, "guard stayed locked after a failure"


class _FakeLibrary:
    def __init__(self):
        self._tracks = []

    def list(self):
        return list(self._tracks)

    def add(self, track):
        self._tracks.append(track)
        return track
