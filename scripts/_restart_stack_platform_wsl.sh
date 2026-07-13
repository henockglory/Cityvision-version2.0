#!/usr/bin/env bash
set -euo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
export PATH="$PATH:/usr/local/go/bin"
source scripts/lib/env-utils.sh
LOGDIR="$ROOT/logs"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

echo "=== Docker infra ==="
docker compose -f infra/docker-compose.yml up -d postgres redis mosquitto minio 2>&1 | tail -6 || true
sleep 6

echo "=== Stop old backend/frontend ==="
stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
stop_from_pid "$LOGDIR/frontend.pid" 2>/dev/null || true
pkill -f citevision-api 2>/dev/null || true
pkill -f 'vite.*5174' 2>/dev/null || true
free_port 8081 5174 2>/dev/null || true
sleep 2

echo "=== Build backend ==="
mkdir -p backend/bin
(cd backend && go build -o bin/citevision-api ./cmd/api)
start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:8081/health" 60
echo "[OK] Backend"
curl -sf http://127.0.0.1:8081/health/platform | python3 -m json.tool 2>/dev/null | head -20 || curl -sf http://127.0.0.1:8081/health/platform | head -c 400
echo ""

echo "=== Restart frontend ==="
start_bg frontend "$ROOT/frontend" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:5174/" 90
echo "[OK] Frontend http://localhost:5174"
