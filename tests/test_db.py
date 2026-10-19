import importlib
import sqlite3
import sys

from conftest import files_by_name, scan_and_analyze


def test_every_connection_is_closed(app, monkeypatch):
    opened = []
    real_get_conn = app.main.get_conn

    def tracked_get_conn():
        conn = real_get_conn()
        opened.append(conn)
        return conn
    monkeypatch.setattr(app.main, 'get_conn', tracked_get_conn)

    scan_and_analyze(app.client)
    fid = files_by_name(app.client)['eng.mkv']['id']
    app.client.post(f'/api/files/{fid}/reanalyze')
    app.client.post(f'/api/files/{fid}/set_language', json={'language': 'fra', 'track': 9})
    app.client.post('/api/theme', json={'theme': 'sonarr'})

    assert opened
    for conn in opened:
        # Une connexion fermée refuse toute requête
        try:
            conn.execute('SELECT 1')
        except sqlite3.ProgrammingError:
            continue
        raise AssertionError('connexion SQLite restée ouverte')


def test_old_database_is_migrated(app):
    # Base au format d'avant la colonne analysis_error
    app.db.unlink()
    conn = sqlite3.connect(app.db)
    conn.execute('CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT UNIQUE, filename TEXT, '
                 'language TEXT, analyzed_at TEXT)')
    conn.execute("INSERT INTO files VALUES (1, '/videos/old.mkv', 'old.mkv', 'eng', '2025-01-01T00:00:00')")
    conn.commit()
    conn.close()

    importlib.reload(sys.modules['backend.main'])
    old = app.client.get('/api/files/1').json()

    assert (old['language'], old['status'], old['analysis_error']) == ('eng', 'analyzed', None)


def test_theme_is_saved(app):
    assert app.client.get('/api/theme').json() == {'theme': 'plex'}
    assert app.client.post('/api/theme', json={'theme': 'jellyfin'}).status_code == 200
    assert app.client.get('/api/theme').json() == {'theme': 'jellyfin'}
    assert app.client.post('/api/theme', json={'theme': 'neon'}).status_code == 400
