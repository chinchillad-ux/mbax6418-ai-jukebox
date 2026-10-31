"""Library removal: durable metadata changes, retained assets and UI reset."""
from pathlib import Path
from dataclasses import replace
from unittest.mock import Mock

import pytest

from jukebox import app
from jukebox.library import Library, LibraryError
from jukebox.models import Track


@pytest.fixture
def songs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    library = Library()
    tracks = []
    for index in range(2):
        music = tmp_path / f'music{index}.mp3'
        cover = tmp_path / f'cover{index}.png'
        speech = tmp_path / f'dj{index}.mp3'
        for file in (music, cover, speech):
            file.write_bytes(b'preserved media')
        track = Track(str(index), f'Song {index}', 'Pop', 'Happy', 30, False,
                      audio_path=str(music), cover_path=str(cover),
                      dj_audio_path=str(speech), dj_commentary='Introduction')
        library.add(track)
        tracks.append(track)
    return library, tracks


def test_remove_persists_and_preserves_media(songs):
    library, tracks = songs
    assert library.remove(tracks[0].id) == tracks[0]
    assert Library().list() == [tracks[1]]
    assert library.list() == [tracks[1]]
    for track in tracks:
        for path in (track.audio_path, track.cover_path, track.dj_audio_path):
            assert Path(path).read_bytes() == b'preserved media'


def test_remove_from_stale_instance_keeps_new_records(songs):
    library, tracks = songs
    Library().add(replace(tracks[1], id='new', title='New song'))
    library.remove(tracks[0].id)
    assert [track.id for track in Library().list()] == [tracks[1].id, 'new']


def test_failed_remove_preserves_disk_and_memory(songs, monkeypatch):
    library, tracks = songs
    old = library.path.read_bytes()
    monkeypatch.setattr('jukebox.library.os.replace', Mock(side_effect=OSError('disk failure')))
    with pytest.raises(LibraryError):
        library.remove(tracks[0].id)
    assert library.path.read_bytes() == old
    assert library.list() == tracks
    assert not list(library.path.parent.glob('.library-*.tmp'))


def test_missing_id_is_noop_and_final_removal_survives_restart(songs):
    library, tracks = songs
    assert library.remove('missing') is None
    for track in tracks:
        library.remove(track.id)
    assert Library().list() == []


def test_inflight_update_cannot_restore_removed_track(songs):
    library, tracks = songs
    library.remove(tracks[0].id)
    with pytest.raises(LibraryError, match='not found'):
        library.update(tracks[0].id, cover_path='late-result.png')
    assert Library().get(tracks[0].id) is None


def test_remove_ui_refreshes_choices_and_stops_all_previews(songs):
    library, tracks = songs
    output = app.remove_and_refresh(tracks[0].id, [tracks[0].id, tracks[1].id])
    assert len(output) == 18
    assert output[0].startswith('✅') and 'Media files kept' in output[0]
    assert '1 saved song' in output[2]
    assert output[3]['value'] is None
    assert output[4]['choices'] == [(tracks[1].title, tracks[1].id)]
    assert output[5]['value'] == [tracks[1].id]
    assert output[6:10] == (None, None, None, None)
    assert output[10] == {'ids': [], 'index': 0, 'phase': None}
    assert tracks[1].title in output[11] and tracks[0].title not in output[11]
    assert output[15:] == ('', '', None)


@pytest.mark.parametrize('track_id', [None, 'missing'])
def test_invalid_removal_does_not_clear_playback(songs, track_id):
    _, tracks = songs
    output = app.remove_and_refresh(track_id, [tracks[0].id])
    assert output[0].startswith('⚠️')
    assert all(value == app.gr.skip() for value in output[1:])
    assert Library().list() == tracks


def test_ui_save_failure_keeps_playback_and_selection(songs, monkeypatch):
    _, tracks = songs
    monkeypatch.setattr(Library, 'remove', Mock(side_effect=LibraryError('disk failure')))
    output = app.remove_and_refresh(tracks[0].id, [tracks[0].id])
    assert output[0].startswith('⚠️')
    assert all(value == app.gr.skip() for value in output[1:])


def test_bundled_sample_is_restorable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app.import_demo_tracks()
    library = Library()
    original = library.list()
    assert len(original) == 3
    library.remove(original[0].id)
    assert len(Library().list()) == 2
    app.import_demo_tracks()
    assert len(Library().list()) == 3
    assert Library().get(original[0].id) == original[0]


def test_removal_api_is_wired_to_all_reset_outputs(songs, monkeypatch):
    monkeypatch.setenv('GRADIO_ANALYTICS_ENABLED', 'False')
    config = app.build_app().get_config_file()
    endpoint = next(item for item in config['dependencies'] if item.get('api_name') == 'remove_library_song')
    assert len(endpoint['inputs']) == 2 and len(endpoint['outputs']) == 18


def test_removal_over_real_gradio_http(songs, monkeypatch):
    from gradio_client import Client
    library, tracks = songs
    monkeypatch.setenv('GRADIO_ANALYTICS_ENABLED', 'False')
    demo = app.build_app()
    try:
        _, url, _ = demo.launch(server_name='127.0.0.1', prevent_thread_lock=True, quiet=True,
                                 allowed_paths=[str(Path.cwd())])
        client = Client(url, verbose=False)
        output = client.predict(tracks[0].id, [track.id for track in tracks], api_name='/remove_library_song')
        assert output[0].startswith('✅')
        assert Library().get(tracks[0].id) is None
        assert Library().get(tracks[1].id) == tracks[1]
        assert Path(tracks[0].audio_path).is_file()
    finally:
        demo.close()
