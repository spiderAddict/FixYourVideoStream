import os
import sqlite3
import subprocess
import json
import tempfile
import shutil
import logging
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path

VIDEOS_DIR = os.environ.get("VIDEOS_DIR", "/videos")
DB_PATH = os.environ.get("DB_PATH", "app.db")

VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v'}

# --- Configuration du logger ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount('/static', StaticFiles(directory="static", html=True), name="static")

@app.get("/")
def root():
    return FileResponse("static/index.html")

# -------------------------
# Base de données SQLite
# -------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    logger.info(f"Initialisation de la base")
        
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY,
        path TEXT UNIQUE,
        filename TEXT,
        language TEXT,
        analyzed_at TEXT
    )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    conn.commit()
    conn.close()

init_db()

# -------------------------
# Analyse avec ffprobe
# -------------------------
def ffprobe_get_audio_language(path):
    try:
        logger.info(f"Analyse du fichier audio avec ffprobe: {path}")
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', str(path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        j = json.loads(res.stdout)
        streams = j.get('streams', [])
        for s in streams:
            if s.get('codec_type') == 'audio':
                tags = s.get('tags') or {}
                lang = tags.get('language') or tags.get('LANGUAGE')
                if lang:
                    return lang
        return None
    except subprocess.CalledProcessError:
        return None

def scan_directory():
    """Retourne la liste des fichiers vidéo trouvés dans VIDEOS_DIR"""
    p = Path(VIDEOS_DIR)
    files = []
    if not p.exists():
        return files
    for f in p.rglob('*'):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS:
            files.append(f)
    return files


@app.get('/api/theme')
def get_theme():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key="theme"')
    r = c.fetchone()
    conn.close()
    if r:
        return {"theme": r['value']}
    return {"theme": "plex"}  # valeur par défaut

class ThemeModel(BaseModel):
    theme: str

@app.post('/api/theme')
def set_theme(model: ThemeModel):
    if model.theme not in ["plex", "sonarr", "jellyfin"]:
        raise HTTPException(status_code=400, detail="Invalid theme")
    conn = get_conn()
    c = conn.cursor()
    c.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', ("theme", model.theme))
    conn.commit()
    conn.close()
    return {"status": "ok", "theme": model.theme}


# -------------------------
# Endpoints API
# -------------------------
@app.get('/api/files')
def list_files(name: str = Query(None, description="Filtre sur le nom du fichier")):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT id, path, filename, language, analyzed_at FROM files')
    rows = {r['path']: dict(r) for r in c.fetchall()}
    conn.close()

    result = []
    for f in scan_directory():
        pathstr = str(f)
        if pathstr in rows:
            r = rows[pathstr]
            item = {
                'id': r['id'],
                'filename': r['filename'],
                'path': r['path'],
                'language': r['language'],
                'analyzed_at': r['analyzed_at'],
                'analyzed': bool(r['analyzed_at'])
            }
        else:
            # Fichier pas encore en base
            item = {
                'id': None,
                'filename': f.name,
                'path': pathstr,
                'language': None,
                'analyzed_at': None,
                'analyzed': False
            }
        if name is None or name.lower() in item['filename'].lower():
            result.append(item)
    return sorted(result, key=lambda x: x['filename'])

@app.get('/api/files/{file_id}')
def get_file(file_id: int):

    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT id, filename, path, language, analyzed_at FROM files WHERE id=?', (file_id,))
    r = c.fetchone()
    conn.close()
    if not r:
        logger.error(f"Fichier non trouvé pour reanalyse: id={file_id}")
        raise HTTPException(status_code=404, detail='File not found')
    return dict(r)

@app.post('/api/rescan')
def analyze_new():
    logger.info(f"Analyser tous les fichiers dans {VIDEOS_DIR}")
    files = scan_directory()
    conn = get_conn()
    c = conn.cursor()

    count = 0

    for f in files:
        pathstr = str(f)
        filename = f.name
        c.execute('SELECT id FROM files WHERE path=?', (pathstr,))
        if c.fetchone():
            continue  # déjà en base
        else:
            c.execute(
                'INSERT INTO files (path, filename) VALUES (?,?)',
                (pathstr, filename)
            )
            count += 1
    conn.commit()
    conn.close()

    conn = get_conn()
    c = conn.cursor()
    return {'status': 'ok', 'count': count}
    

