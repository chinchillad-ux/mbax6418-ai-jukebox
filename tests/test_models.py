"""Track model: the cross-feature contract."""
from jukebox.models import Track


def _track() -> Track:
    return Track(
        id="t1",
        title="Midnight Drive",
        style="Synthwave",
        mood="Melancholic",
        duration_seconds=120,
        is_vocal=True,
        lyrics="Neon lights on an empty road...",
    )


def test_round_trip_preserves_all_fields():
    track = _track()
    assert Track.from_dict(track.to_dict()) == track


def test_dict_contains_contract_fields():
    data = _track().to_dict()
    expected = {
        "id", "title", "style", "mood", "duration_seconds", "is_vocal",
        "lyrics", "audio_path", "cover_path", "dj_commentary", "dj_audio_path", "cover_description",
    }
    assert set(data) == expected


def test_instrumental_track_has_no_lyrics():
    track = Track(
        id="t2",
        title="Rain on Glass",
        style="Lo-fi",
        mood="Calm",
        duration_seconds=90,
        is_vocal=False,
    )
    assert track.lyrics is None
    assert Track.from_dict(track.to_dict()) == track


def test_optional_generation_fields_default_to_none():
    track = _track()
    for field in ("audio_path", "cover_path", "dj_commentary", "dj_audio_path"):
        assert getattr(track, field) is None
