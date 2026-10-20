"""Configuration loader tests — dummy env values, no real credentials."""
import pytest

from jukebox.config import load_settings

DUMMY = {
    "API_KEY": "test-key",
    "LLM_URL": "http://dobolyi.com:9001/v1",
    "COVER_ART_URL": "http://dobolyi.com:9006",
    "MUSIC_URL": "http://dobolyi.com:9007",
    "SPEECH_URL": "http://dobolyi.com:9008",
}


@pytest.fixture
def dummy_env(monkeypatch):
    for key, value in DUMMY.items():
        monkeypatch.setenv(key, value)


def test_settings_load_from_environment(dummy_env):
    settings = load_settings()
    assert settings.api_key == "test-key"
    assert settings.llm_url == DUMMY["LLM_URL"]
    assert settings.cover_art_url == DUMMY["COVER_ART_URL"]
    assert settings.music_url == DUMMY["MUSIC_URL"]
    assert settings.speech_url == DUMMY["SPEECH_URL"]


def test_missing_variable_raises_key_error(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("LLM_URL", raising=False)
    with pytest.raises(KeyError):
        load_settings()
