"""Deterministic transport/clock tests. No sleeping or real service requests."""
import pytest

from jukebox.models import Track
from jukebox.player import PlaybackError, Player


class Clock:
    now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Audio:
    """Fail a test immediately if a new clip starts before stop."""
    def __init__(self):
        self.active = None
        self.events = []
        self.lengths = {"one-dj": 2, "one-song": 10, "two-dj": 3, "two-song": 8}
        self.paused = False
        self.fail_play = False
        self.fail_stop = False

    def duration(self, path):
        self.events.append(("duration", path))
        return self.lengths[path]

    def play(self, path):
        assert self.active is None, "Audio overlap"
        if self.fail_play:
            raise OSError("Private transport diagnostic")
        self.active = path
        self.paused = False
        self.events.append(("play", path))

    def stop(self):
        self.events.append(("stop", self.active))
        if self.fail_stop:
            raise OSError("Private stop diagnostic")
        self.active = None
        self.paused = False

    def pause(self):
        self.paused = True
        self.events.append(("pause", self.active))

    def resume(self):
        self.paused = False
        self.events.append(("resume", self.active))


def track(track_id="one"):
    return Track(track_id, track_id.title(), "Jazz", "Calm", 30, False,
                 audio_path=f"{track_id}-song", dj_audio_path=f"{track_id}-dj")


@pytest.fixture
def setup_player():
    clock = Clock()
    audio = Audio()
    return Player(audio, clock=clock), audio, clock


def test_empty_controls_are_safe(setup_player):
    player, audio, _ = setup_player
    for action in (player.play, player.pause, player.skip, player.stop, player.tick):
        state = action()
        assert state.state == "stopped"
        assert state.now_playing is None
    assert audio.active is None


def test_complete_order_actual_durations_and_no_overlap(setup_player):
    player, audio, clock = setup_player
    player.enqueue([track(), track("two")])
    assert player.play().phase == "speech"
    for seconds, expected in [(2, "one-song"), (10, "two-dj"), (3, "two-song"), (8, None)]:
        clock.advance(seconds)
        state = player.tick()
        assert audio.active == expected
    assert state.state == "stopped"
    assert state.queued == ()
    assert [path for event, path in audio.events if event == "play"] == ["one-dj", "one-song", "two-dj", "two-song"]
    assert audio.events[:4] == [("duration", "one-dj"), ("duration", "one-song"), ("duration", "two-dj"), ("duration", "two-song")]


@pytest.mark.parametrize("phase", ["speech", "song"])
def test_pause_freezes_position_and_resume_excludes_pause_time(setup_player, phase):
    player, audio, clock = setup_player
    player.enqueue([track()])
    player.play()
    if phase == "song":
        clock.advance(2)
        player.tick()
    clock.advance(1)
    assert player.pause().position_seconds == 1
    clock.advance(100)
    assert player.tick().position_seconds == 1
    assert audio.paused
    player.play()
    clock.advance(0.5)
    state = player.tick()
    assert state.phase == phase
    assert state.position_seconds == 1.5
    assert not audio.paused


@pytest.mark.parametrize("phase", ["speech", "song"])
def test_skip_discards_whole_current_track(setup_player, phase):
    player, audio, clock = setup_player
    player.enqueue([track(), track("two")])
    player.play()
    if phase == "song":
        clock.advance(2)
        player.tick()
    state = player.skip()
    assert state.now_playing.id == "two"
    assert state.phase == "speech"
    assert audio.active == "two-dj"
    assert player.skip().state == "stopped"


def test_paused_skip_never_plays_audio_until_resumed(setup_player):
    player, audio, _ = setup_player
    player.enqueue([track(), track("two")])
    player.play()
    player.pause()
    state = player.skip()
    assert state.state == "paused"
    assert state.now_playing.id == "two"
    assert audio.active is None
    assert ("play", "two-dj") not in audio.events
    player.play()
    assert audio.active == "two-dj"


def test_stopped_skip_drops_first_queued_track_without_playing(setup_player):
    player, audio, _ = setup_player
    player.enqueue([track(), track("two")])
    assert player.skip().state == "stopped"
    assert [t.id for t in player.status().queued] == ["two"]
    assert audio.active is None
    assert player.play().now_playing.id == "two"


def test_late_poll_does_not_cut_next_clip_short(setup_player):
    player, audio, clock = setup_player
    player.enqueue([track(), track("two")])
    player.play()
    clock.advance(100)
    state = player.tick()
    assert state.phase == "song"
    assert state.position_seconds == 0
    clock.advance(9)
    assert player.tick().now_playing.id == "one"
    assert audio.active == "one-song"


@pytest.mark.parametrize("bad_duration", [0, -1, float("nan"), float("inf"), "invalid"])
def test_invalid_duration_leaves_queue_unchanged(setup_player, bad_duration):
    player, audio, _ = setup_player
    player.enqueue([track()])
    audio.lengths["two-song"] = bad_duration
    with pytest.raises(PlaybackError, match="valid durations"):
        player.enqueue([track(), track("two")])
    assert [t.id for t in player.status().queued] == ["one"]


@pytest.mark.parametrize("field", ["audio_path", "dj_audio_path"])
def test_incomplete_track_is_rejected(setup_player, field):
    player, _, _ = setup_player
    item = track()
    setattr(item, field, None)
    with pytest.raises(PlaybackError):
        player.enqueue([item])
    assert player.status().queued == ()


def test_missing_audio_is_readable_and_does_not_leak_diagnostics(setup_player):
    player, audio, _ = setup_player
    del audio.lengths["one-song"]
    with pytest.raises(PlaybackError, match="readable song") as caught:
        player.enqueue([track()])
    assert "one-song" not in str(caught.value)


def test_transport_failure_can_retry_same_clip(setup_player):
    player, audio, _ = setup_player
    player.enqueue([track(), track("two")])
    audio.fail_play = True
    with pytest.raises(PlaybackError) as caught:
        player.play()
    assert "Private" not in str(caught.value)
    assert player.status().state == "error"
    assert player.status().now_playing.id == "one"
    assert [t.id for t in player.status().queued] == ["two"]
    audio.fail_play = False
    assert player.play().state == "playing"
    assert audio.active == "one-dj"


def test_stop_failure_does_not_start_overlapping_clip(setup_player):
    player, audio, clock = setup_player
    player.enqueue([track(), track("two")])
    player.play()
    audio.fail_stop = True
    clock.advance(2)
    with pytest.raises(PlaybackError):
        player.tick()
    assert audio.active == "one-dj"
    assert ("play", "one-song") not in audio.events
    assert player.status().state == "error"
    audio.fail_stop = False
    assert player.skip().now_playing.id == "two"
    assert audio.active == "two-dj"


def test_enqueue_while_playing_and_external_mutation(setup_player):
    player, audio, _ = setup_player
    item = track()
    player.enqueue([item])
    item.audio_path = "changed"
    player.status().queued[0].audio_path = "also changed"
    player.play()
    player.enqueue([track("two")])
    player.status().now_playing.audio_path = "changed snapshot"
    assert player.status().now_playing.audio_path == "one-song"
    assert audio.active == "one-dj"
    assert [t.id for t in player.status().queued] == ["two"]


def test_stop_keeps_future_queue_and_play_does_not_restart_active_clip(setup_player):
    player, audio, _ = setup_player
    player.enqueue([track(), track("two")])
    player.play()
    player.play()
    assert audio.events.count(("play", "one-dj")) == 1
    assert player.stop().now_playing is None
    assert player.play().now_playing.id == "two"
