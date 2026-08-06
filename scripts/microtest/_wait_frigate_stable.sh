#!/usr/bin/env bash
set -euo pipefail
FRIGATE="${FRIGATE_URL:-http://127.0.0.1:5000}"
CAM="${FEU_FRIGATE_CAM:-cv_8ed20433-57d5-4999-a6ab-0bea028b23a3}"
echo "=== wait Frigate stable ==="
deadline=$(( $(date +%s) + 120 ))
until curl -sf -m 8 "$FRIGATE/api/version" >/dev/null; do
  [ "$(date +%s)" -ge "$deadline" ] && { echo "[FAIL] Frigate version"; exit 2; }
  sleep 3
done
echo "[OK] Frigate version"
until [ "$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$FRIGATE/api/events?camera=$CAM&limit=5")" = "200" ]; do
  [ "$(date +%s)" -ge "$deadline" ] && { echo "[FAIL] Frigate events HTTP"; exit 2; }
  echo "  waiting events 200..."
  sleep 3
done
echo "[OK] Frigate events HTTP 200"
for i in 1 2 3; do
  code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$FRIGATE/api/events?camera=$CAM&limit=5")
  echo "  probe $i code=$code"
  [ "$code" = "200" ] || exit 2
  sleep 2
done
echo "[GO] Frigate stable"
