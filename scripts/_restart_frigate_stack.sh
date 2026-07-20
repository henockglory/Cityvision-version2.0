#!/usr/bin/env bash
set -euo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source scripts/lib/env-utils.sh
load_dotenv .env

echo "=== 1. Frigate Docker ==="
if ! docker image inspect ghcr.io/blakeblackshear/frigate:stable >/dev/null 2>&1; then
  echo "[INFO] Pulling Frigate image (~1 Go)…"
  docker pull ghcr.io/blakeblackshear/frigate:stable
fi
docker compose -f infra/docker-compose.yml --env-file .env --profile frigate up -d frigate
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:5000/api/version >/dev/null 2>&1; then
    echo "[OK] Frigate API up"
    break
  fi
  sleep 3
  if [[ "$i" -eq 60 ]]; then
    echo "[WARN] Frigate API not ready — continuing stack restart"
  fi
done

echo "=== 2. Backend + frontend ==="
stop_from_pid logs/backend.pid 2>/dev/null || true
stop_from_pid logs/frontend.pid 2>/dev/null || true
pkill -f citevision-api 2>/dev/null || true
pkill -f 'vite --host' 2>/dev/null || true
free_port 8081 5174 2>/dev/null || true
sleep 2

start_bg backend "$ROOT" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ROOT/.env"
sleep 6
echo "=== /health/frigate ==="
curl -sf http://127.0.0.1:8081/health/frigate || { echo FAIL; tail -20 logs/backend.log; exit 1; }
echo

start_bg frontend "$ROOT/frontend" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$ROOT/logs" "$ROOT/.env"
sleep 12
echo "=== frontend ==="
curl -sf http://127.0.0.1:5174/ >/dev/null && echo OK || echo FAIL

echo "=== 3. Rebuild Frigate config from DB ==="
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild" \
  -H "X-Internal-Key: ${KEY}" && echo "[OK] rebuild" \
  || echo "[WARN] rebuild failed"
docker restart citevision-v2-frigate >/dev/null 2>&1 || true
sleep 15

if [[ -f infra/frigate-config/config.yml ]]; then
  echo "=== cameras in config.yml ==="
  grep -E '^  cv_' infra/frigate-config/config.yml || echo "(no cameras compiled yet)"
fi

echo DONE
