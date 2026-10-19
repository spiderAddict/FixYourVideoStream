FROM python:3.11-slim

# Install ffmpeg and build deps
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY static ./static

# Version de l'app, servie par /api/version et affichée dans l'en-tête
ARG APP_VERSION
ENV APP_VERSION=${APP_VERSION}

ENV VIDEOS_DIR=/videos
ENV DB_PATH=/data/app.db

EXPOSE 8000

# Utilisateur de l'application ; UID/GID ajustés au démarrage via PUID/PGID
ENV PUID=1000
ENV PGID=1000

RUN groupadd -g ${PGID} appuser && \
    useradd -u ${PUID} -g appuser -m appuser && \
    mkdir -p /data && \
    chown appuser:appuser /data

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# L'entrypoint démarre en root pour appliquer PUID/PGID, puis abandonne ces droits
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
