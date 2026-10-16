import os
import sqlite3
import subprocess
import json
import tempfile
import logging
import stat
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path

VIDEOS_DIR = os.environ.get("VIDEOS_DIR", "/videos")
DB_PATH = os.environ.get("DB_PATH", "app.db")
VERSION_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "VERSION")

VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v'}
# Conteneurs dans lesquels ffmpeg ne sait pas écrire la langue d'une piste audio
LANGUAGE_UNSUPPORTED_EXTS = {'.avi'}
# Conserver l'original en <fichier>.bak lors d'un changement de langue (double l'espace disque utilisé)
BACKUP_ON_SET_LANGUAGE = os.environ.get("BACKUP_ON_SET_LANGUAGE", "false").lower() in ("1", "true", "yes")

# --- Configuration du logger ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount('/static', StaticFiles(directory="static", html=True), name="static")

def get_version():
    """Retourne la version de l'application"""
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, 'r') as f:
                return f.read().strip()
    except:
        pass
    return "unknown"

@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/api/version")
def get_app_version():
    """API endpoint pour obtenir la version de l'application"""
    return {'version': get_version()}

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
    # Migration : message d'erreur de la dernière analyse (NULL si elle a réussi)
    columns = {row['name'] for row in c.execute('PRAGMA table_info(files)')}
    if 'analysis_error' not in columns:
        logger.info("Migration de la base: ajout de la colonne files.analysis_error")
        c.execute('ALTER TABLE files ADD COLUMN analysis_error TEXT')
    conn.commit()
    conn.close()

init_db()

# -------------------------
# Analyse avec ffprobe
# -------------------------
def ffprobe_streams(path):
    """Retourne la liste brute des flux du fichier (sortie JSON de ffprobe)"""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', str(path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(res.stdout).get('streams', [])

def audio_tracks(streams):
    """Extrait les pistes audio ; 'track' est l'index relatif utilisé par ffmpeg (a:N)"""
    tracks = []
    for s in streams:
        if s.get('codec_type') != 'audio':
            continue
        tags = s.get('tags') or {}
        tracks.append({
            'track': len(tracks),
            'stream_index': s.get('index'),
            'codec': s.get('codec_name'),
            'language': tags.get('language') or tags.get('LANGUAGE'),
            'title': tags.get('title') or tags.get('TITLE'),
            'default': bool((s.get('disposition') or {}).get('default')),
        })
    return tracks

def primary_language(tracks):
    """Langue de la piste lue par défaut par les lecteurs : piste 'default', sinon la première"""
    if not tracks:
        return None
    primary = next((t for t in tracks if t['default']), tracks[0])
    return primary['language']

def ffprobe_get_audio_language(path):
    """Retourne (langue, erreur). Une erreur signifie que le fichier n'a pas pu être lu :
    à ne pas confondre avec (None, None), fichier lu mais sans langue renseignée."""
    logger.info(f"Analyse du fichier audio avec ffprobe: {path}")
    if not os.path.isfile(path):
        logger.error(f"Analyse impossible, fichier introuvable: {path}")
        return None, "Fichier introuvable"
    try:
        return primary_language(audio_tracks(ffprobe_streams(path))), None
    except FileNotFoundError as exc:
        # ffprobe absent : problème d'installation, pas du fichier, on n'enregistre rien
        logger.exception("ffprobe est introuvable")
        raise HTTPException(status_code=500, detail='ffprobe not found') from exc
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        logger.exception(f"Analyse ffprobe en échec: {path}")
        return None, "Fichier illisible par ffprobe"

def save_analysis(conn, file_id, lang, error):
    """Enregistre le résultat d'une analyse (réussie ou en erreur)"""
    conn.execute(
        'UPDATE files SET language=?, analyzed_at=?, analysis_error=? WHERE id=?',
        (lang, datetime.utcnow().isoformat(), error, file_id)
    )

def file_status(row):
    """Statut d'analyse : not_analyzed, analyzed ou error"""
    if not row['analyzed_at']:
        return 'not_analyzed'
    return 'error' if row['analysis_error'] else 'analyzed'

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
    c.execute('SELECT id, path, filename, language, analyzed_at, analysis_error FROM files')
    rows = c.fetchall()
    conn.close()

    result = []
    for r in rows:
        status = file_status(r)
        item = {
            'id': r['id'],
            'filename': r['filename'],
            'path': r['path'],
            'language': r['language'],
            'analyzed_at': r['analyzed_at'],
            'analysis_error': r['analysis_error'],
            'status': status,
            'analyzed': status == 'analyzed'
        }
        if name is None or name.lower() in item['filename'].lower():
            result.append(item)
    return sorted(result, key=lambda x: x['filename'])

