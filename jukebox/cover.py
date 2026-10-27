"""Original cover art through the class FLUX image-generation service."""
from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from PIL import Image

from jukebox.config import load_settings
from jukebox.models import Track


class CoverGenerationError(RuntimeError):
    """Readable cover-generation failure without credentials or service details."""


def generate_cover(track: Track, description: str | None = None) -> Track:
    """Request one PNG; optional visual direction augments the track's themes."""
    if description is not None:
        if not isinstance(description, str) or not 1 <= len(description.strip()) <= 2000:
            raise CoverGenerationError("Enter a cover description (1–2000 characters).")
        description = description.strip()
    settings = load_settings()
    try:
        endpoint = urlsplit(settings.cover_art_url)
        if endpoint.port == 9000:
            raise CoverGenerationError("Port 9000 is not permitted for cover art.")
        if endpoint.scheme not in {"http", "https"} or not endpoint.hostname:
            raise ValueError
    except ValueError:
        raise CoverGenerationError("Invalid cover-art URL configuration.") from None
    payload = {
        "model": settings.cover_art_model,
        "prompt": cover_prompt(track, description),
        "n": 1,
        "size": "1024x1024",
        "response_format": "b64_json",
    }
    request = Request(
        f"{settings.cover_art_url.rstrip('/')}/images/generations",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            body = response.read()
    except (OSError, ValueError):
        raise CoverGenerationError("The cover-art service is unavailable. Please try again later.") from None
    try:
        result = json.loads(body)
        encoded = result["data"][0]["b64_json"]
        if not isinstance(encoded, str):
            raise ValueError
        image = base64.b64decode(encoded, validate=True)
    except (ValueError, KeyError, IndexError, TypeError):
        raise CoverGenerationError("The cover-art service returned an invalid image response.") from None
    try:
        # Pillow tolerates a truncated IEND checksum; require the complete PNG ending.
        if not image.endswith(b"\x00\x00\x00\x00IEND\xaeB\x60\x82"):
            raise ValueError
        with Image.open(BytesIO(image)) as decoded:
            if decoded.format != "PNG":
                raise ValueError
            decoded.verify()  # Check PNG structure and chunk checksums.
        with Image.open(BytesIO(image)) as decoded:
            decoded.load()  # Also reject invalid compressed pixel data.
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise CoverGenerationError("The cover-art service returned a corrupt or invalid PNG image.") from None
    destination = Path("data/covers") / f"{uuid4().hex}.png"
    temporary = destination.with_suffix(".tmp")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(image)
        temporary.replace(destination)
    except OSError:
        raise CoverGenerationError("Could not save the cover image. Check disk space and permissions.") from None
    finally:
        temporary.unlink(missing_ok=True)
    track.cover_path = str(destination)
    if description is not None:
        track.cover_description = description.strip()
    return track


def cover_prompt(track: Track, description: str | None = None) -> str:
    """Use custom visual direction without feeding title/lyrics to the image model."""
    if description is not None:
        # Verbatim title/lyrics can become unwanted lettering despite instructions.
        # Keep musical context, but let the user's description supply the imagery.
        return (
            "Create original square album artwork. "
            f"Musical style: {track.style}. Mood: {track.mood}. "
            f"Visual direction: {description.strip()} "
            "Use expressive imagery, color, and composition to reflect this music. "
            "Do not copy an existing album cover; no lettering, logos, or watermarks."
        )
    prompt = (
        f'Create original square album artwork for "{track.title}". '
        f"Musical style: {track.style}. Mood: {track.mood}. "
        "Use expressive imagery, color, and composition to reflect this music. "
        "Do not copy an existing album cover; no lettering, logos, or watermarks."
    )
    if track.lyrics and track.lyrics.strip():
        prompt += (
            " Interpret the themes and imagery of these lyrics visually, "
            f"rather than printing the words: {track.lyrics.strip()}"
        )
    return prompt
