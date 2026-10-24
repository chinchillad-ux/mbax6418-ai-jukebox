"""AI DJ tests use dummy settings, temporary files, and mocked HTTP only."""
import base64
from dataclasses import replace
from email.message import Message
import json
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from jukebox import dj
from jukebox.config import Settings
from jukebox.models import Track


SETTINGS = Settings(
    "dummy-key", "http://example.test:9001/v1", "x",
    "x", "http://example.test:9008", "qwen",
    "x", "x", "chatterbox-v3",
)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    # Fail closed: even a test missing its response mock cannot access a service.
    monkeypatch.setattr("urllib.request.OpenerDirector.open", Mock(side_effect=AssertionError("Real HTTP forbidden")))


@pytest.fixture
def track():
    return Track(
        "track-1", "Midnight Drive", "Synthwave", "Hopeful", 30, True,
        lyrics="We chase the neon horizon, never looking back",
    )


def llm_response(content):
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


# --- Commentary -------------------------------------------------------------

@pytest.mark.parametrize("content", [
    "Up next, Midnight Drive - a hopeful Synthwave ride into the neon horizon.",
    "Here comes 'Midnight Drive': glowing synthwave with a hopeful mood.",
])
def test_commentary_requests_and_returns_song_specifics(monkeypatch, track, content):
    calls = []
    monkeypatch.setattr(dj, "load_settings", lambda: SETTINGS)
    replies = iter([llm_response(content)])
    monkeypatch.setattr(dj, "_request", lambda method, url, key, payload=None, timeout=45, service="service": (calls.append((url, payload)) or next(replies)))
    result = dj.commentary_for_track(track)
    assert result == content
    assert result  # not empty
    url, payload = calls[0]
    assert url == "http://example.test:9001/v1/chat/completions"
    assert payload["model"] == SETTINGS.llm_model
    prompt = payload["messages"][0]["content"]
    for value in (track.title, track.style, track.mood, track.lyrics):
        assert value in prompt


def test_commentary_instrumental_omits_lyrics(monkeypatch, track):
    calls = []
    monkeypatch.setattr(dj, "load_settings", lambda: SETTINGS)
    instrumental = replace(track, is_vocal=False, lyrics=None)
    replies = iter([llm_response("An instrumental drift through calm synth light, next up on the jukebox.")])
    monkeypatch.setattr(dj, "_request", lambda method, url, key, payload=None, timeout=45, service="service": (calls.append((url, payload)) or next(replies)))
    dj.commentary_for_track(instrumental)
    prompt = calls[0][1]["messages"][0]["content"]
    assert track.lyrics not in prompt
    assert "instrumental" in prompt.lower()


def test_commentary_saves_only_on_requested_track(monkeypatch, track):
    monkeypatch.setattr(dj, "load_settings", lambda: SETTINGS)
    other = replace(track, id="track-2")
    content = "Midnight Drive is next - hopeful synthwave for the open road."
    replies = iter([llm_response(content)])
    monkeypatch.setattr(dj, "_request", lambda method, url, key, payload=None, timeout=45, service="service": next(replies))
    before = track.to_dict()
    result = dj.commentary_for_track(track)
    assert result == content
    assert track.to_dict() == {**before, "dj_commentary": content}
    assert other.dj_commentary is None


@pytest.mark.parametrize("body", [
    b"not json", b"\xff", b"null", b"[]", b"{}", b'{"choices": []}',
    b'{"choices": [{}]}', b'{"choices": [{"message": {}}]}',
    b'{"choices": [{"message": {"content": ""}}]}',
    b'{"choices": [{"message": {"content": null}}]}',
    b'{"choices": [{"message": {"content": 42}}]}',
    b'{"error": "private service details"}',
])
def test_commentary_malformed_response_is_readable(monkeypatch, track, body):
    monkeypatch.setattr(dj, "load_settings", lambda: SETTINGS)
    monkeypatch.setattr(dj, "_request", lambda method, url, key, payload=None, timeout=45, service="service": body)
    with pytest.raises(dj.DJError):
        dj.commentary_for_track(track)
    assert track.dj_commentary is None


