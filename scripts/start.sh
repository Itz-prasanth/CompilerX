#!/bin/sh
# Backend: FastAPI if installed, else the dependency-free stdlib server (same API).
cd "$(dirname "$0")/.."
if python3 -c "import fastapi, uvicorn, pydantic" 2>/dev/null; then
  exec python3 -m uvicorn backend.fastapi_app:app --host "${COMPILERX_HOST:-127.0.0.1}" --port "${COMPILERX_PORT:-8000}"
else
  echo "fastapi/uvicorn not installed - starting the stdlib server (same endpoints)" >&2
  exec python3 -m backend.simple_server
fi
