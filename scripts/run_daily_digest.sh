#!/usr/bin/env bash
# Cron wrapper: runs the agent for all five categories and emails the digest.
# The --only-at-hour guard makes a UTC crontab fire at 8 AM Eastern year-round
# (cron does not know about daylight saving, so we schedule both candidate UTC
# hours and let this script decide).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."
cd "$ROOT/backend"
mkdir -p "$ROOT/logs"
if [ -f .venv/Scripts/activate ]; then source .venv/Scripts/activate; else source .venv/bin/activate; fi
set -a; [ -f .env ] && source .env; set +a
exec python daily_digest.py --only-at-hour "${DIGEST_HOUR:-8}" --tz "${DIGEST_TZ:-America/New_York}" "$@" \
  >>"$ROOT/logs/daily_digest.log" 2>&1
