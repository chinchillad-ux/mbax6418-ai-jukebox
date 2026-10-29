import json
from pathlib import Path
import pytest
from jukebox import music
from jukebox.config import Settings

SETTINGS = Settings("key", "http://qwen:9001/v1", "x", "http://ace:9007", "x", "qwen", "x", "ace", "x")

def wrapped(data): return json.dumps({"code": 200, "error": None, "data": data}).encode()

@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(music, "load_settings", lambda: SETTINGS)
    monkeypatch.setattr(music, "_validate_audio", lambda path, duration: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(music, "_creative_title", lambda *args, **kwargs: "Silver Horizon")

def test_instrumental_omits_lyrics_and_saves_audio(monkeypatch):
    calls, replies = [], iter([wrapped({"task_id": "a"}), wrapped([{"status": 1, "result": json.dumps([{"file": "/v1/audio?path=a"}])}]), b"audio"])
    monkeypatch.setattr(music, "_request", lambda method, url, key, payload=None, timeout=45: (calls.append((url, payload)) or next(replies)))
    track = music.generate_song("ambient", "calm", 10, False)
    assert track.lyrics is None and track.audio_path and Path(track.audio_path).read_bytes() == b"audio"
    assert "lyrics" not in calls[0][1]

def test_vocal_generates_lyrics(monkeypatch):
    replies = iter([b'{"choices":[{"message":{"content":"[Verse] original"}}]}', wrapped({"task_id": "a"}), wrapped([{"status": 1, "result": json.dumps([{"file": "/v1/audio?path=a"}])}]), b"audio"])
    monkeypatch.setattr(music, "_request", lambda *args, **kwargs: next(replies))
    track = music.generate_song("pop", "hopeful", 10, True)
    assert track.lyrics == "[Verse] original" and track.is_vocal

def test_failure_is_readable(monkeypatch):
    replies = iter([wrapped({"task_id": "a"}), wrapped([{"status": 2}])])
    monkeypatch.setattr(music, "_request", lambda *args, **kwargs: next(replies))
    with pytest.raises(music.SongGenerationError, match="failed"):
        music.generate_song("pop", "sad", 10, False)

def test_rejects_bad_inputs():
    with pytest.raises(music.SongGenerationError, match="Duration"):
        music.generate_song("pop", "sad", 1, False)
