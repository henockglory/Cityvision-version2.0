#!/usr/bin/env bash
# Rebuild Frigate config for demo cameras + restart (WSL runtime).
set -euo pipefail
ROOT="${HOME}/citevision-v2"
API="${API:-http://127.0.0.1:8081}"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "==> Frigate rebuild demo"
curl -sf -X POST "${API}/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: ${KEY}" -H "Content-Type: application/json" \
  -d '{}' | head -c 400
echo
docker restart citevision-v2-frigate
echo "waiting for Frigate..."
for i in $(seq 1 30); do
  if curl -m 3 -sf http://127.0.0.1:5000/api/version >/dev/null 2>&1; then
    curl -s http://127.0.0.1:5000/api/version
    echo
    exit 0
  fi
  sleep 3
done
echo "[FAIL] Frigate not healthy after 90s" >&2
exit 1
