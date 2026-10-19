"""Fixtures communes : une petite vidéothèque générée avec ffmpeg et une instance
de l'application isolée (base et dossier vidéo propres à chaque test)."""
import importlib
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent

# Vidéothèque de test : chemin relatif -> langues des pistes audio (None = sans langue)
LIBRARY = {
    'eng.mkv': ['eng'],
    'multi.mkv': ['eng', 'spa'],
    'nolang.mkv': [None],
    'legacy.avi': ['spa'],
    'sub/fra.mp4': ['fra'],
}


def make_video(path, languages):
    """Génère une vidéo d'une seconde avec une piste audio par langue"""
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=64x48:d=1']
    for _ in languages:
        cmd += ['-f', 'lavfi', '-i', 'sine=duration=1']
    cmd += ['-map', '0:v']
    for i, _ in enumerate(languages):
        cmd += ['-map', f'{i + 1}:a']
    # Codecs intégrés à ffmpeg, sans dépendance à libx264
    cmd += ['-c:v', 'mpeg4', '-c:a', 'aac' if path.suffix != '.avi' else 'mp3']
    for i, lang in enumerate(languages):
        if lang:
            cmd += [f'-metadata:s:a:{i}', f'language={lang}']
    subprocess.run(cmd + [str(path)], check=True)


@pytest.fixture(scope='session')
def video_library(tmp_path_factory):
    if not (shutil.which('ffmpeg') and shutil.which('ffprobe')):
        pytest.skip('ffmpeg et ffprobe sont requis pour les tests')
    root = tmp_path_factory.mktemp('library')
    for rel, languages in LIBRARY.items():
        make_video(root / rel, languages)
    (root / 'corrupt.mkv').write_bytes(b'not a video' * 100)
    (root / 'notes.txt').write_text('ignoré par le scan')
    return root


@pytest.fixture
def app(tmp_path, monkeypatch, video_library):
    """Application rechargée sur une copie de la vidéothèque et une base vide"""
    videos = tmp_path / 'videos'
    shutil.copytree(video_library, videos)
    monkeypatch.setenv('VIDEOS_DIR', str(videos))
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'app.db'))
    monkeypatch.delenv('BACKUP_ON_SET_LANGUAGE', raising=False)
    # StaticFiles résout « static » par rapport au répertoire courant
    monkeypatch.chdir(REPO_ROOT)

    # La configuration est lue à l'import : on recharge le module pour chaque test
    if 'backend.main' in sys.modules:
        module = importlib.reload(sys.modules['backend.main'])
    else:
        module = importlib.import_module('backend.main')

    ctx = SimpleNamespace(client=TestClient(module.app), main=module, videos=videos, db=tmp_path / 'app.db')
    yield ctx
    # Ne laisse pas une analyse en masse déborder sur le test suivant
    wait_job(ctx.client)


def wait_job(client, timeout=30):
    """Attend la fin de l'analyse en masse en cours et retourne son état final"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get('/api/jobs/current').json()
        if not job['running']:
            return job
        time.sleep(0.05)
    raise AssertionError("L'analyse en masse ne s'est pas terminée")


def files_by_name(client):
    return {f['filename']: f for f in client.get('/api/files').json()}


def scan_and_analyze(client):
    """Scan puis analyse complète ; retourne l'état final de l'analyse"""
    assert client.post('/api/rescan').status_code == 200
    assert client.post('/api/analyze_all').status_code == 202
    return wait_job(client)
