#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."
cd "$ROOT/backend"

if [ ! -d .venv ]; then
  echo "Creating virtualenv..."
  if command -v uv >/dev/null 2>&1; then uv venv .venv -q; else python3 -m venv .venv; fi
fi
if [ -f .venv/Scripts/activate ]; then source .venv/Scripts/activate; else source .venv/bin/activate; fi
if command -v uv >/dev/null 2>&1; then uv pip install -q -r requirements.txt; else pip install -q -r requirements.txt; fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created backend/.env from .env.example. Add your OPENROUTER_API_KEY and SMTP settings."
fi

exec uvicorn main:app --reload --host 0.0.0.0 --port "${PORT:-8000}"
