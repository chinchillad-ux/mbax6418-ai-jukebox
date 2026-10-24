"""Real sample assets + Library/Player integration; no services or audio device.

FFmpeg decodes the committed clips and ffprobe supplies their actual durations.
The playback transport and clock are simulated; audible UI playback is not tested.
Run from the repository root: python -m pytest tests/test_sample_integration.py -q
"""
from dataclasses import replace
from functools import lru_cache
import json
import math
from pathlib import Path
import shutil
import subprocess

from PIL import Image
import pytest

from jukebox.library import Library
from jukebox.models import Track
from jukebox.player import Player, PlaybackError

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=None)
def measured_duration(path):
    file = ROOT / path
    if not file.is_file():
        raise FileNotFoundError
    if not shutil.which('ffprobe'):
        pytest.fail('Sample integration requires ffprobe on PATH.')
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                             '-of', 'default=nw=1:nk=1', str(file)],
                            capture_output=True, text=True, check=True, timeout=30)
    duration = float(result.stdout.strip())
    assert math.isfinite(duration) and duration > 0
    return duration


@pytest.fixture(scope='module')
def samples():
    manifest = json.loads((ROOT / 'assets/samples/samples.json').read_text(encoding='utf-8'))
    return [Track.from_dict(row) for row in manifest]


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FileTransport:
    """Probe real files, but log transport operations without playing sound."""
    def __init__(self, clock):
        self.clock = clock
        self.active = None
        self.paused = False
        self.events = []

    def duration(self, path):
        return measured_duration(path)

    def play(self, path):
        assert self.active is None, 'Attempt to overlap audio clips'
        assert (ROOT / path).is_file()
        self.active = path
        self.paused = False
        self.events.append(('play', path, self.clock()))

    def pause(self):
        assert self.active is not None
        self.paused = True
        self.events.append(('pause', self.active, self.clock()))

    def resume(self):
        assert self.active is not None and self.paused
        self.paused = False
        self.events.append(('resume', self.active, self.clock()))

    def stop(self):
        self.events.append(('stop', self.active, self.clock()))
        self.active = None
        self.paused = False


def player_for(tracks):
    clock = Clock()
    transport = FileTransport(clock)
    player = Player(transport, clock=clock)
    player.enqueue(tracks)
    return player, transport, clock


def test_manifest_assets_are_complete_and_decodable(samples):
    assert len(samples) == 3
    assert len({t.id for t in samples}) == 3
    assert len({t.title for t in samples}) == 3
    assert any(t.is_vocal for t in samples) and any(not t.is_vocal for t in samples)
    assert shutil.which('ffmpeg'), 'Sample integration requires ffmpeg on PATH.'
    for track in samples:
        assert track.title and track.style and track.mood and track.dj_commentary
        assert bool(track.lyrics) if track.is_vocal else track.lyrics is None
        for path in (track.audio_path, track.cover_path, track.dj_audio_path):
            assert (ROOT / path).resolve().is_relative_to((ROOT / 'assets/samples').resolve())
            assert (ROOT / path).is_file()
        for path in (track.audio_path, track.dj_audio_path):
            assert measured_duration(path) > 0
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(ROOT / path), '-f', 'null', '-'],
                           check=True, capture_output=True, timeout=60)
        with Image.open(ROOT / track.cover_path) as image:
            assert image.format == 'PNG' and image.size == (1024, 1024)
            image.verify()


def test_sample_library_add_dedupe_and_restart(samples, tmp_path):
    path = tmp_path / 'data/library.json'
    library = Library(path)
    for track in samples:
        library.add(track)
    library.add(samples[0])
    restarted = Library(path)
    assert restarted.list() == samples
    for track in samples:
        assert restarted.get(track.id) == track


def test_reloaded_library_plays_all_six_clips_in_order(samples, tmp_path):
    library = Library(tmp_path / 'library.json')
    for track in samples:
        library.add(track)
    reloaded = Library(library.path).list()
    player, transport, clock = player_for(reloaded)
    expected = [path for track in reloaded for path in (track.dj_audio_path, track.audio_path)]
    state = player.play()
    for index, path in enumerate(expected):
        assert state.state == 'playing'
        assert state.now_playing.id == reloaded[index // 2].id
        assert state.phase == ('speech' if index % 2 == 0 else 'song')
        assert transport.active == path
        assert state.duration_seconds == measured_duration(path)
        clock.advance(state.duration_seconds + 0.000001)
        state = player.tick()
    assert state.state == 'stopped' and state.now_playing is None and state.queued == ()
    assert transport.active is None
    plays = [event for event in transport.events if event[0] == 'play']
    assert [event[1] for event in plays] == expected
    for index in range(len(plays) - 1):
        assert plays[index+1][2] - plays[index][2] >= measured_duration(expected[index]) - 0.000001
    assert [e[0] for e in transport.events] == ['play', 'stop'] * 6


@pytest.mark.parametrize('phase', ['speech', 'song'])
def test_real_sample_pause_resume_preserves_position(samples, phase):
    player, transport, clock = player_for(samples)
    player.play()
    if phase == 'song':
        clock.advance(player.status().duration_seconds + 0.000001)
        player.tick()
    clock.advance(0.5)
    paused = player.pause()
    assert paused.state == 'paused' and transport.paused
    clock.advance(300)
    assert player.tick().position_seconds == paused.position_seconds
    player.play()
    clock.advance(0.5)
    resumed = player.tick()
    assert resumed.phase == phase and resumed.state == 'playing'
    assert resumed.position_seconds == pytest.approx(1.0)
    assert not transport.paused


@pytest.mark.parametrize('phase', ['speech', 'song'])
def test_real_sample_skip_advances_to_next_intro(samples, phase):
    player, transport, clock = player_for(samples)
    player.play()
    if phase == 'song':
        clock.advance(player.status().duration_seconds + 0.000001)
        player.tick()
    state = player.skip()
    assert state.now_playing.id == samples[1].id
    assert state.phase == 'speech' and transport.active == samples[1].dj_audio_path


def test_paused_skip_is_silent_until_resume(samples):
    player, transport, clock = player_for(samples)
    player.play()
    player.pause()
    state = player.skip()
    assert state.state == 'paused' and state.now_playing.id == samples[1].id
    assert transport.active is None
    assert len([event for event in transport.events if event[0] == 'play']) == 1
    player.play()
    assert transport.active == samples[1].dj_audio_path


def test_final_sample_skip_stops_cleanly(samples):
    player, transport, clock = player_for([samples[-1]])
    player.play()
    state = player.skip()
    assert state.state == 'stopped' and state.now_playing is None
    assert transport.active is None and state.queued == ()


def test_missing_sample_audio_is_recoverable(samples):
    player, transport, clock = player_for([samples[0]])
    before = player.status().queued
    with pytest.raises(PlaybackError, match='readable song and DJ audio'):
        player.enqueue([replace(samples[1], audio_path='assets/samples/nonexistent.mp3')])
    assert player.status().queued == before
    player.enqueue([samples[1]])
    assert len(player.status().queued) == 2
    assert player.play().state == 'playing'


def test_late_tick_preserves_next_real_clip(samples):
    player, transport, clock = player_for(samples)
    player.play()
    clock.advance(600)
    state = player.tick()
    assert state.phase == 'song' and state.position_seconds == 0
    assert state.duration_seconds == measured_duration(samples[0].audio_path)
    assert transport.active == samples[0].audio_path
