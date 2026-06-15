#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

LOGDIR="$ROOT/logs"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

echo "=== Restart backend + frontend ==="
stop_from_pid "$LOGDIR/backend.pid"
stop_from_pid "$LOGDIR/frontend.pid"
free_port 8081 5174
sleep 2

export PATH="$PATH:/usr/local/go/bin"
GO_BIN="$(command -v go)"
if [[ -z "$GO_BIN" && -x /usr/local/go/bin/go ]]; then
  GO_BIN=/usr/local/go/bin/go
fi
if [[ -z "$GO_BIN" ]]; then
  echo "[FAIL] Go not found — install Go or add to PATH" >&2
  exit 1
fi

start_bg backend "$ROOT/backend" "$GO_BIN run ./cmd/api" "$LOGDIR" "$ENV_FILE"
sleep 10

# WSL: ensure rollup native binding when node_modules was installed on Windows
if [[ "$(uname -s)" == "Linux" ]] && [[ ! -d "$ROOT/frontend/node_modules/@rollup/rollup-linux-x64-gnu" ]]; then
  echo "[INFO] Installing rollup Linux native binding..."
  (cd "$ROOT/frontend" && npm install @rollup/rollup-linux-x64-gnu --no-save --silent) || true
fi

start_bg frontend "$ROOT/frontend" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$LOGDIR" "$ENV_FILE"

echo ""
echo "=== Health checks ==="
BACKEND_PORT="${API_PORT:-8081}"
if wait_http_ok "http://localhost:$BACKEND_PORT/health" 90; then
  echo "[OK] Backend http://localhost:$BACKEND_PORT/health"
else
  echo "[FAIL] Backend — tail logs/backend.log"
  tail -20 "$LOGDIR/backend.log"
  exit 1
fi

if wait_http_ok "http://localhost:5174" 60; then
  echo "[OK] Frontend http://localhost:5174"
else
  echo "[FAIL] Frontend — tail logs/frontend.log"
  tail -20 "$LOGDIR/frontend.log"
  exit 1
fi

echo ""
echo "Done. Demo: http://localhost:5174/demo"
