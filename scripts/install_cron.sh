#!/usr/bin/env bash
# Install (or refresh) the crontab entries for the 8 AM Eastern daily digest.
#
# Eastern time is UTC-4 (EDT) or UTC-5 (EST), so 8 AM Eastern is 12:00 or
# 13:00 UTC depending on the season. We schedule both, in UTC, and the wrapper
# script exits immediately unless it is actually 8 AM in America/New_York.
# This works regardless of the machine's own timezone setting.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER="$SCRIPT_DIR/run_daily_digest.sh"
MARKER="# ai_trends daily digest"

TZ_NAME="${DIGEST_TZ:-America/New_York}"
HOUR="${DIGEST_HOUR:-8}"
ENV_FILE="$SCRIPT_DIR/../backend/.env"
if [ -f "$ENV_FILE" ]; then
  TZ_NAME=$(grep -E '^DIGEST_TZ=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' || true); TZ_NAME="${TZ_NAME:-America/New_York}"
  HOUR=$(grep -E '^DIGEST_HOUR=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' || true); HOUR="${HOUR:-8}"
fi

# Compute the two UTC hours that can correspond to $HOUR local (standard and daylight time).
read -r H1 H2 < <(python3 - "$TZ_NAME" "$HOUR" <<'PY'
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
tz = ZoneInfo(sys.argv[1]); hour = int(sys.argv[2])
hours = set()
for month in (1, 7):
    local = datetime(2026, month, 15, hour, 0, tzinfo=tz)
    hours.add(local.astimezone(timezone.utc).hour)
hs = sorted(hours)
print(hs[0], hs[-1])
PY
)
if [ "$H1" = "$H2" ]; then HOURS="$H1"; else HOURS="$H1,$H2"; fi

# Convert the UTC hours to the machine's local timezone for the crontab, since
# cron schedules in local time.
read -r LOCAL_HOURS < <(python3 - "$HOURS" <<'PY'
import sys
from datetime import datetime, timezone
hours = [int(h) for h in sys.argv[1].split(",")]
local = sorted({datetime(2026, 1, 15, h, tzinfo=timezone.utc).astimezone().hour for h in hours} |
               {datetime(2026, 7, 15, h, tzinfo=timezone.utc).astimezone().hour for h in hours})
print(",".join(str(h) for h in local))
PY
)

LINE="0 $LOCAL_HOURS * * * $WRAPPER $MARKER"

( crontab -l 2>/dev/null | grep -vF "$MARKER" || true; echo "$LINE" ) | crontab -
echo "Installed crontab entry:"
echo "  $LINE"
echo
echo "The wrapper only sends when it is $HOUR:00 in $TZ_NAME; other firings exit quietly."
echo "Logs: $(cd "$SCRIPT_DIR/.." && pwd)/logs/daily_digest.log"
echo
if ! pgrep -x cron >/dev/null 2>&1 && ! pgrep -x crond >/dev/null 2>&1; then
  echo "WARNING: the cron daemon is not running. On WSL start it with:  sudo service cron start"
  echo "To start it automatically, add to /etc/wsl.conf:"
  echo "  [boot]"
  echo "  systemd=true"
  echo "then run 'wsl --shutdown' from Windows and 'sudo systemctl enable --now cron' in WSL."
fi
