"""Song editing regressions; no credentials or live AI services."""
from pathlib import Path

import pytest

from jukebox import app, cover
from jukebox.library import Library, LibraryError
from jukebox.models import Track


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    track = Track("song", "Original", "pop", "happy", 30, True,
                  lyrics="Original lyrics", audio_path="song.mp3",
                  cover_path="old.png", dj_commentary="Original intro",
                  dj_audio_path="intro.mp3")
    for name in ("song.mp3", "old.png", "intro.mp3"):
        Path(name).write_bytes(b"unchanged fixture")
    Library().add(track)
    return track


@pytest.mark.parametrize("title", ["Original", "Changed song title"])
def test_custom_description_reaches_existing_flux_request(saved, monkeypatch, title):
    import base64
    import json
    from io import BytesIO

    from PIL import Image

    from jukebox.config import Settings

    image = BytesIO()
    Image.new("RGB", (4, 4), "purple").save(image, "PNG")
    settings = Settings("dummy-key", "http://example.test:9001/v1",
                        "http://example.test:9006/v1", "http://example.test:9007",
                        "http://example.test:9008", "qwen",
                        "black-forest-labs/FLUX.2-klein-4B", "ace", "speech")
    monkeypatch.setattr(cover, "load_settings", lambda: settings)
    sent = []

    def request(req, **kwargs):
        sent.append(req)
        return BytesIO(json.dumps({"data": [{"b64_json": base64.b64encode(image.getvalue()).decode()}]}).encode())

    monkeypatch.setattr(cover, "urlopen", request)
    saved.title = title
    original = saved.to_dict()
    generated = cover.generate_cover(saved, description="  Violet moons over a quiet sea  ")
    assert generated.cover_path != original["cover_path"]
    assert Path(original["cover_path"]).read_bytes() == b"unchanged fixture"
    assert generated.cover_description == "Violet moons over a quiet sea"
    payload = json.loads(sent[0].data)
    assert "Violet moons over a quiet sea" in payload["prompt"]
    assert saved.title not in payload["prompt"]
    assert saved.lyrics not in payload["prompt"]
    assert f"Musical style: {saved.style}" in payload["prompt"]
    assert f"Mood: {saved.mood}" in payload["prompt"]
    assert "no lettering, logos, or watermarks" in payload["prompt"]
    assert payload["model"] == settings.cover_art_model
    assert sent[0].full_url == "http://example.test:9006/v1/images/generations"
    assert generated.to_dict() == {**original, "cover_path": generated.cover_path,
                                   "cover_description": generated.cover_description}


def test_regenerate_existing_cover_persists_description(saved, monkeypatch):
    def generate(track, description=None):
        track.cover_path = "new.png"
        track.cover_description = description.strip()
        return track
    monkeypatch.setattr(app, "generate_cover", generate)
    path, message = app.regenerate_cover(saved.id, "  Blue mountains  ")
    assert path == "new.png" and "saved" in message.lower()
    assert Library().get(saved.id).to_dict() == {
        **saved.to_dict(), "cover_path": "new.png", "cover_description": "Blue mountains"}
    assert Path("old.png").read_bytes() == b"unchanged fixture"


def test_regeneration_does_not_overwrite_concurrent_rename(saved, monkeypatch):
    def generate(track, description=None):
        app.rename_song(track.id, "Concurrent name")
        track.cover_path = "new.png"
        track.cover_description = description
        return track
    monkeypatch.setattr(app, "generate_cover", generate)
    assert app.regenerate_cover(saved.id, "Mountains")[0] == "new.png"
    current = Library().get(saved.id)
    assert current.title == "Concurrent name"
    assert current.dj_audio_path is None
    assert current.cover_description == "Mountains"


def test_dj_result_for_old_title_is_rejected_after_rename(saved, monkeypatch):
    def commentary(track):
        app.rename_song(track.id, "Concurrent name")
        return "Old title introduction"
    monkeypatch.setattr(app, "commentary_for_track", commentary)
    monkeypatch.setattr(app, "speak", lambda *a, **k: "stale.mp3")
    audio, message = app.generate_dj_intro(saved.id, "Default Voice", None, "")
    assert audio is None
    assert "changed" in message.lower()
    current = Library().get(saved.id)
    assert current.title == "Concurrent name"
    assert current.dj_audio_path is None