@app.get('/api/files/{file_id}')
def get_file(file_id: int):

    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT id, filename, path, language, analyzed_at, analysis_error FROM files WHERE id=?', (file_id,))
    r = c.fetchone()
    conn.close()
    if not r:
        logger.error(f"Fichier non trouvé pour reanalyse: id={file_id}")
        raise HTTPException(status_code=404, detail='File not found')
    return {**dict(r), 'status': file_status(r)}

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

    errors = 0
    try:
        for file in files:
            lang, error = ffprobe_get_audio_language(file['path'])
            errors += bool(error)
            # UPDATE par id (et non INSERT OR REPLACE) pour conserver l'id du fichier :
            # un REPLACE supprime puis recrée la ligne, ce qui change son id
            save_analysis(conn, file['id'], lang, error)
        conn.commit()
    finally:
        conn.close()
    return {'status': 'ok', 'count': count, 'errors': errors}

@app.post('/api/analyze_new')
def analyze_new():
    logger.info("Analyser tous les fichiers pas encore analysé")

    conn = get_conn()
    c = conn.cursor()
    # Fichiers en base jamais analysés, ou dont la dernière analyse a échoué
    c.execute('SELECT id, path, filename FROM files WHERE analyzed_at IS NULL OR analysis_error IS NOT NULL')
    files = c.fetchall()
    count = len(files)

    errors = 0
    try:
        for file in files:
            lang, error = ffprobe_get_audio_language(file['path'])
            errors += bool(error)
            save_analysis(conn, file['id'], lang, error)
        conn.commit()
    finally:
        conn.close()
    return {'status': 'ok', 'count': count, 'errors': errors}
    
@app.post('/api/files/{file_id}/analyze')
def analyze_one(file_id: int):
    logger.info(f"Demande d'analyse du fichier audio ({file_id})")

    # Récupère le chemin du fichier depuis la base
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT path FROM files WHERE id=?', (file_id,))
    r = c.fetchone()
    if not r:
        conn.close()
        logger.error(f"Fichier non trouvé pour analyse: id={file_id}")
        raise HTTPException(status_code=404, detail='File not found')
    path = r['path']

    # Analyse le fichier avec ffprobe
    try:
        lang, error = ffprobe_get_audio_language(path)
        logger.debug(f"Langue du fichier audio: {lang}")
        save_analysis(conn, file_id, lang, error)
        conn.commit()
    finally:
        conn.close()

    logger.info(f"Analyse du fichier audio effectué: {lang} (erreur: {error})")
    return {'status': 'error' if error else 'ok', 'language': lang, 'error': error}

@app.post('/api/files/{file_id}/reanalyze')
def reanalyze(file_id: int):
    logger.info(f"Demande de re-analyse du fichier audio ({file_id})")
        
    # Récupère le chemin du fichier depuis la base
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT path FROM files WHERE id=?', (file_id,))
    r = c.fetchone()
    if not r:
        conn.close()
        logger.error(f"Fichier non trouvé pour reanalyse: id={file_id}")
        raise HTTPException(status_code=404, detail='File not found')
    path = r['path']

    # Analyse le fichier avec ffprobe
    logger.info(f"Re-Analyse du fichier audio avec ffprobe: {path}")
    try:
        lang, error = ffprobe_get_audio_language(path)
        logger.debug(f"Langue du fichier audio: {lang}")
        save_analysis(conn, file_id, lang, error)
        conn.commit()
    finally:
        conn.close()

    logger.info(f"Re-Analyse du fichier audio effectué: {lang} (erreur: {error})")
    return {'status': 'error' if error else 'ok', 'language': lang, 'error': error}

