#!/usr/bin/env bash
# Restart AI ingest if frames_processed stops advancing (frozen pipeline),
# or if AI stack models / face are cold ("Stack IA incomplète").
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

ai_stack_cold() {
  # Returns 0 when stack looks incomplete (needs heal).
  curl -sf --max-time 8 "http://127.0.0.1:${AI_PORT}/health" -o /tmp/watch-ai-health.json 2>/dev/null || return 0
  python3 - <<'PY'
import json,sys
d=json.load(open("/tmp/watch-ai-health.json"))
# Prefer explicit flags when present
cold=[]
if d.get("status") not in (None, "ok", "healthy", "degraded"):
  # unknown status — don't force restart solely on that
  pass
# face path: if key exists and is false → cold
for k in ("face_loaded", "insightface_loaded", "models_all_ok"):
  if k in d and d.get(k) in (False, "false", "0", 0):
    cold.append(k)
# nested models map
models=d.get("models") if isinstance(d.get("models"), dict) else {}
for k in ("yolo","phone","belt","plate","face"):
  v=models.get(k)
  if v in (False, "false", "cold", "missing"):
    cold.append(f"models.{k}")
# Frigate bridge expected when FRIGATE_BRIDGE implied by mqtt counter presence
if "frigate_bridge_mqtt" in d:
  # mqtt stall alone is not cold; snapshot_fail storm is OK; face path needs bridge
  pass
sys.exit(0 if cold else 1)
PY
}

heal_ai_stack() {
  echo "[watch-ai-ingest] AI stack cold — ensure-ai-stack + restart ($(date -Iseconds))"
  if [[ -f "$ROOT/scripts/ensure-ai-stack.sh" ]]; then
    bash "$ROOT/scripts/ensure-ai-stack.sh" --fix >>"$LOGDIR/watch-ai-ingest.log" 2>&1 || true
  fi
  if [[ -f "$ROOT/scripts/restart-ai-engine.sh" ]]; then
    bash "$ROOT/scripts/restart-ai-engine.sh" >>"$LOGDIR/watch-ai-ingest.log" 2>&1 || true
  else
    bash "$ROOT/scripts/ensure-demo-pipeline.sh" >>"$LOGDIR/watch-ai-ingest.log" 2>&1 || true
  fi
}

echo "[watch-ai-ingest] monitoring AI frames every ${INTERVAL}s (min +${MIN_DELTA}/${WINDOW}s) + stack cold heal"

while true; do
  if curl -sf "http://127.0.0.1:${AI_PORT}/health" >/dev/null 2>&1; then
    if ai_stack_cold; then
      heal_ai_stack
    fi
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
    if [[ -f "$ROOT/scripts/ensure-ai-stack.sh" ]]; then
      bash "$ROOT/scripts/ensure-ai-stack.sh" --fix >>"$LOGDIR/watch-ai-ingest.log" 2>&1 || true
    fi
  fi
  sleep "$INTERVAL"
done
