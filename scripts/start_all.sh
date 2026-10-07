#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."
mkdir -p "$ROOT/logs"

"$SCRIPT_DIR/start_backend.sh" >"$ROOT/logs/backend.log" 2>&1 &
BACKEND_PID=$!
echo "Backend started (pid $BACKEND_PID), logging to logs/backend.log"
trap 'echo; echo "Stopping backend..."; kill "$BACKEND_PID" 2>/dev/null || true' INT TERM EXIT

"$SCRIPT_DIR/start_frontend.sh"
