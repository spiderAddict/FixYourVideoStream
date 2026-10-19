#!/bin/sh
# Démarrage du conteneur : aligne appuser sur PUID/PGID (convention des images
# linuxserver/*arr/Jellyfin) pour pouvoir écrire dans /videos sans reconstruire
# l'image, puis lance l'application sans les droits root.
set -e

if [ "$(id -u)" != "0" ]; then
    # Conteneur lancé avec --user : l'utilisateur imposé est conservé tel quel
    exec "$@"
fi

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# -o : l'UID/GID peut déjà exister dans l'image (ex. 100 = users)
if [ "$(id -g appuser)" != "$PGID" ]; then
    groupmod -o -g "$PGID" appuser
fi
if [ "$(id -u appuser)" != "$PUID" ]; then
    usermod -o -u "$PUID" appuser
fi

# /data contient la base SQLite. /videos n'est pas modifié : ses droits
# appartiennent à l'hôte, c'est PUID/PGID qui doit y correspondre.
chown -R appuser:appuser /data

echo "Démarrage avec PUID=$PUID PGID=$PGID"
exec setpriv --reuid=appuser --regid=appuser --init-groups "$@"
