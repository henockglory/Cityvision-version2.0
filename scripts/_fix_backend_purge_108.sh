#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
export PATH="/usr/local/go/bin:/home/gheno/go/bin:${PATH:-}"

# shellcheck disable=SC1091
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$PWD")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== stop old api ==="
if [[ -f logs/backend.pid ]]; then
  kill "$(cat logs/backend.pid)" 2>/dev/null || true
  sleep 2
fi
fuser -k 8081/tcp 2>/dev/null || true
sleep 1

echo "=== start api with env ==="
nohup ./backend/bin/citevision-api >> logs/backend.log 2>&1 &
echo $! > logs/backend.pid
echo "pid=$(cat logs/backend.pid)"

for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8081/health >/dev/null 2>&1; then
    echo "API up"
    break
  fi
  sleep 1
done
curl -sf http://127.0.0.1:8081/health | head -c 300 || echo "health fail"
echo

echo "=== frigate rebuild ==="
curl -sS -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: ${KEY}" -o /tmp/frigate_rebuild.json -w "http=%{http_code}\n"
python3 -m json.tool /tmp/frigate_rebuild.json 2>/dev/null || cat /tmp/frigate_rebuild.json
echo

echo "=== 108 in config.yml? ==="
if grep -n '192.168.1.108' infra/frigate-config/config.yml; then
  echo "STILL PRESENT — force purge"
else
  echo "GONE"
fi

echo "=== cameras in config ==="
grep -E '^  cv_' infra/frigate-config/config.yml || true

echo "=== recent skip logs ==="
grep -E 'frigate skip excluded|frigate config rebuilt' logs/backend.log | tail -10

echo "=== AI demo health ==="
curl -sf http://127.0.0.1:8001/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print({k:d.get(k) for k in ("demo_mode","demo_mode_source","demo_relaxed_evidence")})'
