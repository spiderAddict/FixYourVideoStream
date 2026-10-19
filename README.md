
## Installer les dépendances Python
```
python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

uvicorn backend.main:app --reload
```

## Générer des fichiers de test
```python generate_test_files.py```

## Builder l'image
```docker build -t fixyourvideostream . ```

## Lancer le conteneur et monter le dossier vidéo
```docker run -it --rm -p 8000:8000 -v ./test_videos:/videos -v fixyourvideostream_data:/data fixyourvideostream```

## Scan du répertoire
- « Scan pour nouveaux » ajoute les nouveaux fichiers et retire de la base ceux qui n'existent plus sur le disque.
- Si le répertoire vidéo est absent ou entièrement vide (volume non monté), aucun fichier n'est retiré.

## Analyses en masse
- « Analyser tout » et « Analyser nouveaux » tournent en tâche de fond : la progression est affichée
  et le suivi reprend si la page est rechargée. Une seule analyse en masse à la fois.
- L'avancement est gardé en mémoire : lancer uvicorn avec un seul process (pas de `--workers`).

## Changement de langue audio
- La langue est modifiée sur la piste audio choisie dans le panneau de détail (pas forcément la première).
- Les fichiers `.avi` ne peuvent pas stocker la langue des pistes : l'action y est refusée.
- `BACKUP_ON_SET_LANGUAGE=true` conserve l'original en `<fichier>.bak` avant la première modification
  (désactivé par défaut car cela double l'espace disque du fichier modifié).

## Prompt ChatGpt
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
