import os
import shutil
import time

from conftest import files_by_name, scan_and_analyze, wait_job


def test_analyze_all_keeps_ids_and_reads_default_track(app):
    app.client.post('/api/rescan')
    ids_before = {name: f['id'] for name, f in files_by_name(app.client).items()}

    job = scan_and_analyze(app.client)

    files = files_by_name(app.client)
    assert {name: f['id'] for name, f in files.items()} == ids_before
    assert (job['total'], job['done'], job['errors'], job['error']) == (6, 6, 1, None)
    assert files['eng.mkv']['language'] == 'eng'
    # Langue de la piste lue par défaut (la première), pas d'une piste secondaire
    assert files['multi.mkv']['language'] == 'eng'
    assert files['fra.mp4']['language'] == 'fra'
    assert files['nolang.mkv']['status'] == 'analyzed'
    assert files['nolang.mkv']['language'] is None


def test_unreadable_file_has_error_status(app):
    scan_and_analyze(app.client)

    corrupt = files_by_name(app.client)['corrupt.mkv']

    assert corrupt['status'] == 'error'
    assert corrupt['analysis_error'] == 'Fichier illisible par ffprobe'
    assert corrupt['language'] is None


def test_missing_file_has_error_status(app):
    app.client.post('/api/rescan')
    file = files_by_name(app.client)['eng.mkv']
    os.remove(app.videos / 'eng.mkv')

    res = app.client.post(f"/api/files/{file['id']}/analyze").json()

    assert res == {'status': 'error', 'language': None, 'error': 'Fichier introuvable'}
    assert app.client.get(f"/api/files/{file['id']}").json()['status'] == 'error'


def test_analyze_new_retries_files_in_error(app):
    scan_and_analyze(app.client)
    shutil.copy(app.videos / 'eng.mkv', app.videos / 'corrupt.mkv')

    assert app.client.post('/api/analyze_new').status_code == 202
    job = wait_job(app.client)

    assert (job['total'], job['errors']) == (1, 0)
    assert files_by_name(app.client)['corrupt.mkv']['status'] == 'analyzed'


def test_missing_ffprobe_saves_nothing(app, monkeypatch):
    app.client.post('/api/rescan')
    real_run = app.main.subprocess.run

    def run_without_ffprobe(cmd, *args, **kwargs):
        if cmd[0] == 'ffprobe':
            raise FileNotFoundError('ffprobe')
        return real_run(cmd, *args, **kwargs)
    monkeypatch.setattr(app.main.subprocess, 'run', run_without_ffprobe)

    app.client.post('/api/analyze_all')
    job = wait_job(app.client)
    single = app.client.post(f"/api/files/{files_by_name(app.client)['eng.mkv']['id']}/analyze")

    assert job['error'] == 'ffprobe not found' and job['done'] == 0
    assert single.status_code == 500
    assert {f['status'] for f in files_by_name(app.client).values()} == {'not_analyzed'}


def test_bulk_analysis_runs_in_background(app, monkeypatch):
    app.client.post('/api/rescan')
    real_run = app.main.subprocess.run

    def slow_ffprobe(cmd, *args, **kwargs):
        if cmd[0] == 'ffprobe':
            time.sleep(0.2)
        return real_run(cmd, *args, **kwargs)
    monkeypatch.setattr(app.main.subprocess, 'run', slow_ffprobe)

    started = time.time()
    res = app.client.post('/api/analyze_all')
    assert res.status_code == 202 and time.time() - started < 0.5
    assert res.json()['running'] is True and res.json()['total'] == 6
    # Une seule analyse en masse à la fois, et l'API reste disponible
    assert app.client.post('/api/analyze_new').status_code == 409
    assert app.client.get('/api/files').status_code == 200

    time.sleep(0.5)
    progress = app.client.get('/api/jobs/current').json()
    assert progress['running'] and 0 < progress['done'] < 6

    job = wait_job(app.client)
    assert job['done'] == 6 and job['finished_at']


def test_unknown_file_returns_404(app):
    assert app.client.get('/api/files/999').status_code == 404
    assert app.client.post('/api/files/999/analyze').status_code == 404
    assert app.client.post('/api/files/999/reanalyze').status_code == 404
    assert app.client.get('/api/files/999/tracks').status_code == 404
