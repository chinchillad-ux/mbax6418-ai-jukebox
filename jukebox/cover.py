"""Original cover art through the class FLUX image-generation service."""
from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont

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
        temporary.write_bytes(title_overlay(image, track.title))
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
    """Request visual art only; exact typography is added locally afterward.

    Never feed the literal title or lyric verses to FLUX: even instructions
    not to print those strings can turn them into unwanted lettering.
    """
    prompt = (
        "Create an original square full-bleed illustration with no writing. "
        f"Musical style: {track.style}. Mood: {track.mood}. "
    )
    if description is not None:
        prompt += f"Visual direction: {description.strip()} "
    prompt += (
        "Reflect the musical mood through imagery, color, and composition. "
        "Do not copy an existing album cover; no lettering, logos, or watermarks. "
        "No words, titles, captions, lyrics, signatures, or typography. "
        "No signs, billboards, posters, storefronts, screens, or interfaces. "
        "Favor abstract nonrepresentational imagery rather than objects that contain writing. "
        "The song title will be typeset separately; leave the lower area uncluttered."
    )
    return prompt


def _title_layout(draw: ImageDraw.ImageDraw, title: str, width: int, height: int):
    """Fit the complete title without ellipses, including long unbroken names."""
    margin = max(1, round(width * 0.055))
    available = max(1, width - 2 * margin)
    for size in range(max(1, round(width * 0.08)), 0, -1):
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", size)
        except OSError:
            # Pillow's bundled scalable font needs no system font installation.
            font = ImageFont.load_default(size=size)
        lines = []
        line = ""
        for char in title:
            if char == "\n":
                lines.append(line)
                line = ""
                continue
            candidate = line + char
            if line and draw.textlength(candidate, font=font) > available:
                # Prefer a word break, but split a single oversized word as needed.
                split = line.rfind(" ")
                if split > 0:
                    lines.append(line[:split])
                    line = line[split + 1:] + char
                else:
                    lines.append(line)
                    line = char
            else:
                line = candidate
        lines.append(line)
        text = "\n".join(lines)
        box = draw.multiline_textbbox((0, 0), text, font=font, spacing=max(1, size // 5))
        if box[2] - box[0] <= available and box[3] - box[1] <= height * 0.30:
            return text, font, box, max(1, size // 5)
    raise CoverGenerationError("The cover image is too small to display this title.")


def title_overlay(png: bytes, title: str) -> bytes:
    """Keep the FLUX pixels, adding a readable exact-title layer to the PNG."""
    if not isinstance(title, str) or not title.strip():
        raise CoverGenerationError("A song title is required for cover art.")
    image = Image.open(BytesIO(png)).convert("RGBA")
    width, height = image.size
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    text, font, box, spacing = _title_layout(draw, title.strip(), width, height)
    start = round(height * 0.60)
    for y in range(start, height):
        alpha = round(220 * ((y - start) / max(1, height - start)) ** 0.8)
        draw.line((0, y, width, y), fill=(8, 12, 24, alpha))
    x = (width - (box[2] - box[0])) / 2 - box[0]
    y = height - height * 0.07 - (box[3] - box[1]) - box[1]
    draw.multiline_text((x, y), text, font=font, spacing=spacing,
                        align="center", fill="white")
    output = BytesIO()
    Image.alpha_composite(image, layer).convert("RGB").save(output, format="PNG")
    return output.getvalue()
