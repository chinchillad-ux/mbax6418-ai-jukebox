"""Song generation through the asynchronous ACE-Step class endpoint."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from uuid import uuid4

from jukebox.config import load_settings
from jukebox.models import Track


class SongGenerationError(RuntimeError):
    """Safe, user-facing failure from song generation."""


def _request(method: str, url: str, key: str, payload: dict[str, Any] | None = None, timeout: float = 45) -> bytes:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": f"Bearer {key}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(url, data=data, headers=headers, method=method), timeout=timeout) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise SongGenerationError("The song service is unavailable. Please try again later.") from None


def _json(method: str, url: str, key: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(_request(method, url, key, payload).decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SongGenerationError("The service returned an unreadable response.") from None
    if not isinstance(value, dict) or value.get("error") or value.get("code", 200) != 200:
        raise SongGenerationError("The service rejected the generation request.")
    return value


def _lyrics(style: str, mood: str, duration: int, *, url: str, model: str, key: str) -> str:
    response = _json("POST", f"{url.rstrip('/')}/chat/completions", key, {
        "model": model,
        "messages": [{"role": "user", "content": (
            "Write short, original English song lyrics only (no existing lyrics) for a "
            f"{mood} {style} track lasting about {duration} seconds. Use verse and chorus labels."
        )}],
        "temperature": 0.7,
    })
    try:
        result = response["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError):
        raise SongGenerationError("The lyric service returned no usable lyrics.") from None
    if not result:
        raise SongGenerationError("The lyric service returned no usable lyrics.")
    return result


def _audio_file(row: dict[str, Any]) -> str:
    try:
        entries = json.loads(row["result"]) if isinstance(row["result"], str) else row["result"]
        location = entries[0]["file"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise SongGenerationError("Song generation completed without an audio file.") from None
    if not isinstance(location, str) or not location:
        raise SongGenerationError("Song generation completed without an audio file.")
    return location


def _validate_audio(path: Path, requested_seconds: int) -> None:
    """Decode with ffmpeg and accept durations within max(3s, 25%)."""
    if not path.is_file() or path.stat().st_size == 0:
        raise SongGenerationError("The music service returned an empty audio file.")
    try:
        if shutil.which("ffprobe") and shutil.which("ffmpeg"):
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                capture_output=True, text=True, check=True, timeout=20,
            )
            duration = float(probe.stdout.strip())
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True, check=True, timeout=30)
        elif shutil.which("afinfo"):
            probe = subprocess.run(["afinfo", str(path)], capture_output=True, text=True, check=True, timeout=20)
            match = re.search(r"estimated duration:\s*([0-9.]+) sec", probe.stdout)
            if not match:
                raise ValueError
            duration = float(match.group(1))
        else:
            raise FileNotFoundError
    except (FileNotFoundError, ValueError, subprocess.SubprocessError):
        raise SongGenerationError("Generated audio could not be decoded or inspected.") from None
    if abs(duration - requested_seconds) > max(3.0, requested_seconds * 0.25):
        raise SongGenerationError("Generated audio duration differs too much from the requested duration.")


def generate_song(style: str, mood: str, duration_seconds: int, is_vocal: bool, lyrics: str | None = None) -> Track:
    """Generate a playable track and save it in ignored ``data/songs``.

    ACE-Step receives ``POST /release_task``, then ``POST /query_result`` with
    ``task_id_list`` until completion, followed by the returned audio download.
    """
    if not isinstance(style, str) or not style.strip() or not isinstance(mood, str) or not mood.strip():
        raise SongGenerationError("Style and mood are required.")
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int) or not 10 <= duration_seconds <= 600:
        raise SongGenerationError("Duration must be an integer between 10 and 600 seconds.")
    if lyrics is not None and (not is_vocal or not lyrics.strip()):
        raise SongGenerationError("Lyrics are allowed only for vocal tracks and cannot be empty.")
    settings = load_settings()
    if ":9000" in settings.music_url or ":9000" in settings.llm_url:
        raise SongGenerationError("Port 9000 is not permitted for this feature.")
    final_lyrics = lyrics.strip() if lyrics else None
    if is_vocal and final_lyrics is None:
        final_lyrics = _lyrics(style, mood, duration_seconds, url=settings.llm_url, model=settings.llm_model, key=settings.api_key)

    payload: dict[str, Any] = {
        "prompt": f"Original {style} music with a {mood} mood",
        "audio_duration": duration_seconds,
        "audio_format": "mp3",
        "model": settings.music_model,
    }
    if is_vocal:
        payload["lyrics"] = final_lyrics
    submitted = _json("POST", f"{settings.music_url.rstrip('/')}/release_task", settings.api_key, payload)
    try:
        task_id = submitted["data"]["task_id"]
    except (KeyError, TypeError):
        raise SongGenerationError("The music service did not return a task identifier.") from None

    result: dict[str, Any] | None = None
    for _ in range(60):
        reply = _json("POST", f"{settings.music_url.rstrip('/')}/query_result", settings.api_key, {"task_id_list": [task_id]})
        rows = reply.get("data")
        row = rows[0] if isinstance(rows, list) and rows else None
        if not isinstance(row, dict):
            raise SongGenerationError("The music service returned an invalid task status.")
        if row.get("status") == 1:
            result = row
            break
        if row.get("status") == 2:
            raise SongGenerationError("Song generation failed. Please try a different prompt.")
        time.sleep(2)
    if result is None:
        raise SongGenerationError("Song generation timed out. Please try again later.")

    destination = Path("data/songs") / f"{uuid4().hex}.mp3"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_request("GET", urljoin(f"{settings.music_url.rstrip('/')}/", _audio_file(result)), settings.api_key, timeout=60))
    _validate_audio(destination, duration_seconds)
    return Track(id=uuid4().hex, title=f"{mood.title()} {style.title()}", style=style.strip(), mood=mood.strip(), duration_seconds=duration_seconds, is_vocal=is_vocal, lyrics=final_lyrics, audio_path=str(destination))
