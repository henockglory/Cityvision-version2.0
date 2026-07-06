#!/usr/bin/env bash
# Keep Vite frontend alive on :5174 (survives partial restarts).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

ENV_FILE="$(ensure_env_file "$ROOT")"
LOGDIR="$ROOT/logs"
BACKEND_PORT="${API_PORT:-8081}"
AI_PORT="${AI_ENGINE_PORT:-8001}"
RULES_PORT="${RULES_ENGINE_PORT:-8010}"

demo_stack_ok() {
  curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1 || return 1
  curl -sf "http://127.0.0.1:${AI_PORT}/health" >/dev/null 2>&1 || return 1
  curl -sf "http://127.0.0.1:${RULES_PORT}/health" >/dev/null 2>&1 || return 1
  return 0
}

if curl -sf "http://127.0.0.1:5174/" >/dev/null 2>&1; then
  if demo_stack_ok; then
    echo "[OK] Frontend already up http://localhost:5174"
    exit 0
  fi
  echo "[WARN] Frontend up but demo stack incomplete — repairing pipeline"
  bash "$ROOT/scripts/ensure-demo-pipeline.sh" || {
    echo "[FAIL] Could not repair demo stack — run: bash scripts/restart-api-frontend.sh" >&2
    exit 1
  }
  if demo_stack_ok; then
    echo "[OK] Frontend http://localhost:5174 (stack repaired)"
    exit 0
  fi
  echo "[FAIL] Stack still incomplete after repair" >&2
  exit 1
fi

stop_from_pid "$LOGDIR/frontend.pid" 2>/dev/null || true
free_port 5174 5175 5176 5177 2>/dev/null || true
sleep 1

if [[ "$(uname -s)" == "Linux" ]] && [[ ! -d "$ROOT/frontend/node_modules/@rollup/rollup-linux-x64-gnu" ]]; then
  (cd "$ROOT/frontend" && npm install @rollup/rollup-linux-x64-gnu --no-save --silent) || true
fi

start_bg frontend "$ROOT/frontend" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$LOGDIR" "$ENV_FILE"
if ! wait_http_ok "http://127.0.0.1:5174/" 90; then
  echo "[FAIL] Frontend did not start — see logs/frontend.log" >&2
  tail -20 "$LOGDIR/frontend.log" 2>/dev/null || true
  exit 1
fi
echo "[OK] Frontend http://localhost:5174"
