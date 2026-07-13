#!/usr/bin/env bash
# Measure disk growth during demo loop — gate Phase 4.
set -euo pipefail
DURATION_MIN="${1:-30}"
MAX_MB_IDLE="${DISK_BUDGET_MB_IDLE:-500}"
MAX_MB_ACTIVE="${DISK_BUDGET_MB_ACTIVE:-5120}"
FRIGATE_REC="${FRIGATE_RECORDINGS_PATH:-/var/lib/docker/volumes}"

before=$(df -B1 / 2>/dev/null | tail -1 | awk '{print $3}' || echo 0)
echo "Disk used before: $before bytes — waiting ${DURATION_MIN}m..."
sleep "$((DURATION_MIN * 60))"
after=$(df -B1 / 2>/dev/null | tail -1 | awk '{print $3}' || echo 0)
delta=$((after - before))
delta_mb=$((delta / 1024 / 1024))
echo "Delta: ${delta_mb} MB (${DURATION_MIN} min)"
limit=$MAX_MB_IDLE
if [ "${ACTIVE_DEMO:-0}" = "1" ]; then
  limit=$MAX_MB_ACTIVE
fi
if [ "$delta_mb" -gt "$limit" ]; then
  echo "FAIL: budget ${limit} MB exceeded (${delta_mb} MB)"
  exit 1
fi
echo "PASS: within budget ${limit} MB"
exit 0
