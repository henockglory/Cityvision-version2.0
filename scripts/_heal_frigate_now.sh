#!/usr/bin/env bash
set -uo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== repair demo streams ==="
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/demo/repair-streams" \
  -H "X-Internal-Key: $KEY" || true
echo

echo "=== frigate rebuild ==="
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: $KEY"
echo

echo "=== frigate config cameras ==="
grep -E '^  cv_' infra/frigate-config/config.yml | head -10 || true

echo "=== restart frigate ==="
docker restart citevision-v2-frigate
for i in $(seq 1 30); do
  curl -sf http://127.0.0.1:5000/api/version >/dev/null 2>&1 && break
  sleep 2
done
curl -sf http://127.0.0.1:5000/api/version && echo " frigate up"

echo "=== wait for frigate events (optional) ==="
if [[ "${SKIP_FRIGATE_EVENTS_WAIT:-0}" == "1" ]]; then
  echo "[INFO] skip Frigate events wait (launch mode) — detection is not a start gate"
  exit 0
fi
for i in $(seq 1 18); do
  n=$(curl -sf "http://127.0.0.1:5000/api/events?limit=5" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)" 2>/dev/null || echo 0)
  echo "events=$n"
  if [ "$n" -gt 0 ] 2>/dev/null; then
    echo "Frigate events OK"
    exit 0
  fi
  sleep 5
done
echo "WARN: no frigate events yet"
exit 0
