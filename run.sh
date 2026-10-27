#!/usr/bin/env bash
# Avvia tutor-local in un solo processo: il backend FastAPI serve anche il frontend già compilato.
# Uso: ./run.sh        (PORT=8010 di default)
set -euo pipefail
cd "$(dirname "$0")"

if   [ -d backend/.venv ]; then VENV=backend/.venv
elif [ -d .venv ];         then VENV=.venv
else
  echo "Manca il virtualenv. Crealo così:"
  echo "  cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# Ricompila il frontend se manca la build o se un sorgente è più recente della build.
needs_build=0
if [ ! -f frontend/dist/index.html ]; then
  needs_build=1
elif [ -n "$(find frontend/src frontend/index.html frontend/vite.config.js frontend/package.json \
                   -newer frontend/dist/index.html 2>/dev/null | head -n 1)" ]; then
  needs_build=1
fi
if [ "$needs_build" = 1 ]; then
  echo "Compilo il frontend…"
  (cd frontend && npm install && npm run build)
fi

echo "Tutor locale su http://127.0.0.1:${PORT:-8010}"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
cd backend
exec uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8010}"
