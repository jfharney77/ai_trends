#!/usr/bin/env bash
set -euo pipefail
MARKER="# ai_trends daily digest"
( crontab -l 2>/dev/null | grep -vF "$MARKER" || true ) | crontab -
echo "Removed ai_trends crontab entry."
