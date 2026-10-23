"""UI-independent playback sequencer with an injected audio transport and clock.

The UI must supply an AudioBackend and call tick regularly. No background
threads or audio devices are started on import. All calls belong on the same
UI/controller thread; pause/skip stop or suspend the actual transport as well
as updating the state. A late tick delays the next clip rather than overlapping.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import time
from typing import Callable, Literal, Protocol

from jukebox.models import Track


class PlaybackError(RuntimeError):
    """Safe playback error, suitable for the UI's retry action."""


class AudioBackend(Protocol):
    """Adapter supplied by issue #6; methods must finish before returning.

    duration must inspect the actual audio, not the requested song length.
    play starts one clip from its beginning. pause/resume retain its position.
    stop must silence/reset the active clip before returning. The backend must
    not auto-play another clip or loop. tick's clock and this adapter must share
    playback timing (normal 1x speed); browser adapters should drive transitions
    from media timing/end events rather than an unrelated server timer.
    """

    def duration(self, path: str) -> float: ...
    def play(self, path: str) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def stop(self) -> None: ...


@dataclass(frozen=True)
class PlaybackStatus:
    state: Literal["stopped", "playing", "paused", "error"]
    now_playing: Track | None
    phase: Literal["speech", "song"] | None
    position_seconds: float
    duration_seconds: float
    queued: tuple[Track, ...]
    error: str | None


@dataclass(frozen=True)
class _Item:
    track: Track
    speech_duration: float
    song_duration: float


class Player:
    """speech -> song -> next speech, with explicit polling via ``tick``.

    Enqueue validates the complete batch before changing the queue. Every track
    needs generated speech and song paths with positive, finite durations.
    The caller may enqueue the same track more than once. A library may contain
    incomplete tracks, but they cannot be queued until both audio clips exist.
    """

    def __init__(self, backend: AudioBackend, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._backend = backend
        self._clock = clock
        self._queue: deque[_Item] = deque()
        self._current: _Item | None = None
        self._phase: Literal["speech", "song"] | None = None
        self._state: Literal["stopped", "playing", "paused", "error"] = "stopped"
        self._position = 0.0
        self._started = 0.0
        self._error: str | None = None
        self._clip_started = False

    def enqueue(self, tracks: list[Track]) -> PlaybackStatus:
        batch = []
        try:
            for track in tracks:
                if not isinstance(track, Track) or not track.audio_path or not track.dj_audio_path:
                    raise ValueError
                copied = Track.from_dict(track.to_dict())
                durations = [float(self._backend.duration(path)) for path in (copied.dj_audio_path, copied.audio_path)]
                if not all(math.isfinite(d) and d > 0 for d in durations):
                    raise ValueError
                batch.append(_Item(copied, *durations))
        except Exception:
            raise PlaybackError("Each queued track needs readable song and DJ audio with valid durations.") from None
        self._queue.extend(batch)
        return self.status()

    def _duration(self) -> float:
        if self._current is None:
            return 0.0
        return self._current.speech_duration if self._phase == "speech" else self._current.song_duration

    def _call(self, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception:
            self._state = "error"
            self._error = "Playback failed. Check the audio output and files, then retry or skip."
            try:
                self._backend.stop()
            except Exception:
                pass
            raise PlaybackError(self._error) from None

    def _start_clip(self) -> None:
        assert self._current is not None
        path = self._current.track.dj_audio_path if self._phase == "speech" else self._current.track.audio_path
        self._position = 0.0
        self._call(lambda: self._backend.play(path))
        self._started = self._clock()
        self._state = "playing"
        self._clip_started = True
        self._error = None

    def _next(self, *, start: bool = True) -> None:
        self._current = self._queue.popleft() if self._queue else None
        self._phase = "speech" if self._current is not None else None
        self._position = 0.0
        self._error = None
        self._clip_started = False
        if self._current is None:
            self._state = "stopped"
        elif start:
            self._start_clip()
        else:
            self._state = "paused"

    def status(self) -> PlaybackStatus:
        """Snapshot only. ``tick`` performs automatic advancement."""
        position = self._position
        if self._state == "playing":
            position += max(0.0, self._clock() - self._started)
        copy = lambda t: Track.from_dict(t.to_dict())
        return PlaybackStatus(self._state, copy(self._current.track) if self._current else None,
                              self._phase, min(position, self._duration()), self._duration(),
                              tuple(copy(item.track) for item in self._queue), self._error)

    def play(self) -> PlaybackStatus:
        if self._state == "paused":
            if not self._clip_started:
                self._start_clip()
            else:
                self._call(self._backend.resume)
                self._started = self._clock()
                self._state = "playing"
        elif self._state == "error" and self._current is not None:
            # Retry the failed clip from its beginning, after confirming silence.
            self._call(self._backend.stop)
            self._start_clip()
        elif self._state == "stopped":
            self._next()
        return self.tick()

    def pause(self) -> PlaybackStatus:
        self.tick()
        if self._state == "playing":
            position = self.status().position_seconds
            self._call(self._backend.pause)
            self._position = position
            self._state = "paused"
        return self.status()

    def skip(self) -> PlaybackStatus:
        """Discard the current track, including any unplayed song segment.

        A paused skip selects the next track but stays paused. A stopped skip
        discards the first queued track without starting playback.
        """
        was_paused = self._state == "paused"
        was_stopped = self._state == "stopped"
        self._call(self._backend.stop)
        if was_stopped:
            if self._queue:
                self._queue.popleft()
        else:
            self._next(start=not was_paused)
        return self.status()

    def stop(self) -> PlaybackStatus:
        """Stop and discard the current track; keep future queued tracks."""
        self._call(self._backend.stop)
        self._current = None
        self._phase = None
        self._position = 0.0
        self._state = "stopped"
        self._error = None
        return self.status()

    def tick(self) -> PlaybackStatus:
        """Advance a completed clip. The next clip starts at this tick's time.

        No accumulated timer overshoot is carried into the next clip: if the UI
        polls late, the next speech/song still gets its complete playback time.
        """
        if self._state == "playing" and self.status().position_seconds >= self._duration():
            self._call(self._backend.stop)
            if self._phase == "speech":
                self._phase = "song"
                self._start_clip()
            else:
                self._next()
        return self.status()