@app.post('/api/analyze_all')
def analyze_all():
    logger.info("Analyser tous les fichiers")
    
    conn = get_conn()
    c = conn.cursor()
    # Parcours les fichiers déjà en base
    c.execute('SELECT id, path, filename FROM files')
    files = c.fetchall()
    count = len(files) 

    for file in files:
        file_id = file['id']
        file_path = file['path']
        file_filename = file['filename']
        lang = ffprobe_get_audio_language(file_path)
        analyzed_at = datetime.utcnow().isoformat()
        c.execute('SELECT id FROM files WHERE path=?', (file_path,))
        if c.fetchone():
            c.execute(
                'UPDATE files SET filename=?, language=?, analyzed_at=? WHERE path=?',
                (file_filename, lang, analyzed_at, file_path)
            )
        else:
            c.execute(
                'INSERT INTO files (path, filename, language, analyzed_at) VALUES (?,?,?,?)',
                (file_path, file_filename, lang, analyzed_at)
            )
    conn.commit()
    conn.close()
    return {'status': 'ok', 'count': count}

@app.post('/api/analyze_new')
def analyze_new():        
    logger.info("Analyser tous les fichiers pas encore analysé")
    
    conn = get_conn()
    c = conn.cursor()
    # Parcours les fichiers déjà en base, mais non analysés, analyzed_at == null    
    c.execute('SELECT id, path, filename FROM files WHERE analyzed_at IS NULL')
    files = c.fetchall()
    count = len(files)

    for file in files:
        file_id = file['id']
        file_path = file['path']
        file_filename = file['filename']
        lang = ffprobe_get_audio_language(file_path)
        analyzed_at = datetime.utcnow().isoformat()
        c.execute(
            'INSERT INTO files (path, filename, language, analyzed_at) VALUES (?,?,?,?)',
            (file_path, file_filename, lang, analyzed_at)
        )
    conn.commit()
    conn.close()
    conn = get_conn()
    c = conn.cursor()
    return {'status': 'ok', 'count': count}

# -------------------------
# Modèle Pydantic
# -------------------------
class AnalyseModel(BaseModel):
    path: str
    filename : str
    
@app.post('/api/files/analyze')
def analyze_one(model: AnalyseModel):
    logger.info(f"Analyse du fichier audio avec ffprobe: {model.path}")
    lang = ffprobe_get_audio_language(model.path)
    analyzed_at = datetime.utcnow().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute(
            'INSERT INTO files (path, filename, language, analyzed_at) VALUES (?,?,?,?)',
            (model.path, model.filename, lang, analyzed_at)
        )
    conn.commit()
    conn.close()
    logger.info(f"Analyse du fichier audio effectué: {lang}")
    return {'status': 'ok', 'language': lang}

@app.post('/api/files/{file_id}/reanalyze')
def reanalyze(file_id: int):
    logger.info(f"Demande de re-Analyse du fichier: {file_id}")
        
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT path FROM files WHERE id=?', (file_id,))
    r = c.fetchone()
    if not r:
        conn.close()
        logger.error(f"Fichier non trouvé pour reanalyse: id={file_id}")
        raise HTTPException(status_code=404, detail='File not found')
    path = r['path']
    logger.info(f"Re-Analyse du fichier audio avec ffprobe: {path}")
    lang = ffprobe_get_audio_language(path)
    analyzed_at = datetime.utcnow().isoformat()
    logger.debug(f"Langue du fichier audio: {lang}")
    c.execute('UPDATE files SET language=?, analyzed_at=? WHERE id=?',
              (lang, analyzed_at, file_id))
    conn.commit()
    conn.close()
    logger.info(f"Re-Analyse du fichier audio effectué")
    return {'status': 'ok', 'language': lang}

# -------------------------
# Modèle Pydantic
# -------------------------
class SetLangModel(BaseModel):
    language: str
    
@app.post('/api/files/{file_id}/set_language')
def set_language(file_id: int, model: SetLangModel):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT path FROM files WHERE id=?', (file_id,))
    r = c.fetchone()
    if not r:
        conn.close()
        logger.error(f"Fichier non trouvé pour set_language: id={file_id}")
        raise HTTPException(status_code=404, detail='File not found')
    src = r['path']

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=Path(src).suffix)
    os.close(tmp_fd)
    try:
        logger.info(f"Changer la langue audio du fichier avec ffmpeg: {src} -> {model.language}")
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', src,
            '-map', '0', '-c', 'copy',
            f'-metadata:s:a:0', f'language={model.language}', tmp_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"Process de changement de langue en erreur: cmd={cmd}: {res.stderr}")
            raise HTTPException(status_code=500, detail=f'ffmpeg error: {res.stderr[:500]}')
        shutil.move(tmp_path, src)
        analyzed_at = datetime.utcnow().isoformat()
        c.execute(
            'UPDATE files SET language=?, analyzed_at=? WHERE id=?',
            (model.language, analyzed_at, file_id)
        )
        conn.commit()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        conn.close()
    return {'status': 'ok', 'language': model.language}
