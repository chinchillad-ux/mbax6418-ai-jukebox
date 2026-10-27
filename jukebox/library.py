"""Persistent session library. Runtime metadata stays in ignored ``data/``."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from threading import RLock

from jukebox.models import Track

_LIBRARY_WRITE_LOCK = RLock()
class LibraryError(RuntimeError):
    """A readable library failure; the previous saved library is preserved."""


def _copy(track: Track) -> Track:
    if not isinstance(track, Track) or not isinstance(track.id, str) or not track.id.strip():
        raise LibraryError("A library track must have a nonempty ID.")
    return Track.from_dict(track.to_dict())


class Library:
    """Load on construction, persist on add, and deduplicate by Track ID.

    Adding an existing ID replaces its metadata without changing its position.
    Returned Tracks are copies: call ``add`` after generation updates a Track to
    save the new paths. A failed write changes neither memory nor the old file.
    """

    def __init__(self, path: str | Path = "data/library.json") -> None:
        self.path = Path(path)
        self._tracks: dict[str, Track] = {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("tracks"), list):
                raise ValueError
            for record in payload["tracks"]:
                track = _copy(Track.from_dict(record))
                if track.id in self._tracks:
                    raise ValueError
                self._tracks[track.id] = track
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, LibraryError):
            raise LibraryError("The saved library could not be loaded. Keep the file for recovery before replacing it.") from None

    def list(self) -> list[Track]:
        """Return tracks in insertion order, independent of the saved objects."""
        return [_copy(track) for track in self._tracks.values()]

    def get(self, track_id: str) -> Track | None:
        track = self._tracks.get(track_id)
        return _copy(track) if track is not None else None

    
    def update(self, track_id: str, *, expected_title: str | None = None, **changes) -> Track:
        """Patch editable fields on the latest record, without stale-record overwrites.

        The lock covers reload through atomic save within this app process.
        Long-running DJ requests may commit only if their title is still current.
        """
        allowed = {"title", "cover_path", "cover_description", "dj_commentary", "dj_audio_path"}
        if not changes.keys() <= allowed:
            raise LibraryError("Only song title, artwork, and DJ metadata can be edited.")
        with _LIBRARY_WRITE_LOCK:
            track = Library(self.path).get(track_id)
            if track is None:
                raise LibraryError("Song not found in your library.")
            if expected_title is not None and track.title != expected_title:
                raise LibraryError("The song title changed. Generate a new DJ introduction.")
            if "title" in changes and changes["title"] != track.title:
                changes = {**changes, "dj_commentary": None, "dj_audio_path": None}
            for field, value in changes.items():
                setattr(track, field, value)
            return self.add(track)

    def add(self, track: Track) -> Track:
        saved = _copy(track)

        with _LIBRARY_WRITE_LOCK:
            # Reload the latest library before saving.
            latest = Library(self.path)
            candidate = {**latest._tracks, saved.id: saved}
            temporary: Path | None = None

            try:
                encoded = json.dumps(
                    {
                        "version": 1,
                        "tracks": [
                            t.to_dict() for t in candidate.values()
                        ]
                    },
                    ensure_ascii=False,
                    allow_nan=False
                )

                self.path.parent.mkdir(
                    parents=True, exist_ok=True
                )

                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=".library-",
                    suffix=".tmp",
                    delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())

                os.replace(temporary, self.path)

            except (OSError, ValueError, TypeError):
                raise LibraryError(
                    "The library could not be saved. "
                    "Check disk space and folder permissions, "
                    "then retry."
                ) from None

            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass

            self._tracks = candidate

        return _copy(saved)