@pytest.mark.parametrize("failure", [
    TimeoutError("private"), OSError("private"), URLError("private"),
    HTTPError("http://example.test", 401, "private", Message(), None),
    HTTPError("http://example.test", 500, "private", Message(), None),
])
def test_commentary_service_failure_is_readable(monkeypatch, track, failure):
    monkeypatch.setattr(dj, "load_settings", lambda: SETTINGS)
    # Exercise the real _request error translation by failing at urlopen.
    monkeypatch.setattr(dj, "urlopen", Mock(side_effect=failure))
    with pytest.raises(dj.DJError, match="commentary service") as error:
        dj.commentary_for_track(track)
    assert "private" not in str(error.value)
    assert track.dj_commentary is None


def test_commentary_rejects_invalid_track(monkeypatch, track):
    monkeypatch.setattr(dj, "load_settings", lambda: SETTINGS)
    mock = Mock()
    monkeypatch.setattr(dj, "_request", mock)
    with pytest.raises(dj.DJError, match="required"):
        dj.commentary_for_track(replace(track, title="   "))
    mock.assert_not_called()


@pytest.mark.parametrize("field", ["llm_url", "speech_url"])
def test_commentary_forbids_port_9000(monkeypatch, track, field):
    monkeypatch.setattr(dj, "load_settings", lambda: replace(SETTINGS, **{field: "http://example.test:9000/v1"}))
    mock = Mock()
    monkeypatch.setattr(dj, "_request", mock)
    with pytest.raises(dj.DJError, match="9000"):
        dj.commentary_for_track(track)
    mock.assert_not_called()


# --- Speech -----------------------------------------------------------------

AUDIO = b"ID3\x04\x00\x00\x00\x00\x00\x00fake-mp3-bytes"

def speech_calls(monkeypatch, bodies):
    calls = []
    monkeypatch.setattr(dj, "load_settings", lambda: SETTINGS)
    replies = iter(bodies)
    monkeypatch.setattr(dj, "_request", lambda method, url, key, payload=None, timeout=45, service="service": (calls.append((url, payload)) or next(replies)))
    return calls


def test_speak_default_voice_saves_audio(monkeypatch, tmp_path):
    calls = speech_calls(monkeypatch, [AUDIO])
    path = dj.speak("Up next on the jukebox, a hopeful synthwave ride.")
    saved = Path(path)
    assert saved.parent == Path("data/dj")
    assert saved.suffix == ".mp3"
    assert saved.read_bytes() == AUDIO
    url, payload = calls[0]
    assert url == "http://example.test:9008/v1/audio/speech"
    assert payload == {
        "model": SETTINGS.speech_model,
        "input": "Up next on the jukebox, a hopeful synthwave ride.",
        "voice": "default",
        "language_id": "en",
        "response_format": "mp3",
    }
    assert "ref_audio" not in payload


def test_speak_custom_mp3_reference(monkeypatch, tmp_path):
    reference = tmp_path / "ref.mp3"
    reference.write_bytes(b"ID3reference-voice")
    calls = speech_calls(monkeypatch, [AUDIO])
    path = dj.speak("Hello from the custom voice.", voice_ref_path=str(reference))
    assert Path(path).read_bytes() == AUDIO
    url, payload = calls[0]
    assert payload["voice"] == "default"
    assert payload["ref_audio"].startswith("data:audio/mpeg;base64,")
    decoded = base64.b64decode(payload["ref_audio"].split(",", 1)[1])
    assert decoded == reference.read_bytes()
    # The reference was copied into the ignored voice-refs directory.
    refs = list(Path("data/voice-refs").glob("*"))
    assert len(refs) == 1 and refs[0].suffix == ".mp3"
    assert refs[0].read_bytes() == reference.read_bytes()


def test_speak_custom_wav_reference(monkeypatch, tmp_path):
    reference = tmp_path / "ref.wav"
    reference.write_bytes(b"RIFFwave-data")
    calls = speech_calls(monkeypatch, [AUDIO])
    dj.speak("Testing the WAV reference.", voice_ref_path=str(reference))
    url, payload = calls[0]
    assert payload["ref_audio"].startswith("data:audio/wav;base64,")
    assert next(Path("data/voice-refs").glob("*.wav")).read_bytes() == reference.read_bytes()


def test_speak_reference_inside_voice_refs_is_not_copied(monkeypatch, tmp_path):
    refs_dir = Path("data/voice-refs")
    refs_dir.mkdir(parents=True)
    existing = refs_dir / "kept.wav"
    existing.write_bytes(b"RIFFexisting-voice")
    calls = speech_calls(monkeypatch, [AUDIO])
    dj.speak("Same voice again.", voice_ref_path=str(existing))
    url, payload = calls[0]
    assert payload["ref_audio"].split(",", 1)[1] == base64.b64encode(b"RIFFexisting-voice").decode()
    assert list(refs_dir.glob("*")) == [existing]


