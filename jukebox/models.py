"""Track — the cross-feature contract of the AI Jukebox.

Every feature (song generation, cover art, DJ speech, queue/playback, UI)
builds on this model. Keep it minimal and stable: changing its fields after
later issues land requires a PR that updates every consumer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Track:
    id: str
    title: str
    style: str
    mood: str
    duration_seconds: int
    is_vocal: bool
    lyrics: str | None = None  # None for instrumental tracks
    audio_path: str | None = None  # set by song generation (issue #2)
    cover_path: str | None = None  # set by cover art (issue #3)
    dj_commentary: str | None = None  # set by the AI DJ (issue #4)
    dj_audio_path: str | None = None  # set by the AI DJ (issue #4)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        return cls(**data)
