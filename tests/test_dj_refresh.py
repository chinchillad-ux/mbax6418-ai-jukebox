from jukebox import app
from jukebox.library import Library
from jukebox.models import Track


def test_dj_refresh_finds_new_songs_and_preserves_valid_selections(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    library = Library()
    assert app.refresh_dj_songs()[0]['choices'] == []
    library.add(Track(id='new', title='New song', style='pop', mood='happy',
                      duration_seconds=30, is_vocal=False,
                      audio_path='song.mp3', dj_audio_path='intro.mp3'))
    songs, playlist = app.refresh_dj_songs('new', ['missing', 'new'])
    assert songs['choices'] == [('New song', 'new')]
    assert songs['value'] == 'new'
    assert playlist['value'] == ['new']
    library.update('new', dj_audio_path=None)
    songs, playlist = app.refresh_dj_songs('missing', ['new'])
    assert songs['value'] is None
    assert playlist['value'] == []


def test_dj_choices_refresh_on_page_load_and_tab_entry():
    config = app.build_app().config
    picker = next(c['id'] for c in config['components']
                  if c['props'].get('elem_id') == 'dj-song-picker')
    dj_tab = next(c['id'] for c in config['components']
                  if c['props'].get('elem_id') == 'ai-dj-tab')
    dependencies = [d for d in config['dependencies'] if picker in d['outputs']]
    assert any(any(t[1] == 'load' for t in d['targets']) for d in dependencies)
    assert any([dj_tab, 'select'] in [list(t) for t in d['targets']]
               for d in dependencies)
