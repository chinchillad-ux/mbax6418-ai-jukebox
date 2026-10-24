"""AI DJ commentary (Qwen) and speech (Chatterbox) for the jukebox.

``commentary_for_track`` asks the class Qwen service (port 9001) for 2-4
spoken sentences specific to a Track and stores them on the Track.
``speak`` asks the class Chatterbox service (port 9008) for an MP3 of the
given text, using the bundled default voice or a user-supplied MP3/WAV
voice reference. Generated audio is saved under ignored ``data/dj/``;
voice-reference copies are kept only under ignored ``data/voice-refs/``.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from jukebox.config import load_settings
from jukebox.models import Track


class DJError(RuntimeError):
    """Safe, user-facing DJ failure without credentials or service details."""


def _request(method: str, url: str, key: str, payload: dict[str, Any] | None = None, timeout: float = 45, service: str = "service") -> bytes:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": f"Bearer {key}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(url, data=data, headers=headers, method=method), timeout=timeout) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise DJError(f"The {service} is unavailable. Please try again later.") from None


def _llm_json(url: str, key: str, payload: dict[str, Any], *, service: str) -> dict[str, Any]:
    """POST JSON to the Qwen chat endpoint and return a sane response dict."""
    try:
        value = json.loads(_request("POST", url, key, payload, timeout=45, service=service).decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise DJError(f"The {service} returned an unreadable response.") from None
    if not isinstance(value, dict) or value.get("error") or value.get("code", 200) != 200:
        raise DJError(f"The {service} rejected the commentary request.")
    return value


def _commentary_prompt(track: Track) -> str:
    """Prompt that grounds the commentary in this exact track's metadata."""
    prompt = (
        "Write 2 to 4 short, natural English sentences that an upbeat radio DJ "
        "would say aloud to introduce the next song between tracks. Do not write "
        "generic filler: be specific to this exact track, mention its title "
        f'"{track.title}" naturally in the commentary, and describe its style '
        f"({track.style}) and mood ({track.mood}). Do not mention instructions, "
        "prompts, AI, or songwriting, and do not quote the lyrics. Speak only "
        "the sentences a listener would hear."
    )
    if track.is_vocal and track.lyrics and track.lyrics.strip():
        prompt += (
            " Weave in one of the song's lyrical themes or images in your own "
            f"words. Lyrics to draw on: {track.lyrics.strip()}"
        )
    else:
        prompt += " This track is instrumental, with no vocals or lyrics."
    return prompt


def commentary_for_track(track: Track) -> str:
    """Generate 2-4 spoken sentences about the track; save and return them."""
    if not isinstance(track, Track):
        raise DJError("A Track is required for DJ commentary.")
    if not (track.title and track.title.strip() and track.style and track.style.strip() and track.mood and track.mood.strip()):
        raise DJError("Track title, style, and mood are required for DJ commentary.")
    settings = load_settings()
    if ":9000" in settings.llm_url or ":9000" in settings.speech_url:
        raise DJError("Port 9000 is not permitted for DJ commentary.")
    response = _llm_json(
        f"{settings.llm_url.rstrip('/')}/chat/completions",
        settings.api_key,
        {
            "model": settings.llm_model,
            "messages": [{"role": "user", "content": _commentary_prompt(track)}],
            "temperature": 0.7,
        },
        service="commentary service",
    )
    try:
        commentary = response["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError):
        raise DJError("The commentary service returned no usable commentary.") from None
    if not commentary:
        raise DJError("The commentary service returned no usable commentary.")
    track.dj_commentary = commentary
    return commentary


def _store_voice_reference(voice_ref_path: str) -> str:
    """Validate an MP3/WAV reference and keep it under ``data/voice-refs/``.

    References already under ``data/voice-refs/`` are used in place; any
    other reference is copied there so user audio never lives elsewhere in
    the repository. Returns the canonical local path.
    """
    source = Path(voice_ref_path)
    if not source.is_file():
        raise DJError("The voice reference file is missing.")
    if source.stat().st_size == 0:
        raise DJError("The voice reference file is empty.")
    suffix = source.suffix.lower()
    if suffix not in {".mp3", ".wav"}:
        raise DJError("Voice references must be MP3 or WAV files.")
    references_dir = Path("data/voice-refs")
    try:
        references_dir.mkdir(parents=True, exist_ok=True)
        if source.resolve().is_relative_to(references_dir.resolve()):
            return str(source)
    except OSError:
        raise DJError("Could not prepare the voice reference.") from None
    destination = references_dir / f"{uuid4().hex}{suffix}"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        temporary.write_bytes(source.read_bytes())
        temporary.replace(destination)
    except OSError:
        raise DJError("Could not store the voice reference.") from None
    finally:
        temporary.unlink(missing_ok=True)
    return str(destination)


def _reference_data_uri(path: str) -> str:
    """Base64 data URI of a reference audio file for the ``ref_audio`` field."""
    mime = "audio/mpeg" if Path(path).suffix.lower() == ".mp3" else "audio/wav"
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def _looks_like_audio(data: bytes) -> bool:
    """Reject empty/HTML/JSON bodies; accept ID3 tags or an MPEG frame sync."""
    if not data:
        return False
    if data.startswith(b"ID3"):
        return True
    return len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0


def speak(text: str, voice_ref_path: str | None = None) -> str:
    """Synthesize ``text`` with Chatterbox and save the MP3 under ``data/dj/``.

    ``voice_ref_path`` is an optional MP3/WAV voice reference; without it the
    service's bundled default voice is used. Returns the saved audio path.
    """
    if not isinstance(text, str) or not text.strip():
        raise DJError("Commentary text is required for speech.")
    settings = load_settings()
    if ":9000" in settings.speech_url or ":9000" in settings.llm_url:
        raise DJError("Port 9000 is not permitted for DJ speech.")
    payload: dict[str, Any] = {
        "model": settings.speech_model,
        "input": text,
        "voice": "default",
        "language_id": "en",
        "response_format": "mp3",
    }
    if voice_ref_path is not None:
        reference = _store_voice_reference(voice_ref_path)
        payload["ref_audio"] = _reference_data_uri(reference)
    audio = _request(
        "POST",
        f"{settings.speech_url.rstrip('/')}/v1/audio/speech",
        settings.api_key,
        payload,
        timeout=120,
        service="speech service",
    )
    if not audio:
        raise DJError("The speech service returned an empty audio file.")
    if not _looks_like_audio(audio):
        raise DJError("The speech service returned an unreadable audio response.")
    destination = Path("data/dj") / f"{uuid4().hex}.mp3"
    temporary = destination.with_suffix(".tmp")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(audio)
        temporary.replace(destination)
    except OSError:
        raise DJError("Could not save the DJ audio. Check disk space and permissions.") from None
    finally:
        temporary.unlink(missing_ok=True)
    return str(destination)
