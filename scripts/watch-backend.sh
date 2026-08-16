#!/usr/bin/env bash
# Keeps the API process alive — restarts backend if /health fails (WSL dev).
# Also rebuilds citevision-api when Frigate Go sources are newer than the binary
# even if /health is already up (otherwise Start keeps a stale compiler).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

LOGDIR="$ROOT/logs"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
BACKEND_PORT="${API_PORT:-8081}"
INTERVAL="${WATCH_BACKEND_INTERVAL:-20}"
BIN="$ROOT/backend/bin/citevision-api"

mkdir -p "$LOGDIR"
echo "[watch-backend] monitoring http://127.0.0.1:$BACKEND_PORT/health every ${INTERVAL}s"
# Prefer IPv4: on WSL, localhost can resolve to ::1 while the API listens on 127.0.0.1 only,
# which caused false "API down" heals that killed mono-camera 1-hit validation.

api_ok() {
  curl -sf "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1
}

while true; do
  need_restart=0
  was_down=0
  bin_before=$(stat -c %Y "$BIN" 2>/dev/null || echo 0)
  if [[ -x "$ROOT/scripts/lib/ensure-backend-bin.sh" ]]; then
    bash "$ROOT/scripts/lib/ensure-backend-bin.sh" || true
  fi
  bin_after=$(stat -c %Y "$BIN" 2>/dev/null || echo 0)
  if [[ "$bin_after" -gt "$bin_before" ]]; then
    echo "[watch-backend] backend binary rebuilt — will restart API ($(date -Iseconds))"
    need_restart=1
  fi

  if ! api_ok; then
    sleep 2
    if ! api_ok; then
      echo "[watch-backend] API down — restarting backend only ($(date -Iseconds))"
      need_restart=1
      was_down=1
    fi
  fi

  if [[ "$need_restart" -eq 1 ]]; then
    stop_from_pid "$LOGDIR/backend.pid"
    free_port "$BACKEND_PORT"
    sleep 2
    if [[ -x "$BIN" ]]; then
      start_bg backend "$ROOT/backend" "$BIN" "$LOGDIR" "$ENV_FILE"
      wait_http_ok "http://127.0.0.1:$BACKEND_PORT/health" 90 || true
      if [[ "$was_down" -eq 1 ]]; then
        bash "$ROOT/scripts/ensure-demo-pipeline.sh" || true
      fi
    else
      echo "[watch-backend] binary missing — run bash scripts/restart-api-frontend.sh" >&2
    fi
  fi
  sleep "$INTERVAL"
done
