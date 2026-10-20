"""Class-service configuration, loaded from the environment (.env).

All class services share a single API key. Base URL shapes follow the
class-endpoints.txt handout; issues #2-#4 verify the exact request formats.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    api_key: str
    llm_url: str  # port 9001 - text/vision LLM (lyrics, DJ commentary)
    cover_art_url: str  # port 9006 - FLUX cover art
    music_url: str  # port 9007 - ACE-Step song generation
    speech_url: str  # port 9008 - Chatterbox TTS


def load_settings(env_file: str | None = None) -> Settings:
    """Load settings from ``.env`` (or a test fixture), then the environment.

    A missing variable raises ``KeyError`` with the variable name so
    configuration problems surface immediately at startup.
    """
    load_dotenv(env_file)
    return Settings(
        api_key=os.environ["API_KEY"],
        llm_url=os.environ["LLM_URL"],
        cover_art_url=os.environ["COVER_ART_URL"],
        music_url=os.environ["MUSIC_URL"],
        speech_url=os.environ["SPEECH_URL"],
    )
