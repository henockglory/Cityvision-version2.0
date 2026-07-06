#!/usr/bin/env bash
# Keeps backend + rules-engine + AI ingest alive (full demo pipeline).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
BACKEND_PORT="${API_PORT:-8081}"
AI_PORT="${AI_ENGINE_PORT:-8001}"
RULES_PORT="${RULES_ENGINE_PORT:-8010}"
INTERVAL="${WATCH_DEMO_STACK_INTERVAL:-25}"
# Consecutive silent cycles before forcing a rules-engine restart to flush stuck MQTT state
_SILENT_MAX="${WATCH_RULES_SILENT_MAX:-8}"
_silent_cycles=0

stack_ok() {
  curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1 \
    && curl -sf "http://127.0.0.1:${AI_PORT}/health" >/dev/null 2>&1 \
    && curl -sf "http://127.0.0.1:${RULES_PORT}/health" >/dev/null 2>&1
}

# Returns 0 if rules-engine processed at least one event in the last INTERVAL*2 seconds.
rules_active() {
  local log="$ROOT/logs/rules-engine.log"
  [[ -f "$log" ]] || return 0   # can't tell → assume ok
  # Look for "rule matched" or "synced" in the last 2*INTERVAL lines
  local window=$(( INTERVAL * 2 ))
  local last_active
  last_active=$(grep -aE 'rule .* matched|synced [0-9]+ active' "$log" 2>/dev/null \
    | tail -1 | awk '{print $1, $2}' || true)
  [[ -z "$last_active" ]] && return 0
  local log_ts rule_age
  log_ts=$(date -d "$last_active" +%s 2>/dev/null || echo 0)
  rule_age=$(( $(date +%s) - log_ts ))
  # Allow up to (INTERVAL * _SILENT_MAX) seconds of silence before flagging
  (( rule_age < INTERVAL * _SILENT_MAX ))
}

echo "[watch-demo-stack] monitoring backend:${BACKEND_PORT} ai:${AI_PORT} rules:${RULES_PORT} every ${INTERVAL}s"

while true; do
  if ! stack_ok; then
    echo "[watch-demo-stack] incomplete stack — repair ($(date -Iseconds))"
    _silent_cycles=0
    bash "$ROOT/scripts/ensure-demo-pipeline.sh" || true
  elif ! rules_active; then
    _silent_cycles=$(( _silent_cycles + 1 ))
    if (( _silent_cycles >= _SILENT_MAX )); then
      echo "[watch-demo-stack] rules-engine silent for $(( _silent_cycles * INTERVAL ))s — restart ($(date -Iseconds))"
      _silent_cycles=0
      bash "$ROOT/scripts/_start-rules-engine.sh" || true
    fi
  else
    _silent_cycles=0
  fi
  sleep "$INTERVAL"
done
