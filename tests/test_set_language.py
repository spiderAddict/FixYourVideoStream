import pytest

from conftest import files_by_name


def file_id(app, name):
    app.client.post('/api/rescan')
    return files_by_name(app.client)[name]['id']


def set_language(app, fid, language, track=0):
    return app.client.post(f'/api/files/{fid}/set_language', json={'language': language, 'track': track})


def track_languages(app, fid):
    return [t['language'] for t in app.client.get(f'/api/files/{fid}/tracks').json()['tracks']]


def test_language_is_set_on_the_chosen_track(app):
    fid = file_id(app, 'multi.mkv')

    res = set_language(app, fid, 'fra', track=1)

    assert res.status_code == 200
    assert track_languages(app, fid) == ['eng', 'fra']
    # La langue affichée reste celle de la piste par défaut
    assert res.json()['language'] == 'eng'
    assert app.client.get(f'/api/files/{fid}').json()['language'] == 'eng'


def test_language_change_on_default_track_updates_file_language(app):
    fid = file_id(app, 'eng.mkv')

    assert set_language(app, fid, 'fra').status_code == 200

    assert track_languages(app, fid) == ['fra']
    assert app.client.get(f'/api/files/{fid}').json()['language'] == 'fra'


def test_unknown_track_is_rejected(app):
    fid = file_id(app, 'eng.mkv')

    assert set_language(app, fid, 'fra', track=3).status_code == 400
    assert track_languages(app, fid) == ['eng']


def test_avi_is_refused(app):
    fid = file_id(app, 'legacy.avi')

    assert app.client.get(f'/api/files/{fid}/tracks').json()['language_editable'] is False
    assert set_language(app, fid, 'fra').status_code == 400


@pytest.mark.parametrize('language', ['fr', 'french', 'xxx', 'qaa', '', 'fra; rm', '<script>'])
def test_invalid_language_is_rejected(app, language):
    fid = file_id(app, 'eng.mkv')
    before = (app.videos / 'eng.mkv').read_bytes()

    assert set_language(app, fid, language).status_code == 422
    assert (app.videos / 'eng.mkv').read_bytes() == before


# « und » est la valeur par défaut en MKV : aucune balise n'est écrite
@pytest.mark.parametrize('language, stored', [('FRE', 'fre'), (' fra\n', 'fra'), ('und', None)])
def test_language_code_is_normalized(app, language, stored):
    fid = file_id(app, 'eng.mkv')

    assert set_language(app, fid, language).status_code == 200
    assert track_languages(app, fid) == [stored]


def test_no_backup_by_default(app):
    fid = file_id(app, 'eng.mkv')

    set_language(app, fid, 'fra')

    assert not (app.videos / 'eng.mkv.bak').exists()


def test_backup_keeps_the_very_first_original(app, monkeypatch):
    monkeypatch.setattr(app.main, 'BACKUP_ON_SET_LANGUAGE', True)
    fid = file_id(app, 'eng.mkv')
    original = (app.videos / 'eng.mkv').read_bytes()

    set_language(app, fid, 'fra')
    set_language(app, fid, 'spa')

    assert (app.videos / 'eng.mkv.bak').read_bytes() == original
    assert track_languages(app, fid) == ['spa']
    # Le .bak n'est pas une vidéo pour le scan
    assert app.client.post('/api/rescan').json()['count'] == 0
