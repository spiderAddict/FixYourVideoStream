import os
import shutil

import pytest

from conftest import files_by_name


def test_rescan_adds_only_video_files(app):
    res = app.client.post('/api/rescan').json()

    assert res == {'status': 'ok', 'count': 6, 'removed': 0, 'purge_skipped': False}
    assert set(files_by_name(app.client)) == {
        'eng.mkv', 'multi.mkv', 'nolang.mkv', 'legacy.avi', 'fra.mp4', 'corrupt.mkv'
    }


def test_rescan_is_idempotent(app):
    app.client.post('/api/rescan')
    ids = {f['id'] for f in files_by_name(app.client).values()}

    res = app.client.post('/api/rescan').json()

    assert (res['count'], res['removed']) == (0, 0)
    assert {f['id'] for f in files_by_name(app.client).values()} == ids


def test_rescan_removes_deleted_and_adds_new_files(app):
    app.client.post('/api/rescan')
    os.remove(app.videos / 'sub' / 'fra.mp4')
    shutil.copy(app.videos / 'eng.mkv', app.videos / 'new.mkv')

    res = app.client.post('/api/rescan').json()

    assert (res['count'], res['removed'], res['purge_skipped']) == (1, 1, False)
    names = files_by_name(app.client)
    assert 'new.mkv' in names and 'fra.mp4' not in names


@pytest.mark.parametrize('state', ['empty', 'missing'])
def test_rescan_keeps_files_when_videos_dir_looks_unmounted(app, state):
    app.client.post('/api/rescan')
    shutil.rmtree(app.videos)
    if state == 'empty':
        app.videos.mkdir()

    res = app.client.post('/api/rescan').json()

    assert res['purge_skipped'] is True and res['removed'] == 0
    assert len(files_by_name(app.client)) == 6


def test_list_files_filters_by_name(app):
    app.client.post('/api/rescan')

    names = [f['filename'] for f in app.client.get('/api/files', params={'name': 'MKV'}).json()]

    assert names == sorted(['eng.mkv', 'multi.mkv', 'nolang.mkv', 'corrupt.mkv'])