@pytest.mark.parametrize("audio", [b"", b"<html>not audio</html>", b"\x00\x00", b"{}", b"RIFF"])
def test_speak_invalid_audio_cleans_up(monkeypatch, tmp_path, audio):
    speech_calls(monkeypatch, [audio])
    with pytest.raises(dj.DJError):
        dj.speak("This should not produce a file.")
    assert not list(Path("data/dj").glob("*")) if Path("data/dj").exists() else True
    assert not list(tmp_path.rglob("*.tmp"))


def test_speak_write_failure_cleans_partial_file(monkeypatch, tmp_path):
    speech_calls(monkeypatch, [AUDIO])
    original_write = Path.write_bytes

    def fail_write(path, data):
        original_write(path, data[:8])
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", fail_write)
    with pytest.raises(dj.DJError, match="save"):
        dj.speak("Disk trouble here.")
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_speak_reference_copy_failure_cleans_tmp(monkeypatch, tmp_path):
    reference = tmp_path / "ref.mp3"
    reference.write_bytes(b"ID3reference")
    monkeypatch.setattr(dj, "load_settings", lambda: SETTINGS)
    replies = iter([AUDIO])
    monkeypatch.setattr(dj, "_request", lambda method, url, key, payload=None, timeout=45, service="service": next(replies))

    original_write = Path.write_bytes

    def fail_write(path, data):
        if "voice-refs" in str(path):
            original_write(path, data[:4])
            raise OSError("disk full")
        return original_write(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_write)
    with pytest.raises(dj.DJError, match="voice reference"):
        dj.speak("Cloning voice.", voice_ref_path=str(reference))
    assert not list(Path("data/voice-refs").glob("*")) if Path("data/voice-refs").exists() else True
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("kind, match", [
    ("missing", "missing"),
    ("empty", "empty"),
    ("bad-extension", "MP3 or WAV"),
])
def test_speak_invalid_reference_makes_no_request(monkeypatch, tmp_path, kind, match):
    if kind == "missing":
        ref = str(tmp_path / "nope.mp3")
    elif kind == "empty":
        ref = str(tmp_path / "empty.mp3")
        Path(ref).write_bytes(b"")
    else:
        ref = str(tmp_path / "ref.ogg")
        Path(ref).write_bytes(b"OggS")
    mock = Mock()
    monkeypatch.setattr(dj, "load_settings", lambda: SETTINGS)
    monkeypatch.setattr(dj, "_request", mock)
    with pytest.raises(dj.DJError, match=match):
        dj.speak("No request should happen.", voice_ref_path=ref)
    mock.assert_not_called()
    # No DJ output or reference copies were produced.
    assert not Path("data/dj").exists() or not list(Path("data/dj").glob("*"))
    assert not Path("data/voice-refs").exists() or not list(Path("data/voice-refs").glob("*"))


@pytest.mark.parametrize("failure", [
    TimeoutError("private"), OSError("private"), URLError("private"),
    HTTPError("http://example.test", 401, "private", Message(), None),
    HTTPError("http://example.test", 500, "private", Message(), None),
])
def test_speak_service_failure_is_readable(monkeypatch, tmp_path, failure):
    monkeypatch.setattr(dj, "load_settings", lambda: SETTINGS)
    # Exercise the real _request error translation by failing at urlopen.
    monkeypatch.setattr(dj, "urlopen", Mock(side_effect=failure))
    with pytest.raises(dj.DJError, match="speech service") as error:
        dj.speak("Hello.")
    assert "private" not in str(error.value)
    assert not Path("data/dj").exists() or not list(Path("data/dj").glob("*"))


def test_speak_forbids_port_9000(monkeypatch, tmp_path):
    monkeypatch.setattr(dj, "load_settings", lambda: replace(SETTINGS, speech_url="http://example.test:9000"))
    mock = Mock()
    monkeypatch.setattr(dj, "_request", mock)
    with pytest.raises(dj.DJError, match="9000"):
        dj.speak("Hello.")
    mock.assert_not_called()


def test_speak_rejects_empty_text(monkeypatch):
    monkeypatch.setattr(dj, "load_settings", lambda: SETTINGS)
    mock = Mock()
    monkeypatch.setattr(dj, "_request", mock)
    with pytest.raises(dj.DJError, match="text"):
        dj.speak("   ")
    mock.assert_not_called()
