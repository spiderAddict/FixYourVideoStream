# FixYourVideoStream

Application web qui analyse un dossier de vidéos, affiche la langue déclarée sur les pistes audio de chaque
fichier et permet de corriger cette langue, par exemple pour qu'un lecteur (Plex, Jellyfin…) propose
automatiquement la bonne piste.

- Liste des vidéos du dossier avec leur statut d'analyse et leur langue, filtrable par nom, statut et langue.
- Analyse de tout le dossier, ou seulement des nouveaux fichiers, en tâche de fond avec progression.
- Panneau de détail : pistes audio du fichier (langue, codec, piste par défaut) et passage d'une piste en français.
- Trois thèmes : Plex, Sonarr, Jellyfin.

Formats pris en charge : `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.m4v` (sous-dossiers compris).

## Démarrer avec Docker

```bash
docker build -t fixyourvideostream .
docker run -d -p 8000:8000 \
  -e PUID=1000 -e PGID=1000 \
  -v /chemin/vers/videos:/videos \
  -v fixyourvideostream_data:/data \
  fixyourvideostream
```

Puis ouvrir http://localhost:8000. Les images publiées par la CI (à chaque tag `vX.Y.Z`) sont sur
`ghcr.io/spideraddict/fixyourvideostream:<version>`.

Avec Docker Compose (NAS) :

```yaml
services:
  fixyourvideostream:
    image: ghcr.io/spideraddict/fixyourvideostream:<version>
    ports:
      - "8000:8000"
    environment:
      - PUID=1000   # propriétaire des fichiers vidéo sur le NAS
      - PGID=1000
    volumes:
      - /volume1/videos:/videos
      - fixyourvideostream_data:/data
    restart: unless-stopped

volumes:
  fixyourvideostream_data:
```

### Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `PUID` / `PGID` | `1000` | Utilisateur et groupe qui exécutent l'application. Ils doivent avoir le droit d'écrire dans le dossier vidéo pour changer une langue (sur un NAS : l'UID/GID propriétaire des fichiers). |
| `BACKUP_ON_SET_LANGUAGE` | `false` | `true` conserve l'original en `<fichier>.bak` avant la première modification. Désactivé par défaut car cela double l'espace disque du fichier modifié. |
| `VIDEOS_DIR` | `/videos` | Dossier analysé. |
| `DB_PATH` | `/data/app.db` | Base SQLite (analyses et thème). |
| `APP_VERSION` | `unknown` | Version affichée dans l'en-tête, fixée au build (`--build-arg APP_VERSION=…`). |

Les variables sont lues au démarrage : après une modification, recréer le conteneur.

### Volumes et permissions

- Le conteneur démarre en root, aligne son utilisateur sur `PUID`/`PGID`, donne `/data` à cet utilisateur
  puis abandonne les droits root. **Les droits de `/videos` ne sont jamais modifiés.**
- `--user` reste possible : `PUID`/`PGID` sont alors ignorés.
- Un `HEALTHCHECK` interroge `/api/version`.

## Fonctionnement

- **Scan pour nouveaux** : ajoute les nouveaux fichiers et retire de la base ceux qui n'existent plus sur le disque.
  Si le dossier vidéo est absent ou entièrement vide (volume non monté), aucun fichier n'est retiré.
- **Analyser nouveaux / Analyser tout** : lit les pistes audio avec ffprobe, en tâche de fond. La progression
  s'affiche et le suivi reprend si la page est rechargée. « Analyser nouveaux » reprend aussi les fichiers en erreur.
  Une seule analyse en masse à la fois.
- **Langue affichée** : celle de la piste lue par défaut par les lecteurs (piste « default », sinon la première).
- **Statuts** : ✓ analysé, ⏳ pas encore analysé, ✗ erreur (fichier introuvable ou illisible par ffprobe).
- **Forcer FR** : écrit `fra` sur la piste choisie, en remuxant le fichier sans réencodage (`ffmpeg -c copy`).
  L'original n'est remplacé que si le nouveau fichier contient les mêmes flux et la bonne langue.
  Refusé pour les `.avi`, dont le format ne permet pas de stocker la langue des pistes.

## Sécurité

- L'application n'a **aucune authentification**, alors qu'elle peut réécrire les fichiers vidéo.
  Elle est prévue pour un réseau local de confiance : ne pas exposer le port 8000 sur internet
  (ou alors derrière un reverse proxy avec authentification).
- La langue envoyée à l'API doit être un code ISO 639-2 (`fra`, `fre`, `eng`, `und`…), sinon la requête est refusée (422).

## Limites connues

- Un seul process uvicorn : l'avancement des analyses en masse est gardé en mémoire (pas de `--workers`).
- Un fichier renommé ou déplacé est vu comme un nouveau fichier : il faut le réanalyser.
- Le changement de langue réécrit tout le fichier : il faut de l'espace libre équivalent dans son dossier.

## Développement

Prérequis : Python 3.11+ et ffmpeg/ffprobe dans le `PATH`.

```bash
python -m venv venv
source venv/bin/activate          # Windows : venv\Scripts\activate
pip install -r requirements-dev.txt

python generate_test_files.py     # quelques vidéos dans test_videos/
VIDEOS_DIR=test_videos uvicorn backend.main:app --reload
```

Une configuration de débogage VS Code est fournie (`.vscode/launch.json`).

### Tests

```bash
ruff check .
pytest
```

Les tests génèrent leurs propres vidéos avec ffmpeg. La CI (workflow *Tests*) lance `ruff` et `pytest` sur
chaque push et chaque pull request ; le workflow *Build And Push Docker Image* publie l'image à chaque tag `v*`.

## Origine du projet

<details>
<summary>Prompt ChatGPT d'origine</summary>

```
Je voudrais une application web qui me permette d'analyser le contenu d'un répertoire, et pour chaque fichier vidéo trouvé, elle affichera la langue inscrite dans les metadonnées des pistes audio. 
L'application permettra d'analyser tout le répertoire, puis d'afficher la liste des fichiers dans une liste avec leur langue audio. 
Cette analyse sera sauvegardée ce qui permettra de réanalyser que les nouveaux fichiers au lieu de la totalité. 
J'ai donc 2 actions possibles sur la page de liste : "Analyser tout" et "Analyser les nouveaux fichiers".
La liste affichera le nom du fichier, sa langue et une icone représentant le statut d'analyse, c'est à dire "déjà analysé" ou "pas encore analysé".
La liste affichée est celle des fichiers du répertoire et non la liste sauvegardée en base.
En cliquant sur un élément de la liste, je veux voir un panneau à droite du navigateur qui se déplie affichant le path du fichier, sont statut d'analyse, sa langue audio si elle est connue, et des actions : réanalyser, changer la langue audio. Ce panneau détail reste fixé.
Le bouton réanalyser, réanalyser le fichier. 
Le bouton changer la langue audio positionnera la langue française sur la piste audio du fichier vidéo. 
Le code sera commenté.

Un logger sera implémenté pour suivre les actions principales et obligatoirement pour gérer les erreurs.

Je voudrais un bouton en haut a droite qui permette de changer le style de l'application entre 3 styles, Plex, Sonarr, Jellyfin.
Ces styles seront sauvegardés en base mais chargés en cache dans l'application pour ne pas requêter la base à chaque page affichée.

L'appliation sera debuggable dans VS Code. Tu vas donc me fournir un fichier de configuration.

Le style frontend de l'application utilisera Bulma.

L'application sera déployé dans un conteneur , il me faut donc un Dockerfile. 
Le répertoire des fichiers à analyser sera monté par un volume.
```

</details>
