#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
  KEY="${INTERNAL_API_KEY:-$KEY}"
fi

echo "=== repair streams ==="
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams
echo
echo "=== frigate rebuild ==="
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild
echo
echo "=== restart frigate ==="
docker restart citevision-v2-frigate
for i in $(seq 1 45); do
  if curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null; then
    echo "Frigate API up after ${i}x2s"
    break
  fi
  sleep 2
done
sleep 20
echo "=== config cameras snippet ==="
docker exec citevision-v2-frigate sh -c 'python3 - <<"PY"
import yaml
try:
  c=yaml.safe_load(open("/config/config.yml"))
except Exception as e:
  print("load err", e); raise SystemExit(1)
cams=(c or {}).get("cameras") or {}
print("n_cameras", len(cams))
print("names", list(cams.keys())[:20])
PY' 2>/dev/null || docker exec citevision-v2-frigate ls -la /config/ | head -20

echo "=== stats after rebuild ==="
bash scripts/_diag_frigate_e2e.sh
