#!/usr/bin/env bash
set -euo pipefail
ROOT=~/citevision-v2
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"

echo "=== Backend restart ==="
stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
free_port 8081 2>/dev/null || true
sleep 2
start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:8081/health" 90 && echo "[OK] backend :8081" || echo "[FAIL] backend"

echo "=== Status ==="
curl -s http://localhost:8081/health | python3 -m json.tool 2>/dev/null | head -5
curl -s http://localhost:8010/health | python3 -m json.tool 2>/dev/null | head -5