def test_editor_loads_current_metadata_and_rename_resets_dj_ui(saved):
    title, description, image = app.load_song_editor(saved.id)
    assert title == saved.title and image == saved.cover_path
    assert saved.style in description and saved.mood in description
    result = app.rename_and_refresh(saved.id, "New title")
    status, gallery, songs, dj, playlist, audio, playing, state, preview, dj_status, playback = result
    assert "saved" in status
    assert gallery == [(saved.cover_path, "New title")]
    assert songs["value"] == saved.id
    assert songs["choices"] == [("New title", saved.id)]
    assert dj["choices"] == [("New title", saved.id)]
    assert playlist["choices"] == []
    assert audio is None and playing is None
    assert state == {"ids": [], "index": 0, "phase": None}
    assert "empty" in preview and "new DJ" in dj_status
    assert "stopped" in playback
    assert app.load_song_editor(None) == ("", "", None)


def test_editor_controls_are_wired_to_saved_id_without_image_upload(saved):
    config = app.build_app().config
    components = {c["id"]: c for c in config["components"]}
    by_label = {c["props"].get("label"): c for c in components.values()}
    assert by_label["Song title"]["type"] == "textbox"
    assert by_label["Cover description"]["type"] == "textbox"
    assert by_label["Current album cover"]["props"]["interactive"] is False
    dependencies = {d["api_name"]: d for d in config["dependencies"]}
    rename = dependencies["rename_and_refresh"]
    regenerate = dependencies["regenerate_cover"]
    assert [components[i]["props"]["label"] for i in rename["inputs"]] == ["Choose Any Saved Song", "Song title"]
    assert [components[i]["props"]["label"] for i in regenerate["inputs"]] == ["Choose Any Saved Song", "Cover description"]
    assert len(rename["outputs"]) == 11
    assert any(d["api_name"] == "load_song_editor" for d in config["dependencies"])


@pytest.mark.parametrize("title", ["", "   ", None, "x" * 201])
def test_invalid_titles_do_not_change_library(saved, title):
    message = app.rename_song(saved.id, title)
    assert message.startswith("⚠️")
    assert Library().get(saved.id) == saved


@pytest.mark.parametrize("description", ["", "   ", None, "x" * 2001])
def test_invalid_descriptions_do_not_call_service(saved, monkeypatch, description):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid description must not call FLUX")
    monkeypatch.setattr(app, "generate_cover", forbidden)
    path, message = app.regenerate_cover(saved.id, description)
    assert path == saved.cover_path and message.startswith("⚠️")
    assert Library().get(saved.id) == saved


@pytest.mark.parametrize("failure", [app.CoverGenerationError("offline"), RuntimeError("private details")])
def test_regeneration_failure_keeps_old_cover_and_metadata(saved, monkeypatch, failure):
    def generate(track, **kwargs):
        track.cover_path = "must-not-save.png"
        raise failure
    monkeypatch.setattr(app, "generate_cover", generate)
    path, message = app.regenerate_cover(saved.id, "Blue mountains")
    assert path == saved.cover_path and "kept" in message
    assert "private details" not in message
    assert Library().get(saved.id) == saved
    assert Path(saved.cover_path).read_bytes() == b"unchanged fixture"


def test_failed_atomic_save_preserves_previous_cover_and_title(saved, monkeypatch):
    import jukebox.library as library_module
    def fail(*args):
        raise OSError("disk full")
    def generate(track, **kwargs):
        track.cover_path = "new.png"
        return track
    monkeypatch.setattr(library_module.os, "replace", fail)
    monkeypatch.setattr(app, "generate_cover", generate)
    path, message = app.regenerate_cover(saved.id, "Blue mountains")
    assert path == saved.cover_path and "kept" in message
    assert "Could not rename" in app.rename_song(saved.id, "New title")
    assert Library().get(saved.id) == saved
    assert not list(Path("data").glob(".library-*.tmp"))


def test_noop_rename_keeps_dj_and_does_not_reset_ui(saved):
    result = app.rename_and_refresh(saved.id, " Original ")
    assert result[0].startswith("No change")
    assert all(value == app.gr.skip() for value in result[1:])
    assert Library().get(saved.id) == saved


