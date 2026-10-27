# BOZZA NON TESTATA (qui non c'è Docker). Contiene solo orchestrator + interfaccia web.
# Whisper-MLX, Ollama/Splash e il TTS di macOS NON girano in un container su Mac (niente accesso a Metal):
# restano sull'host e il container li raggiunge via host.docker.internal. Vedi docs/TECHNICAL.md §13.
# Build dalla radice del progetto:  docker build -f deploy/Dockerfile -t tutor-local .
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/vite.config.js frontend/index.html ./
COPY frontend/src ./src
RUN npm install && npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements-core.txt backend/requirements-core.txt
RUN pip install --no-cache-dir -r backend/requirements-core.txt
COPY backend backend
COPY --from=ui /ui/dist frontend/dist
ENV STT_BACKEND=openai DB_PATH=/data/tutor.db
VOLUME /data
EXPOSE 8010
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
