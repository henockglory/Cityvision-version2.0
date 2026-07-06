#!/usr/bin/env bash
# Restart AI ingest if frames_processed stops advancing (frozen pipeline).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"
AI_PORT="${AI_ENGINE_PORT:-8001}"
INTERVAL="${WATCH_AI_INTERVAL:-30}"
MIN_DELTA="${WATCH_AI_MIN_FRAMES:-8}"
WINDOW="${WATCH_AI_WINDOW_SEC:-45}"

frames_count() {
  curl -sf "http://127.0.0.1:${AI_PORT}/cameras" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('cameras') or []; print(sum(int(x.get('frames_processed') or 0) for x in c))" 2>/dev/null \
    || echo 0
}

echo "[watch-ai-ingest] monitoring AI frames every ${INTERVAL}s (min +${MIN_DELTA}/${WINDOW}s)"

while true; do
  if curl -sf "http://127.0.0.1:${AI_PORT}/health" >/dev/null 2>&1; then
    f0="$(frames_count)"
    sleep "$WINDOW"
    f1="$(frames_count)"
    delta=$((f1 - f0))
    if [[ "$f0" -gt 0 && "$delta" -lt "$MIN_DELTA" ]]; then
      echo "[watch-ai-ingest] frozen (delta=${delta}) — restarting AI + resync ($(date -Iseconds))"
      bash "$ROOT/scripts/restart-ai-engine.sh" || true
      bash "$ROOT/scripts/ensure-demo-pipeline.sh" || true
    fi
  else
    echo "[watch-ai-ingest] AI down on :${AI_PORT} — restarting pipeline ($(date -Iseconds))"
    bash "$ROOT/scripts/ensure-demo-pipeline.sh" || true
  fi
  sleep "$INTERVAL"
done
