"""Exercise the running Gradio app over HTTP; only FLUX transport is mocked."""
import base64
import json
from io import BytesIO
from pathlib import Path

from gradio_client import Client
from PIL import Image

from jukebox import app, cover
from jukebox.config import Settings
from jukebox.library import Library
from jukebox.models import Track


def test_running_app_rename_regenerate_failure_and_reload(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRADIO_ANALYTICS_ENABLED", "False")
    old_image = tmp_path / "old.png"
    Image.new("RGB", (8, 8), "blue").save(old_image)
    original_bytes = old_image.read_bytes()
    original = Track("runtime-song", "Before", "pop", "happy", 30, True,
                     lyrics="Keep these lyrics", audio_path="unchanged.mp3",
                     cover_path=str(old_image), dj_commentary="Before intro",
                     dj_audio_path="old-intro.mp3")
    Library().add(original)
    settings = Settings("dummy-key", "http://example.test:9001/v1",
                        "http://example.test:9006/v1", "http://example.test:9007",
                        "http://example.test:9008", "qwen",
                        "black-forest-labs/FLUX.2-klein-4B", "ace", "speech")
    monkeypatch.setattr(cover, "load_settings", lambda: settings)
    requests = []
    image = BytesIO()
    Image.new("RGB", (1024, 1024), "red").save(image, "PNG")

    def flux(req, **kwargs):
        payload = json.loads(req.data)
        requests.append(payload)
        if "simulate outage" in payload["prompt"]:
            raise OSError("synthetic service outage")
        return BytesIO(json.dumps({"data": [{"b64_json": base64.b64encode(image.getvalue()).decode()}]}).encode())

    monkeypatch.setattr(cover, "urlopen", flux)
    demo = app.build_app()
    try:
        _, url, _ = demo.launch(server_name="127.0.0.1", prevent_thread_lock=True,
                                quiet=True, allowed_paths=[str(tmp_path)])
        client = Client(url, verbose=False)
        title, description, old_preview = client.predict(original.id, api_name="/load_song_editor")
        assert title == "Before" and "pop" in description
        assert Path(old_preview).read_bytes() == original_bytes
        rename = client.predict(original.id, "After 🎵", api_name="/rename_and_refresh")
        assert "Title saved" in rename[0]
        assert Library().get(original.id).title == "After 🎵"
        assert Library().get(original.id).dj_audio_path is None
        client.predict(original.id, "Red planets", api_name="/regenerate_cover")
        new_preview, status, _ = client.predict(original.id, api_name="/show_cover_result")
        assert "saved" in status and Path(new_preview).is_file()
        current = Library().get(original.id)
        assert current.cover_path != original.cover_path
        assert current.cover_description == "Red planets"
        assert current.audio_path == original.audio_path and current.lyrics == original.lyrics
        assert "Red planets" in requests[-1]["prompt"]
        assert "After 🎵" not in requests[-1]["prompt"]
        assert original.lyrics not in requests[-1]["prompt"]
        client.predict(original.id, "simulate outage", api_name="/regenerate_cover")
        kept_preview, failure, choices = client.predict(original.id, api_name="/show_cover_result")
        assert "kept" in failure
        assert kept_preview == app.gr.skip() and choices == app.gr.skip()
        assert Library().get(original.id) == current
        title, description, preview = client.predict(original.id, api_name="/load_song_editor")
        assert (title, description) == ("After 🎵", "Red planets")
        assert Path(preview).read_bytes() == Path(new_preview).read_bytes()
        assert old_image.read_bytes() == original_bytes
        assert len(Library().list()) == 1
    finally:
        demo.close()
