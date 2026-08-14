#!/usr/bin/env bash
# Keeps the API process alive — restarts backend if /health fails (WSL dev).
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

mkdir -p "$LOGDIR"
echo "[watch-backend] monitoring http://127.0.0.1:$BACKEND_PORT/health every ${INTERVAL}s"
# Prefer IPv4: on WSL, localhost can resolve to ::1 while the API listens on 127.0.0.1 only,
# which caused false "API down" heals that killed mono-camera 1-hit validation.

while true; do
  if ! curl -sf "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; then
    # Confirm with a second probe before heal (avoid flapping on brief blips).
    sleep 2
    if curl -sf "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; then
      sleep "$INTERVAL"
      continue
    fi
    echo "[watch-backend] API down — restarting backend only ($(date -Iseconds))"
    stop_from_pid "$LOGDIR/backend.pid"
    free_port "$BACKEND_PORT"
    sleep 2
    export PATH="$PATH:/usr/local/go/bin"
    GO_BIN="$(command -v go || true)"
    if [[ -z "$GO_BIN" && -x /usr/local/go/bin/go ]]; then
      GO_BIN=/usr/local/go/bin/go
    fi
    if [[ -n "$GO_BIN" ]]; then
      mkdir -p "$ROOT/backend/bin"
      (cd "$ROOT/backend" && "$GO_BIN" build -o "$ROOT/backend/bin/citevision-api" ./cmd/api) || true
    fi
    if [[ -x "$ROOT/backend/bin/citevision-api" ]]; then
      start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
      wait_http_ok "http://127.0.0.1:$BACKEND_PORT/health" 90 || true
      bash "$ROOT/scripts/ensure-demo-pipeline.sh" || true
    else
      echo "[watch-backend] binary missing — run bash scripts/restart-api-frontend.sh" >&2
    fi
  fi
  sleep "$INTERVAL"
done