@app.get('/api/files/{file_id}/tracks')
def get_tracks(file_id: int):
    """Liste les pistes audio du fichier, lues directement sur le disque"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT path FROM files WHERE id=?', (file_id,))
    r = c.fetchone()
    conn.close()
    if not r:
        logger.error(f"Fichier non trouvé pour la liste des pistes: id={file_id}")
        raise HTTPException(status_code=404, detail='File not found')
    path = r['path']
    try:
        tracks = audio_tracks(ffprobe_streams(path))
    except Exception as exc:
        logger.exception(f"Lecture des pistes impossible pour {path}")
        raise HTTPException(status_code=500, detail='Unable to read audio tracks') from exc
    return {
        'tracks': tracks,
        'language_editable': Path(path).suffix.lower() not in LANGUAGE_UNSUPPORTED_EXTS,
    }

# -------------------------
# Modèle Pydantic
# -------------------------
class SetLangModel(BaseModel):
    language: str
    track: int = 0  # index relatif de la piste audio (a:N)

@app.post('/api/files/{file_id}/set_language')
def set_language(file_id: int, model: SetLangModel):
    logger.info(f"Demande de changement de langue du fichier audio ({file_id}, piste a:{model.track})")

    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT path FROM files WHERE id=?', (file_id,))
    r = c.fetchone()
    if not r:
        conn.close()
        logger.error(f"Fichier non trouvé pour set_language: id={file_id}")
        raise HTTPException(status_code=404, detail='File not found')
    src = r['path']

    # Le muxer AVI de ffmpeg n'écrit pas la langue des pistes : l'opération
    # « réussirait » sans rien changer au fichier
    if Path(src).suffix.lower() in LANGUAGE_UNSUPPORTED_EXTS:
        conn.close()
        logger.warning(f"Changement de langue refusé, conteneur non supporté: {src}")
        raise HTTPException(status_code=400, detail=f'Container {Path(src).suffix} cannot store audio language')

    tmp_path = None
    try:
        source_streams = ffprobe_streams(src)
        source_tracks = audio_tracks(source_streams)
        if not 0 <= model.track < len(source_tracks):
            logger.error(f"Piste audio a:{model.track} inexistante dans {src} ({len(source_tracks)} piste(s))")
            raise HTTPException(status_code=400, detail=f'Audio track {model.track} does not exist')

        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=Path(src).parent,
            suffix=Path(src).suffix
        )
        os.close(tmp_fd)
        source_mode = stat.S_IMODE(os.stat(src).st_mode)
        source_size = os.path.getsize(src)
        logger.info(
            f"Changer la langue audio: {src} ({source_size} octets) "
            f"piste a:{model.track} -> {model.language}; fichier temporaire: {tmp_path}"
        )
        cmd = [
            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', src,
            '-map', '0', '-c', 'copy',
            f'-metadata:s:a:{model.track}', f'language={model.language}', tmp_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"Process de changement de langue en erreur: cmd={cmd}: {res.stderr}")
            raise HTTPException(status_code=500, detail=f'ffmpeg error: {res.stderr[:500]}')

        output_size = os.path.getsize(tmp_path)
        if output_size == 0:
            logger.error(f"Sortie ffmpeg vide pour {src}: {tmp_path}")
            raise HTTPException(status_code=500, detail='ffmpeg produced an empty file')

        # Validation de la sortie avant de toucher à l'original : même nombre de flux
        # (aucun flux perdu par le remux) et langue effectivement écrite sur la piste
        try:
            output_streams = ffprobe_streams(tmp_path)
        except subprocess.CalledProcessError as exc:
            logger.error(f"Validation ffprobe échouée pour {tmp_path}: {exc.stderr}")
            raise HTTPException(status_code=500, detail='ffprobe validation failed')
        if len(output_streams) != len(source_streams):
            logger.error(
                f"Flux perdus par ffmpeg pour {src}: {len(source_streams)} -> {len(output_streams)}"
            )
            raise HTTPException(status_code=500, detail='ffmpeg output is missing streams')
        output_tracks = audio_tracks(output_streams)
        if output_tracks[model.track]['language'] != model.language:
            logger.error(f"Langue non écrite dans la sortie ffmpeg pour {src}: {output_tracks[model.track]}")
            raise HTTPException(status_code=500, detail='Language was not written to the output file')

        os.chmod(tmp_path, source_mode)
        backup_path = safe_move(tmp_path, src)
        logger.info(f"Remplacement réussi: {src} ({source_size} -> {output_size} octets)")
        if backup_path:
            logger.info(f"Original conservé: {backup_path}")

        # La langue affichée est celle de la piste principale, qui n'est pas
        # forcément celle qui vient d'être modifiée
        lang = primary_language(output_tracks)
        save_analysis(conn, file_id, lang, None)
        conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Échec du changement de langue pour {src}")
        raise HTTPException(status_code=500, detail='Unable to update file language') from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        conn.close()
    return {'status': 'ok', 'language': lang, 'tracks': output_tracks}

# -------------------------
# Safe move, meme pour nas
# -------------------------
def safe_move(src, dst):
    """Remplace dst par src. Si BACKUP_ON_SET_LANGUAGE est actif, l'original est
    conservé en <dst>.bak (ignoré par le scan) ; retourne alors son chemin."""
    if not BACKUP_ON_SET_LANGUAGE:
        os.replace(src, dst)
        return None
    backup_path = f"{dst}.bak"
    if os.path.exists(backup_path):
        # Un .bak existe déjà : c'est l'original d'avant toute modification, on le garde
        os.replace(src, dst)
        return backup_path
    os.replace(dst, backup_path)
    try:
        os.replace(src, dst)
    except Exception:
        # Remet l'original en place si le remplacement échoue
        os.replace(backup_path, dst)
        raise
    return backup_path