@pytest.mark.parametrize("track_id", [None, "missing"])
def test_missing_selection_changes_nothing(saved, track_id):
    assert "select" in app.rename_song(track_id, "New name")
    assert app.regenerate_cover(track_id, "Mountains")[0] is None
    assert Library().get(saved.id) == saved


def test_gallery_selection_targets_same_song_in_editor(saved):
    event = app.gr.SelectData(None, {"index": 0, "value": None})
    audio, message, selected_id = app.select_library_song(event)
    assert audio == saved.audio_path and selected_id == saved.id
    assert saved.title in message


def test_legacy_record_and_description_survive_reload(saved):
    import json
    record = saved.to_dict()
    del record["cover_description"]
    Path("data/library.json").write_text(json.dumps({"version": 1, "tracks": [record]}))
    assert Library().get(saved.id).cover_description is None
    Library().update(saved.id, cover_description="A red sun")
    assert app.load_song_editor(saved.id)[1] == "A red sun"


def test_cover_failure_does_not_reset_unsaved_description(saved):
    assert app.refresh_after_cover(saved.id, "⚠️ Previous cover kept") == app.gr.skip()
    assert app.refresh_after_cover(saved.id, "✅ New album cover saved")["value"] == saved.id


@pytest.mark.parametrize("description", ["", "   ", 42, "x" * 2001], ids=["empty", "spaces", "wrong-type", "too-long"])
def test_cover_service_rejects_invalid_custom_description_before_settings(saved, monkeypatch, description):
    monkeypatch.setattr(cover, "load_settings", lambda: pytest.fail("Must validate before settings"))
    with pytest.raises(cover.CoverGenerationError, match="description"):
        cover.generate_cover(saved, description=description)
    assert saved.cover_path == "old.png"


def test_duplicate_titles_keep_distinct_ids_and_original_order(saved):
    from dataclasses import replace
    other = replace(saved, id="other", title="Other")
    Library().add(other)
    app.rename_song(saved.id, "Other")
    assert [(t.id, t.title) for t in Library().list()] == [("song", "Other"), ("other", "Other")]
    assert Library().get("other") == other


def test_coverless_song_can_use_regenerate(saved, monkeypatch):
    Library().update(saved.id, cover_path=None)
    def generate(track, description=None):
        track.cover_path = "new.png"
        track.cover_description = description
        return track
    monkeypatch.setattr(app, "generate_cover", generate)
    assert app.regenerate_cover(saved.id, "Mountains")[0] == "new.png"
    assert Library().get(saved.id).audio_path == saved.audio_path


def test_no_artwork_response_preserves_saved_track(saved, monkeypatch):
    def generate(track, **kwargs):
        track.cover_path = None
        return track
    monkeypatch.setattr(app, "generate_cover", generate)
    assert app.regenerate_cover(saved.id, "Mountains")[0] == saved.cover_path
    assert Library().get(saved.id) == saved


def test_stale_library_update_preserves_newer_fields(saved):
    stale = Library()
    Library().update(saved.id, cover_path="new.png")
    stale.update(saved.id, title="New title")
    current = Library().get(saved.id)
    assert current.title == "New title" and current.cover_path == "new.png"
    assert current.dj_commentary is None and current.dj_audio_path is None
    with pytest.raises(LibraryError):
        stale.update(saved.id, audio_path="not-allowed.mp3")
    with pytest.raises(LibraryError):
        stale.update("missing", title="Name")


def test_rename_persists_only_title_and_invalidates_stale_dj(saved):
    message = app.rename_song(saved.id, "  New title 🎵  ")
    assert "saved" in message.lower()
    assert "DJ" in message
    assert Library().get(saved.id).to_dict() == {
        **saved.to_dict(), "title": "New title 🎵",
        "dj_commentary": None, "dj_audio_path": None,
    }
    assert all(Path(p).read_bytes() == b"unchanged fixture"
               for p in (saved.audio_path, saved.cover_path, saved.dj_audio_path))
    assert app.refresh_saved_song_choices(saved.id)["choices"] == [("New title 🎵", saved.id)]
    songs, playlist = app.refresh_dj_songs()
    assert songs["choices"] == [("New title 🎵", saved.id)]
    assert playlist["choices"] == []
    assert app.load_library()[0] == [(saved.cover_path, "New title 🎵")]
