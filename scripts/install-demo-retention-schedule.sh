#!/usr/bin/env bash
# Install 30-minute demo retention: WSL cron purge + Windows scheduled compact (admin).
set -euo pipefail
ROOT="${CITEVISION_ROOT:-$HOME/citevision-v2}"
WIN_ROOT="/mnt/c/Users/gheno/citevision"
RETAIN_MIN="${FRIGATE_DEMO_RETENTION_MIN:-30}"
CRON_LINE="*/30 * * * * FRIGATE_DEMO_RETENTION_MIN=${RETAIN_MIN} ${ROOT}/scripts/demo-retention-purge.sh >> ${ROOT}/logs/demo-retention-purge.log 2>&1"

chmod +x "${ROOT}/scripts/demo-retention-purge.sh"

# WSL crontab
( crontab -l 2>/dev/null | grep -v 'demo-retention-purge.sh' || true
  echo "$CRON_LINE"
) | crontab -

echo "[OK] WSL cron every 30m:"
echo "  $CRON_LINE"

# Windows scheduled task (requires admin PowerShell once)
PS1="${WIN_ROOT}/scripts/install-demo-retention-schedule.ps1"
if [[ -f "$PS1" ]]; then
  /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -ExecutionPolicy Bypass -File "C:\\Users\\gheno\\citevision\\scripts\\install-demo-retention-schedule.ps1" 2>&1 || \
    echo "[WARN] Windows task install failed — run PowerShell as Admin: install-demo-retention-schedule.ps1"
else
  echo "[WARN] Missing $PS1"
fi

echo "[OK] Retention ${RETAIN_MIN} minutes — purge cron installed"
