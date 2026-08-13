#!/usr/bin/env bash
# Keep Vite (:5174) alive so the browser proxy to /health/platform stays usable.
# Launched by start-full-stack.sh via start_bg after the service gate.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENSURE="$SCRIPT_DIR/ensure-frontend.sh"
UI_URL="${CITEVISION_UI_URL:-http://127.0.0.1:5174}"
PLATFORM_URL="${UI_URL%/}/health/platform"
INTERVAL="${CITEVISION_WATCH_FRONTEND_INTERVAL:-8}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

ui_up() {
  curl -sf --max-time 3 "${UI_URL%/}/" >/dev/null 2>&1
}

platform_proxy_ok() {
  local body
  body="$(curl -sf --max-time 8 "$PLATFORM_URL" 2>/dev/null || true)"
  [[ -n "$body" ]] || return 1
  # Reachable platform JSON with components (do not require models_all_ok here —
  # that is the Start gate; watchdog only keeps the UI/proxy process alive).
  printf '%s' "$body" | python3 -c '
import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    sys.exit(1)
sys.exit(0 if isinstance(d, dict) and "components" in d else 1)
' 2>/dev/null
}

log "watch-frontend started (interval=${INTERVAL}s) ui=$UI_URL mode=${CITEVISION_FRONTEND_MODE:-static}"
fail_streak=0
while true; do
  if ui_up && platform_proxy_ok; then
    fail_streak=0
  else
    fail_streak=$((fail_streak + 1))
    if ui_up; then
      log "proxy unhealthy (streak=$fail_streak) — Vite up but /health/platform via proxy failed"
      # Soft heal: only restart Vite every 3rd miss to avoid thrash when API is briefly busy.
      if (( fail_streak % 3 == 0 )); then
        log "heal: ensure-frontend"
        bash "$ENSURE" >/dev/null 2>&1 || true
      fi
    else
      log "UI down (streak=$fail_streak) — ensure-frontend"
      bash "$ENSURE" >/dev/null 2>&1 || true
    fi
  fi
  sleep "$INTERVAL"
done
