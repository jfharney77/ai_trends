#!/usr/bin/env bash
# Kill the uvicorn backend (port 8000) and the Vite dev server (port 5173).
set -uo pipefail
for port in "${PORT:-8000}" 5173; do
  pids=$(lsof -t -i ":$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "Stopping processes on port $port: $pids"
    kill $pids 2>/dev/null || true
  else
    echo "Nothing listening on port $port"
  fi
done
