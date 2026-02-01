FROM python:3.11-slim

# Install ffmpeg and build deps
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY static ./static

# 👇 Version de l'app
ARG APP_VERSION
ENV APP_VERSION=${APP_VERSION}

# Remplacement dans le HTML
RUN sed -i "s/__APP_VERSION__/${APP_VERSION}/g" static/index.html

ENV VIDEOS_DIR=/videos
ENV DB_PATH=/app/app.db

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]