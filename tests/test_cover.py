"""Cover tests use dummy settings, temporary files, and mocked HTTP only."""
import base64
from dataclasses import replace
from email.message import Message
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

from PIL import Image
import pytest

from jukebox import cover
from jukebox.config import Settings
from jukebox.models import Track


SETTINGS = Settings(
    "dummy-key", "http://example.test:9001/v1", "http://example.test:9006/v1",
    "http://example.test:9007", "http://example.test:9008", "qwen",
    "black-forest-labs/FLUX.2-klein-4B", "ace", "speech",
)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    # Fail closed: even a test missing its response mock cannot access a service.
    monkeypatch.setattr("urllib.request.OpenerDirector.open", Mock(side_effect=AssertionError("Real HTTP forbidden")))


@pytest.fixture
def track():
    return Track("track-1", "Midnight Drive", "Synthwave", "Hopeful", 30, False)


@pytest.fixture
def png():
    output = BytesIO()
    Image.new("RGB", (4, 4), "blue").save(output, format="PNG")
    return output.getvalue()


def mock_response(monkeypatch, body):
    monkeypatch.setattr(cover, "load_settings", lambda: SETTINGS)
    response = BytesIO(body)
    request = Mock(return_value=response)
    monkeypatch.setattr(cover, "urlopen", request)
    return request


def image_response(image):
    return json.dumps({"data": [{"b64_json": base64.b64encode(image).decode()}]}).encode()


def test_saves_valid_png_and_updates_only_correct_track(monkeypatch, track, png):
    generate = cover.generate_cover
    request = mock_response(monkeypatch, image_response(png))
    other = replace(track, id="track-2")
    before = track.to_dict()
    assert generate(track) is track
    saved = Path(track.cover_path)
    assert saved.parent == Path("data/covers")
    assert saved.suffix == ".png" and saved.read_bytes() == png
    assert saved.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert track.to_dict() == {**before, "cover_path": str(saved)}
    assert other.cover_path is None
    sent = request.call_args.args[0]
    assert sent.full_url == "http://example.test:9006/v1/images/generations"
    assert sent.method == "POST"
    assert sent.get_header("Authorization") == "Bearer dummy-key"
    assert sent.get_header("Content-type") == "application/json"
    assert json.loads(sent.data) == {
        "model": SETTINGS.cover_art_model, "prompt": cover.cover_prompt(track),
        "n": 1, "size": "1024x1024", "response_format": "b64_json",
    }
    assert request.call_args.kwargs["timeout"] > 0
    assert request.call_count == 1


@pytest.mark.parametrize("body", [
    b"not json", b"\xff", b"null", b"[]", b"{}", b'{"data": []}',
    b'{"data": null}', b'{"data": [null]}', b'{"data": [{}]}',
    b'{"data": [{"b64_json": null}]}', b'{"data": [{"b64_json": 42}]}',
    b'{"data": [{"b64_json": "!!!"}]}', b'{"error": "private service details"}',
])
def test_invalid_response_leaves_no_files(monkeypatch, track, tmp_path, body):
    mock_response(monkeypatch, body)
    with pytest.raises(cover.CoverGenerationError, match="response"):
        cover.generate_cover(track)
    assert track.cover_path is None
    assert not list(tmp_path.rglob("*.png"))
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("failure", [
    TimeoutError("private"), OSError("private"), URLError("private"),
    HTTPError("http://example.test", 401, "private", Message(), None),
    HTTPError("http://example.test", 500, "private", Message(), None),
])
def test_service_failure_is_readable(monkeypatch, track, tmp_path, failure):
    request = mock_response(monkeypatch, b"")
    request.side_effect = failure
    with pytest.raises(cover.CoverGenerationError, match="service") as error:
        cover.generate_cover(track)
    assert "private" not in str(error.value)
    assert track.cover_path is None
    assert not list(tmp_path.rglob("*"))


@pytest.mark.parametrize("kind", ["empty", "header", "truncated", "missing-end", "truncated-end", "crc", "jpeg", "bad-pixels"])
def test_corrupt_images_leave_existing_cover_untouched(monkeypatch, track, png, tmp_path, kind):
    import struct
    import zlib

    if kind == "empty":
        invalid = b""
    elif kind == "header":
        invalid = b"\x89PNG\r\n\x1a\nnot an image"
    elif kind == "truncated":
        invalid = png[:-15]
    elif kind == "missing-end":
        invalid = png[:-12]
    elif kind == "truncated-end":
        invalid = png[:-1]
    elif kind == "crc":
        invalid = png[:29] + bytes([png[29] ^ 1]) + png[30:]
    elif kind == "jpeg":
        stream = BytesIO()
        Image.new("RGB", (4, 4)).save(stream, "JPEG")
        invalid = stream.getvalue()
    else:
        # Correct chunk CRC, but undecodable compressed pixels: verify alone is insufficient.
        data = b"IDATnot a zlib stream"
        invalid = png[:33] + struct.pack(">I", len(data) - 4) + data + struct.pack(">I", zlib.crc32(data)) + png[-12:]
    previous = tmp_path / "previous.png"
    previous.write_bytes(png)
    track.cover_path = str(previous)
    mock_response(monkeypatch, image_response(invalid))
    with pytest.raises(cover.CoverGenerationError, match="PNG"):
        cover.generate_cover(track)
    assert track.cover_path == str(previous)
    assert previous.read_bytes() == png
    assert list(tmp_path.rglob("*")) == [previous]


@pytest.mark.parametrize("stage", ["write", "rename"])
def test_disk_failure_cleans_partial_file(monkeypatch, track, png, tmp_path, stage):
    mock_response(monkeypatch, image_response(png))
    track.cover_path = "previous-cover.png"
    original_write = Path.write_bytes

    def fail_write(path, data):
        original_write(path, data[:12])
        raise OSError("disk full")

    if stage == "write":
        monkeypatch.setattr(Path, "write_bytes", fail_write)
    else:
        monkeypatch.setattr(Path, "replace", Mock(side_effect=OSError("rename failed")))
    with pytest.raises(cover.CoverGenerationError, match="save"):
        cover.generate_cover(track)
    assert track.cover_path == "previous-cover.png"
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


@pytest.mark.parametrize("url", ["http://example.test:9000/v1", "not-a-url"])
def test_invalid_or_forbidden_endpoint_makes_no_request(monkeypatch, track, url):
    request = mock_response(monkeypatch, b"")
    monkeypatch.setattr(cover, "load_settings", lambda: replace(SETTINGS, cover_art_url=url))
    with pytest.raises(cover.CoverGenerationError, match="configuration|9000"):
        cover.generate_cover(track)
    request.assert_not_called()


def test_prompt_uses_track_details_and_lyrical_theme():
    from jukebox.cover import cover_prompt

    track = Track("t1", "Midnight Drive", "Synthwave", "Hopeful", 30, True)
    instrumental_prompt = cover_prompt(track)
    for value in (track.title, track.style, track.mood):
        assert value in instrumental_prompt
    track.lyrics = "We find our way home beneath the northern lights"
    vocal_prompt = cover_prompt(track)
    assert track.lyrics in vocal_prompt
    assert vocal_prompt != instrumental_prompt
    assert "theme" in vocal_prompt.lower()
