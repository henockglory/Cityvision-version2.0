#!/usr/bin/env bash
# Keep rules-engine alive and MQTT-live — restart on HTTP down or MQTT zombie.
# Zombie = /health OK but mqtt_connected=false OR last_mqtt_msg_age_sec stale
# while upstream (AI Frigate bridge MQTT) is still publishing.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

LOGDIR="$ROOT/logs"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

RULES_PORT="${RULES_ENGINE_PORT:-8010}"
RULES_URL="http://127.0.0.1:${RULES_PORT}"
AI_URL="${AI_URL:-http://127.0.0.1:8001}"
INTERVAL="${WATCH_RULES_INTERVAL:-15}"
STALE_SEC="${WATCH_RULES_MQTT_STALE_SEC:-90}"
COOLDOWN="${WATCH_RULES_RESTART_COOLDOWN_SEC:-60}"
RESTART_FLAG="${LOGDIR}/rules-engine.restart-request"
LAST_RESTART_FILE="${LOGDIR}/.watch-rules-engine.last-restart"

mkdir -p "$LOGDIR"
# Drop stale restart flags from a previous boot/supervisor tick — Start already
# brought rules-engine up; consuming an old flag mid-launch causes GATE FAIL RULES.
if [[ -f "$RESTART_FLAG" ]]; then
  echo "[watch-rules-engine] clearing stale restart-request on start"
  rm -f "$RESTART_FLAG" 2>/dev/null || true
fi
echo "[watch-rules-engine] monitoring ${RULES_URL}/health every ${INTERVAL}s (mqtt_stale>${STALE_SEC}s)"

last_restart_epoch() {
  if [[ -f "$LAST_RESTART_FILE" ]]; then
    cat "$LAST_RESTART_FILE" 2>/dev/null || echo 0
  else
    echo 0
  fi
}

in_cooldown() {
  local now last elapsed
  now="$(date +%s)"
  last="$(last_restart_epoch)"
  elapsed=$((now - last))
  (( elapsed < COOLDOWN ))
}

do_restart() {
  local reason="$1"
  if in_cooldown; then
    echo "[watch-rules-engine] SKIP restart (cooldown ${COOLDOWN}s) reason=${reason} ($(date -Iseconds))"
    # Consume the flag so we do not spin on the same stale request every INTERVAL.
    [[ "$reason" == "restart-request-flag" ]] && rm -f "$RESTART_FLAG" 2>/dev/null || true
    return 0
  fi
  echo "[watch-rules-engine] RESTART reason=${reason} ($(date -Iseconds))"
  date +%s >"$LAST_RESTART_FILE"
  rm -f "$RESTART_FLAG" 2>/dev/null || true
  bash "$ROOT/scripts/_start-rules-engine.sh" || true
  sleep 3
}

ai_bridge_mqtt() {
  curl -sf --max-time 3 "${AI_URL}/health" 2>/dev/null \
    | python3 -c 'import json,sys
try:
  d=json.load(sys.stdin)
  print(int(d.get("frigate_bridge_mqtt") or 0))
except Exception:
  print(0)' 2>/dev/null || echo 0
}

rules_health_json() {
  curl -sf --max-time 3 "${RULES_URL}/health" 2>/dev/null || true
}

upstream_publishing() {
  # True if AI bridge MQTT counter advances over a short window, or was already >0 and AI is up.
  local m0 m1
  m0="$(ai_bridge_mqtt)"
  sleep 5
  m1="$(ai_bridge_mqtt)"
  if [[ "$m1" =~ ^[0-9]+$ ]] && [[ "$m0" =~ ^[0-9]+$ ]] && (( m1 > m0 )); then
    return 0
  fi
  # Fallback: recent events in DB (optional — ignore failures)
  local n
  n="$(docker exec citevision-v2-postgres psql -U citevision -d citevision -tAc \
    "SELECT count(*)::int FROM events WHERE occurred_at > now() - interval '2 minutes';" \
    2>/dev/null | tr -d '[:space:]' || echo 0)"
  [[ "$n" =~ ^[1-9][0-9]*$ ]]
}

PREV_AI_MQTT="$(ai_bridge_mqtt)"

while true; do
  # Supervisor / platform heal request
  if [[ -f "$RESTART_FLAG" ]]; then
    do_restart "restart-request-flag"
    PREV_AI_MQTT="$(ai_bridge_mqtt)"
    sleep "$INTERVAL"
    continue
  fi

  BODY="$(rules_health_json)"
  if [[ -z "$BODY" ]]; then
    do_restart "http_down"
    PREV_AI_MQTT="$(ai_bridge_mqtt)"
    sleep "$INTERVAL"
    continue
  fi

  EVAL="$(printf '%s' "$BODY" | python3 -c "
import json,sys
d=json.load(sys.stdin)
conn=d.get('mqtt_connected')
age=d.get('last_mqtt_msg_age_sec')
try:
  age_i=int(age) if age is not None else -1
except Exception:
  age_i=-1
stale_lim=int('${STALE_SEC}')
connected=conn in (True,1,'1','true','True')
# age==-1 = never received yet (boot grace: not a zombie by itself)
stale=age_i >= stale_lim
zombie=(not connected) or stale
print('connected='+('1' if connected else '0'))
print('age='+str(age_i))
print('zombie='+('1' if zombie else '0'))
" 2>/dev/null || echo -e "connected=0\nage=-1\nzombie=1")"

  CONNECTED="$(printf '%s\n' "$EVAL" | awk -F= '/^connected=/{print $2}')"
  AGE="$(printf '%s\n' "$EVAL" | awk -F= '/^age=/{print $2}')"
  ZOMBIE="$(printf '%s\n' "$EVAL" | awk -F= '/^zombie=/{print $2}')"

  if [[ "$ZOMBIE" == "1" ]]; then
    CUR_AI="$(ai_bridge_mqtt)"
    # Only restart for MQTT zombie when upstream is alive (avoid restart storms at idle boot)
    UPSTREAM=0
    if [[ "$CUR_AI" =~ ^[0-9]+$ ]] && [[ "$PREV_AI_MQTT" =~ ^[0-9]+$ ]] && (( CUR_AI > PREV_AI_MQTT )); then
      UPSTREAM=1
    elif upstream_publishing; then
      UPSTREAM=1
    fi
    PREV_AI_MQTT="$CUR_AI"
    if [[ "$UPSTREAM" == "1" ]]; then
      do_restart "mqtt_zombie connected=${CONNECTED} age=${AGE}s stale_lim=${STALE_SEC}s"
    else
      echo "[watch-rules-engine] mqtt soft-stale connected=${CONNECTED} age=${AGE}s but upstream quiet — wait ($(date -Iseconds))"
    fi
  else
    PREV_AI_MQTT="$(ai_bridge_mqtt)"
  fi

  sleep "$INTERVAL"
done
