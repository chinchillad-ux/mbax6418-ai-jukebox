"""Configuration tests use only temporary files and dummy environment values."""
import pytest

from jukebox.config import load_settings

DUMMY = {
    "API_KEY": "test-key",
    "LLM_URL": "http://example.test:9001/v1",
    "COVER_ART_URL": "http://example.test:9006",
    "MUSIC_URL": "http://example.test:9007",
    "SPEECH_URL": "http://example.test:9008",
    "LLM_MODEL": "test-llm",
    "COVER_ART_MODEL": "test-cover",
    "MUSIC_MODEL": "test-music",
    "SPEECH_MODEL": "test-speech",
}


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for key in DUMMY:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def empty_env(tmp_path):
    path = tmp_path / ".env"
    path.write_text("")
    return str(path)


def test_settings_load_from_environment(monkeypatch, empty_env):
    for key, value in DUMMY.items():
        monkeypatch.setenv(key, value)
    settings = load_settings(empty_env)
    for key, value in DUMMY.items():
        assert getattr(settings, key.lower()) == value


@pytest.mark.parametrize("missing", DUMMY)
def test_missing_variable_raises_key_error(monkeypatch, empty_env, missing):
    for key, value in DUMMY.items():
        if key != missing:
            monkeypatch.setenv(key, value)
    with pytest.raises(KeyError, match=missing):
        load_settings(empty_env)


def test_settings_load_from_explicit_env_file(tmp_path):
    path = tmp_path / "fixture.env"
    path.write_text("\n".join(f"{key}={value}" for key, value in DUMMY.items()))
    settings = load_settings(str(path))
    for key, value in DUMMY.items():
        assert getattr(settings, key.lower()) == value


def test_environment_takes_precedence_over_file(monkeypatch, tmp_path):
    path = tmp_path / "fixture.env"
    path.write_text("\n".join(f"{key}={value}" for key, value in DUMMY.items()))
    monkeypatch.setenv("LLM_MODEL", "environment-model")
    assert load_settings(str(path)).llm_model == "environment-model"
