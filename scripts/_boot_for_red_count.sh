#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
export PATH="/usr/local/go/bin:$HOME/go/bin:$PATH"

# Sync key scripts
for f in scripts/stack-up.sh scripts/validate_rule_dod.py scripts/_validate_rule_frigate_1hit.py scripts/capture_alerts_ui.mjs; do
  cp -f "$WIN/$f" "$ROOT/$f" 2>/dev/null || true
  sed -i 's/\r$//' "$ROOT/$f" 2>/dev/null || true
done

grep -q '^OCR_URL=' .env || echo 'OCR_URL=http://127.0.0.1:8181/ocr' >> .env
sed -i 's|^OCR_URL=.*|OCR_URL=http://127.0.0.1:8181/ocr|' .env

bash scripts/stack-up.sh || true

# OCR profile
cd infra
docker compose --env-file "$ROOT/.env" --profile ocr up -d citevision-ocr || true
cd "$ROOT"
for i in $(seq 1 30); do
  curl -sf --max-time 3 http://127.0.0.1:8181/healthz >/dev/null && break
  sleep 2
done

# Vite
if ! curl -sf --max-time 2 http://127.0.0.1:5174/ >/dev/null; then
  cd frontend
  nohup npm run dev -- --host 127.0.0.1 --port 5174 > /tmp/citevision-vite.log 2>&1 &
  for i in $(seq 1 25); do curl -sf --max-time 2 http://127.0.0.1:5174/ >/dev/null && break; sleep 1; done
  cd "$ROOT"
fi

bash scripts/_restart_backend.sh || true
bash scripts/_start-rules-engine.sh || true

source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial -H "X-Internal-Key: $KEY" || true
echo

bash scripts/health_check_all.sh || true
echo "OCR=$(curl -sf http://127.0.0.1:8181/healthz || echo down)"
echo "=== boot done $(date -Is) ==="
