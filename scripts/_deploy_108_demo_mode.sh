#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2

echo "=== sync key files ==="
for f in \
  backend/internal/frigate/sync.go \
  backend/internal/frigate/sync_test.go \
  ai-engine/src/citevision_ai/config.py \
  ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py \
  ai-engine/src/citevision_ai/main.py
do
  cp "/mnt/c/Users/gheno/citevision/$f" "$f"
  sed -i 's/\r$//' "$f"
  echo "ok $f"
done

export PATH="/usr/local/go/bin:/home/gheno/go/bin:${PATH:-}"

echo "=== go test frigate ==="
(cd backend && go test ./internal/frigate/ -count=1 2>&1 | tail -40)

echo "=== rebuild api binary ==="
(cd backend && go build -o bin/citevision-api ./cmd/api/)

echo "=== restart backend ==="
python3 scripts/_restart_backend.py 2>&1 | tail -30

echo "=== wait API ==="
for i in $(seq 1 25); do
  if curl -sf http://127.0.0.1:8081/health >/dev/null 2>&1; then
    echo "API up"
    break
  fi
  sleep 1
done

# shellcheck disable=SC1091
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$PWD")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== frigate rebuild (exclude 108) ==="
curl -sS -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: ${KEY}" -o /tmp/frigate_rebuild.json -w "http=%{http_code}\n" || true
python3 -m json.tool /tmp/frigate_rebuild.json 2>/dev/null || cat /tmp/frigate_rebuild.json || true
echo

echo "=== 108 in config.yml? ==="
if grep -n '192.168.1.108' infra/frigate-config/config.yml; then
  echo "STILL PRESENT"
else
  echo "GONE from config.yml"
fi

echo "=== DEMO_MODE keys ==="
grep -E '^(DEMO_MODE|CITEVISION_DEMO_MODE)=' .env ai-engine/.env generated.env 2>/dev/null || echo "none"

echo "=== restart AI ==="
python3 scripts/_restart_ai.py 2>&1 | tail -50

echo "=== AI /health demo fields ==="
for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:8001/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -sf http://127.0.0.1:8001/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print({k:d.get(k) for k in ("status","demo_mode","demo_mode_source","demo_relaxed_evidence","yolo_cuda")})'
