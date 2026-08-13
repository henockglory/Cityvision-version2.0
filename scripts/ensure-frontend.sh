#!/usr/bin/env bash
# Keep product UI alive on :5174.
# Default MODE=static: low-memory Node static+proxy (survives WSL OOM that kills Vite HMR).
# MODE=dev: classic Vite HMR (heavier — only for local UI work).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

ENV_FILE="$(ensure_env_file "$ROOT")"
LOGDIR="$ROOT/logs"
BACKEND_PORT="${API_PORT:-8081}"
AI_PORT="${AI_ENGINE_PORT:-8001}"
RULES_PORT="${RULES_ENGINE_PORT:-8010}"
# static | preview | dev — product Start uses static
MODE="${CITEVISION_FRONTEND_MODE:-static}"

demo_stack_ok() {
  curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1 || return 1
  curl -sf "http://127.0.0.1:${AI_PORT}/health" >/dev/null 2>&1 || return 1
  curl -sf "http://127.0.0.1:${RULES_PORT}/health" >/dev/null 2>&1 || return 1
  return 0
}

platform_proxy_ok() {
  curl -sf --max-time 8 "http://127.0.0.1:5174/health/platform" 2>/dev/null \
    | python3 -c 'import json,sys
d=json.load(sys.stdin)
sys.exit(0 if isinstance(d, dict) and "components" in d else 1)' 2>/dev/null
}

if curl -sf "http://127.0.0.1:5174/" >/dev/null 2>&1; then
  if demo_stack_ok && platform_proxy_ok; then
    echo "[OK] Frontend already up http://localhost:5174 (mode=$MODE)"
    exit 0
  fi
  if demo_stack_ok && ! platform_proxy_ok; then
    echo "[WARN] UI up but /health/platform proxy broken — restarting frontend"
    stop_from_pid "$LOGDIR/frontend.pid" 2>/dev/null || true
    pkill -f 'serve-frontend-static.mjs|vite.*5174' 2>/dev/null || true
    free_port 5174 5175 5176 5177 2>/dev/null || true
    sleep 1
  elif ! demo_stack_ok; then
    echo "[WARN] Frontend up but demo stack incomplete — repairing pipeline"
    bash "$ROOT/scripts/ensure-demo-pipeline.sh" || {
      echo "[FAIL] Could not repair demo stack — run: bash scripts/restart-api-frontend.sh" >&2
      exit 1
    }
    if demo_stack_ok && platform_proxy_ok; then
      echo "[OK] Frontend http://localhost:5174 (stack repaired)"
      exit 0
    fi
  fi
fi

ensure_dist() {
  if [[ -f "$ROOT/frontend/dist/index.html" ]]; then
    return 0
  fi
  echo "[INFO] building frontend/dist (one-time, replaces Vite HMR)..."
  if [[ "$(uname -s)" == "Linux" ]] && [[ ! -d "$ROOT/frontend/node_modules/@rollup/rollup-linux-x64-gnu" ]]; then
    (cd "$ROOT/frontend" && npm install @rollup/rollup-linux-x64-gnu --no-save --silent) || true
  fi
  # Cap Node heap so build does not OOM-kill the whole WSL session.
  (cd "$ROOT/frontend" && NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=2048}" npm run build) || {
    echo "[FAIL] frontend build failed" >&2
    return 1
  }
}

start_frontend() {
  case "$MODE" in
    static)
      ensure_dist || return 1
      start_bg frontend "$ROOT" "node scripts/serve-frontend-static.mjs" "$LOGDIR" "$ENV_FILE"
      ;;
    preview)
      ensure_dist || return 1
      if [[ "$(uname -s)" == "Linux" ]] && [[ ! -d "$ROOT/frontend/node_modules/@rollup/rollup-linux-x64-gnu" ]]; then
        (cd "$ROOT/frontend" && npm install @rollup/rollup-linux-x64-gnu --no-save --silent) || true
      fi
      start_bg frontend "$ROOT/frontend" "npm run preview -- --host 0.0.0.0 --port 5174 --strictPort" "$LOGDIR" "$ENV_FILE"
      ;;
    dev|*)
      if [[ "$(uname -s)" == "Linux" ]] && [[ ! -d "$ROOT/frontend/node_modules/@rollup/rollup-linux-x64-gnu" ]]; then
        (cd "$ROOT/frontend" && npm install @rollup/rollup-linux-x64-gnu --no-save --silent) || true
      fi
      # Soft cap — still prefer static for product.
      start_bg frontend "$ROOT/frontend" "env NODE_OPTIONS=--max-old-space-size=768 npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$LOGDIR" "$ENV_FILE"
      ;;
  esac
}

stop_from_pid "$LOGDIR/frontend.pid" 2>/dev/null || true
pkill -f 'serve-frontend-static.mjs' 2>/dev/null || true
pkill -f 'vite.*--port 5174|vite --host' 2>/dev/null || true
free_port 5174 5175 5176 5177 2>/dev/null || true
sleep 1

start_frontend || exit 1
if ! wait_http_ok "http://127.0.0.1:5174/" 120; then
  echo "[FAIL] Frontend did not start — see logs/frontend.log" >&2
  tail -40 "$LOGDIR/frontend.log" 2>/dev/null || true
  exit 1
fi
echo "[OK] Frontend http://localhost:5174 (mode=$MODE)"
