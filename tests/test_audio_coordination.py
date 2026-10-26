from jukebox.app import build_app


def test_all_audio_players_have_client_side_coordination():
    config = build_app().config
    audio = [c for c in config['components'] if c['type'] == 'audio']
    assert len(audio) == 4
    for component in audio:
        handlers = [d for d in config['dependencies']
                    if (component['id'], 'play') in [tuple(t) for t in d['targets']]]
        assert any(d.get('js') and 'pause()' in d['js'] and
                   component['props']['elem_id'] in d['js'] for d in handlers)
