"""Qwen title requests, validation, and retaining audio on naming failures."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from jukebox import music


@pytest.mark.parametrize('lyrics', [None, 'Paper boats sailing toward the morning sun'])
def test_title_request_uses_correct_context_and_class_model(monkeypatch, lyrics):
    request = Mock(return_value={'choices':[{'message':{'content':json.dumps({'title':'Paper Boats at Dawn'})}}]})
    monkeypatch.setattr(music, '_json', request)
    assert music._creative_title('Electronic','Hopeful',lyrics,url='http://example.test:9001/v1',model='class-qwen',key='dummy') == 'Paper Boats at Dawn'
    args = request.call_args.args
    assert args[:3] == ('POST','http://example.test:9001/v1/chat/completions','dummy')
    payload=args[3]
    assert payload['model']=='class-qwen'
    context=json.loads(payload['messages'][1]['content'])
    assert context['lyrics']==lyrics
    assert context['mode']==('vocal' if lyrics else 'instrumental')
    assert 'Do not just concatenate' in payload['messages'][0]['content']


@pytest.mark.parametrize('content', ['', '{}', 'not JSON', '{"title":12}', '{"title":""}',
                                    '{"title":"Hopeful Electronic"}', '{"title":"Electronic Hopeful"}',
                                    json.dumps({'title':'X'*81}), json.dumps({'title':'line\nbreak'})])
def test_invalid_model_title_is_rejected(monkeypatch, content):
    monkeypatch.setattr(music,'_json',lambda *a,**k:{'choices':[{'message':{'content':content}}]})
    with pytest.raises(music.SongGenerationError,match='title'):
        music._creative_title('Electronic','Hopeful',None,url='http://example.test:9001/v1',model='qwen',key='dummy')


def test_fenced_json_is_accepted(monkeypatch):
    monkeypatch.setattr(music,'_json',lambda *a,**k:{'choices':[{'message':{'content':'```json\n{"title":"Neon Afterglow"}\n```'}}]})
    assert music._creative_title('Electronic','Hopeful',None,url='http://example.test:9001/v1',model='qwen',key='dummy')=='Neon Afterglow'


@pytest.mark.parametrize('failed_title', [False,True])
def test_generated_audio_survives_title_failure_and_title_precedes_cover(monkeypatch,tmp_path,failed_title):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(music,'load_settings',lambda:SimpleNamespace(music_url='http://example.test:9007',llm_url='http://example.test:9001/v1',api_key='dummy',music_model='ace',llm_model='qwen'))
    def reply(method,url,key,payload):
        if url.endswith('/release_task'):
            return {'data':{'task_id':'task'}}
        return {'data':[{'status':1,'result':[{'file':'/audio'}]}]}
    monkeypatch.setattr(music,'_json',reply)
    monkeypatch.setattr(music,'_request',lambda *a,**kw:b'playable-audio-fixture')
    validated=[]
    monkeypatch.setattr(music,'_validate_audio',lambda path,seconds:validated.append(path))
    def title(*a,**kw):
        assert validated and validated[0].is_file()
        if failed_title:
            raise music.SongGenerationError('Title service unavailable')
        return 'Neon Afterglow'
    monkeypatch.setattr(music,'_creative_title',title)
    track=music.generate_song('Electronic','Hopeful',30,False)
    assert Path(track.audio_path).read_bytes()==b'playable-audio-fixture'
    assert track.title.startswith('Untitled Track ') if failed_title else track.title=='Neon Afterglow'
    assert track.cover_path is None and track.dj_commentary is None


def test_title_http_failure_is_safe(monkeypatch):
    from http.client import IncompleteRead
    monkeypatch.setattr(music,'urlopen',Mock(side_effect=IncompleteRead(b'partial')))
    with pytest.raises(music.SongGenerationError):
        music._creative_title('Pop','Happy',None,url='http://example.test:9001/v1',model='qwen',key='dummy')
