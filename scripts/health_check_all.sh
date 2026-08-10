#!/usr/bin/env bash
# CitéVision Sprint 0 — health check unique (I1–I8 + disque).
# Run BEFORE every validation session. Exit 0 = all green; non-zero = blockers.
# Docker Desktop is FORBIDDEN — native WSL dockerd only.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAIL=0
WARN=0
DISK_WARN_PCT="${DISK_WARN_PCT:-80}"
AI_URL="${AI_URL:-http://127.0.0.1:8001}"
API_URL="${API_URL:-http://127.0.0.1:8081}"
RULES_URL="${RULES_ENGINE_URL:-http://127.0.0.1:8010}"
UI_URL="${UI_URL:-http://127.0.0.1:5174}"
FRIGATE_URL="${FRIGATE_URL:-http://127.0.0.1:5000}"
GO2RTC_URL="${GO2RTC_URL:-http://127.0.0.1:1984}"
MAILHOG_URL="${MAILHOG_URL:-http://127.0.0.1:8025}"
PG_CONTAINER="${PG_CONTAINER:-citevision-v2-postgres}"
PG_USER="${POSTGRES_USER:-citevision}"
RULES_MQTT_STALE_SEC="${RULES_MQTT_STALE_SEC:-120}"

# Phase A Tâche 8: health from /mnt/c is misleading (edits ≠ runtime).
if [[ "$ROOT" == /mnt/c/* ]] || [[ "$ROOT" == /mnt/d/* ]]; then
  echo "[FAIL] health_check_all refuse ROOT under /mnt/* (got $ROOT)."
  echo "       Run from native WSL tree: cd ~/citevision-v2 && bash scripts/health_check_all.sh"
  exit 1
fi

ok()   { printf '[OK]   %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; WARN=$((WARN + 1)); }
fail() { printf '[FAIL] %s\n' "$*"; FAIL=$((FAIL + 1)); }

json_len() {
  # stdin JSON object/array -> length; else 0
  python3 -c 'import json,sys
try:
  d=json.load(sys.stdin)
  print(len(d) if isinstance(d,(dict,list)) else 0)
except Exception:
  print(0)' 2>/dev/null || echo 0
}

echo "=== CitéVision health_check_all $(date -Is) ==="
echo "ROOT=$ROOT"
echo

echo "--- disk ---"
if command -v df >/dev/null 2>&1; then
  USE_PCT="$(df -P / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')"
  AVAIL="$(df -h / | awk 'NR==2 {print $4}')"
  if [[ -n "${USE_PCT:-}" ]] && [[ "$USE_PCT" =~ ^[0-9]+$ ]] && (( USE_PCT >= DISK_WARN_PCT )); then
    fail "root filesystem ${USE_PCT}% used (avail=$AVAIL, threshold=${DISK_WARN_PCT}%) — purge before demo"
  else
    ok "root filesystem ${USE_PCT:-?}% used (avail=$AVAIL)"
  fi
  # Phase A reval: WARN if Windows C: free < 40G or Frigate recordings volume > 20G
  C_AVAIL_G="$(df -P /mnt/c 2>/dev/null | awk 'NR==2 {printf "%d", $4/1024/1024}')"
  if [[ -n "${C_AVAIL_G:-}" ]] && [[ "$C_AVAIL_G" =~ ^[0-9]+$ ]] && (( C_AVAIL_G < 40 )); then
    warn "Windows C: free ${C_AVAIL_G}G < 40G — abort validation / purge before continuing"
  elif [[ -n "${C_AVAIL_G:-}" ]]; then
    ok "Windows C: free ${C_AVAIL_G}G"
  fi
  FRIG_REC="/var/lib/docker/volumes/infra_frigate_recordings/_data"
  if [[ -d "$FRIG_REC" ]]; then
    FRIG_G="$(sudo du -s -BG "$FRIG_REC" 2>/dev/null | awk '{gsub(/G/,"",$1); print $1}')"
    if [[ -n "${FRIG_G:-}" ]] && [[ "$FRIG_G" =~ ^[0-9]+$ ]] && (( FRIG_G > 20 )); then
      warn "Frigate recordings ${FRIG_G}G > 20G — run demo-retention-purge.sh"
    elif [[ -n "${FRIG_G:-}" ]]; then
      ok "Frigate recordings ${FRIG_G}G"
    fi
  fi
else
  warn "df not available"
fi
echo

echo "--- dockerd (native WSL) ---"
if docker info >/dev/null 2>&1; then
  ok "dockerd reachable"
else
  warn "dockerd down — starting via scripts/_start_dockerd_wsl.sh"
  if [[ -f "$ROOT/scripts/_start_dockerd_wsl.sh" ]]; then
    if bash "$ROOT/scripts/_start_dockerd_wsl.sh"; then
      ok "dockerd started"
    else
      fail "could not start dockerd (Docker Desktop forbidden)"
    fi
  else
    fail "missing $ROOT/scripts/_start_dockerd_wsl.sh"
  fi
fi
echo

# shellcheck source=scripts/lib/service-heal.sh
source "$ROOT/scripts/lib/service-heal.sh" 2>/dev/null || true

echo "--- postgres ---"
if docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1; then
  ok "pg_isready inside $PG_CONTAINER"
else
  warn "pg_isready inside container failed — will rely on host publish check"
fi
if command -v pg_isready >/dev/null 2>&1 && pg_isready -h 127.0.0.1 -p "${POSTGRES_PORT:-5433}" -U "$PG_USER" >/dev/null 2>&1; then
  ok "pg_isready on host :${POSTGRES_PORT:-5433}"
elif declare -F tcp_ok >/dev/null 2>&1 && tcp_ok 127.0.0.1 "${POSTGRES_PORT:-5433}"; then
  ok "postgres host TCP :${POSTGRES_PORT:-5433}"
else
  fail "Postgres host unreachable (:${POSTGRES_PORT:-5433})"
fi
echo

echo "--- containers ---"
for name in citevision-v2-postgres citevision-v2-redis citevision-v2-mosquitto citevision-v2-minio citevision-v2-mailhog citevision-v2-go2rtc citevision-v2-ocr; do
  st="$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || echo missing)"
  if [[ "$st" == "running" ]]; then
    ok "$name running"
  else
    fail "$name status=$st"
  fi
done
FRIGATE_ST="$(docker inspect -f '{{.State.Status}}' citevision-v2-frigate 2>/dev/null || echo missing)"
if [[ "$FRIGATE_ST" == "running" ]]; then
  ok "citevision-v2-frigate running"
else
  warn "citevision-v2-frigate status=$FRIGATE_ST — bringing up via compose --profile frigate"
  # shellcheck source=scripts/lib/env-utils.sh
  source "$ROOT/scripts/lib/env-utils.sh" 2>/dev/null || true
  ENV_FILE="${ENV_FILE:-$ROOT/.env}"
  [[ -f "$ENV_FILE" ]] || ENV_FILE="$(ensure_env_file "$ROOT" 2>/dev/null || echo "$ROOT/.env")"
  if [[ -f "$ROOT/infra/docker-compose.yml" ]]; then
    (cd "$ROOT/infra" && docker compose --env-file "$ENV_FILE" --profile frigate up -d frigate) >/dev/null 2>&1 || true
    sleep 8
  fi
  FRIGATE_ST="$(docker inspect -f '{{.State.Status}}' citevision-v2-frigate 2>/dev/null || echo missing)"
  if [[ "$FRIGATE_ST" == "running" ]]; then
    ok "citevision-v2-frigate running after heal"
  elif [[ "$FRIGATE_ST" == "missing" ]]; then
    fail "citevision-v2-frigate still missing after compose --profile frigate"
  else
    fail "citevision-v2-frigate status=$FRIGATE_ST after heal"
  fi
fi
echo

echo "--- host published ports (container running ≠ port alive) ---"
if declare -F ensure_infra_host_ports >/dev/null 2>&1; then
  set +e
  INFRA_OUT="$(ensure_infra_host_ports 2>&1)"
  INFRA_RC=$?
  set -e
  printf '%s\n' "$INFRA_OUT"
  # Count heals/warns for summary; hard FAIL only if still dead after heal.
  if printf '%s\n' "$INFRA_OUT" | grep -q '\[WARN\]'; then
    WARN=$((WARN + 1))
  fi
  if [[ "$INFRA_RC" -ne 0 ]]; then
    fail "infra host ports still unhealthy after heal (redis/mqtt/postgres/minio/ocr/mailhog)"
  else
    ok "infra host ports reachable"
  fi
else
  fail "scripts/lib/service-heal.sh missing ensure_infra_host_ports"
fi
echo

echo "--- frigate ---"
if curl -sf --max-time 8 "$FRIGATE_URL/api/version" >/dev/null 2>&1; then
  VER="$(curl -sf --max-time 5 "$FRIGATE_URL/api/version" | tr -d '\n' || true)"
  ok "Frigate API up version=${VER:-unknown}"
  CFG="$(curl -sf --max-time 10 "$FRIGATE_URL/api/config" || true)"
  if [[ -n "$CFG" ]]; then
    CAMS="$(printf '%s' "$CFG" | python3 -c 'import json,sys
d=json.load(sys.stdin)
print(len(d.get("cameras") or {}))' 2>/dev/null || echo err)"
    if [[ "$CAMS" == "0" ]]; then
      warn "Frigate cameras={} — attempting docker restart + re-check"
      docker restart citevision-v2-frigate >/dev/null 2>&1 || true
      sleep 25
      CFG2="$(curl -sf --max-time 10 "$FRIGATE_URL/api/config" || true)"
      if [[ -n "$CFG2" ]]; then
        CAMS2="$(printf '%s' "$CFG2" | python3 -c 'import json,sys
d=json.load(sys.stdin)
print(len(d.get("cameras") or {}))' 2>/dev/null || echo err)"
        if [[ "$CAMS2" != "0" ]] && [[ "$CAMS2" != "err" ]]; then
          ok "Frigate cameras count=$CAMS2 after heal"
        else
          warn "Frigate cameras still empty after restart — backend compiler pending"
        fi
      else
        warn "Frigate /api/config empty after restart"
      fi
    elif [[ "$CAMS" == "err" ]]; then
      warn "could not parse Frigate /api/config"
    else
      ok "Frigate cameras count=$CAMS"
    fi
  else
    warn "Frigate /api/config empty/failed"
  fi
else
  warn "Frigate API unreachable — retry compose up + wait"
  ENV_FILE="${ENV_FILE:-$ROOT/.env}"
  (cd "$ROOT/infra" && docker compose --env-file "$ENV_FILE" --profile frigate up -d frigate) >/dev/null 2>&1 || true
  sleep 15
  if curl -sf --max-time 8 "$FRIGATE_URL/api/version" >/dev/null 2>&1; then
    ok "Frigate API up after heal"
  else
    fail "Frigate API unreachable at $FRIGATE_URL"
  fi
fi
echo

echo "--- go2rtc ---"
STREAMS_JSON="$(curl -sf --max-time 5 "$GO2RTC_URL/api/streams" || true)"
if [[ -z "$STREAMS_JSON" ]]; then
  warn "go2rtc API unreachable — free ports 1984/8554/8555 + recreate"
  # shellcheck source=scripts/lib/env-utils.sh
  source "$ROOT/scripts/lib/env-utils.sh" 2>/dev/null || true
  docker rm -f citevision-v2-go2rtc 2>/dev/null || true
  free_port 1984 8554 8555 2>/dev/null || true
  fuser -k 8555/udp 2>/dev/null || true
  sleep 1
  ENV_FILE="${ENV_FILE:-$ROOT/.env}"
  (cd "$ROOT/infra" && docker compose --env-file "$ENV_FILE" up -d go2rtc) >/dev/null 2>&1 || true
  sleep 5
  STREAMS_JSON="$(curl -sf --max-time 5 "$GO2RTC_URL/api/streams" || true)"
fi
if [[ -z "$STREAMS_JSON" ]]; then
  fail "go2rtc API unreachable at $GO2RTC_URL after heal"
else
  STREAMS="$(printf '%s' "$STREAMS_JSON" | json_len)"
  if [[ "$STREAMS" == "0" ]]; then
    warn "go2rtc streams_registered=0 — running ensure-demo-streams.sh"
    if [[ -f "$ROOT/scripts/ensure-demo-streams.sh" ]]; then
      bash "$ROOT/scripts/ensure-demo-streams.sh" || warn "ensure-demo-streams.sh exited non-zero"
      STREAMS2="$(curl -sf --max-time 5 "$GO2RTC_URL/api/streams" | json_len)"
      if [[ "$STREAMS2" == "0" ]]; then
        # go2rtc daemon up is enough for launch; demo stream inventory is data-dependent.
        warn "go2rtc still streams_registered=0 after heal — demos may need re-upload; API is up"
      else
        ok "go2rtc streams_registered=$STREAMS2 after heal"
      fi
    else
      warn "missing ensure-demo-streams.sh and streams=0"
    fi
  else
    ok "go2rtc streams_registered=$STREAMS"
  fi
fi
echo

echo "--- ai-engine ---"
# Ensure bridge kill-switches in .env before any AI restart (Frigate-primary).
if [[ -f "$ROOT/scripts/lib/env-utils.sh" ]]; then
  # shellcheck source=scripts/lib/env-utils.sh
  source "$ROOT/scripts/lib/env-utils.sh" 2>/dev/null || true
  ensure_demo_validation_env "$ROOT" "${ENV_FILE:-$ROOT/.env}" 2>/dev/null || true
fi
UVICORN_N="$(pgrep -af 'uvicorn.*citevision|citevision_ai' 2>/dev/null | grep -vE 'grep|pgrep|health_check' | wc -l | tr -d ' ')"
UVICORN_N="${UVICORN_N:-0}"
if (( UVICORN_N > 1 )); then
  warn "multiple AI processes ($UVICORN_N) — restarting via scripts/_restart_ai.py"
  if [[ -f "$ROOT/scripts/_restart_ai.py" ]]; then
    python3 "$ROOT/scripts/_restart_ai.py" || warn "_restart_ai.py failed"
  fi
elif (( UVICORN_N == 0 )); then
  warn "no uvicorn citevision_ai — starting via scripts/_restart_ai.py"
  if [[ -f "$ROOT/scripts/_restart_ai.py" ]]; then
    python3 "$ROOT/scripts/_restart_ai.py" || warn "_restart_ai.py failed"
    sleep 5
  elif [[ -f "$ROOT/scripts/run-ai-engine.sh" ]]; then
    bash "$ROOT/scripts/run-ai-engine.sh" >/tmp/citevision-ai-heal.log 2>&1 &
    sleep 8
  else
    warn "missing _restart_ai.py / run-ai-engine.sh"
  fi
  UVICORN_N="$(pgrep -af 'uvicorn.*citevision|citevision_ai' 2>/dev/null | grep -vE 'grep|pgrep|health_check' | wc -l | tr -d ' ')"
  UVICORN_N="${UVICORN_N:-0}"
  if (( UVICORN_N >= 1 )); then
    ok "AI process started (count=$UVICORN_N)"
  else
    warn "AI process still absent after heal attempt"
  fi
else
  ok "single AI process detected"
fi

HEALTH_RAW="$(curl -sS --max-time 5 -w '\n%{http_code}' "$AI_URL/health" 2>/dev/null || true)"
if [[ -z "$HEALTH_RAW" ]]; then
  warn "AI /health unreachable — one more restart attempt"
  [[ -f "$ROOT/scripts/_restart_ai.py" ]] && python3 "$ROOT/scripts/_restart_ai.py" || true
  sleep 8
  HEALTH_RAW="$(curl -sS --max-time 8 -w '\n%{http_code}' "$AI_URL/health" 2>/dev/null || true)"
fi
if [[ -z "$HEALTH_RAW" ]]; then
  fail "AI /health unreachable at $AI_URL"
else
  HTTP_CODE="$(printf '%s' "$HEALTH_RAW" | tail -n1)"
  BODY="$(printf '%s' "$HEALTH_RAW" | sed '$d')"
  if [[ "$HTTP_CODE" != "200" ]]; then
    fail "AI /health HTTP ${HTTP_CODE:-?} (GPU/models) $(printf '%s' "$BODY" | head -c 180)"
  else
    ok "AI /health HTTP 200 at $AI_URL"
    if printf '%s' "$BODY" | python3 -c 'import json,sys
d=json.load(sys.stdin)
gpu=str(d.get("gpu_active") or d.get("yolo_cuda") or "").lower()
req=str(d.get("gpu_required") or "").lower()
print("gpu_active="+gpu+" gpu_required="+req+" provider="+str(d.get("yolo_provider")))
if req in ("true","1","yes") and gpu not in ("true","1","yes"):
  raise SystemExit(42)
' ; then
      ok "GPU health coherent"
    else
      fail "AI /health GPU required but inactive (A.5)"
    fi
    # Frigate-primary bridges: upsert once then FAIL if still missing (permanent heal).
    BRIDGE_PROBE="$(printf '%s' "$BODY" | python3 -c 'import json,sys
d=json.load(sys.stdin)
geom=str(d.get("frigate_geometry_bridge","")).lower()
speed=str(d.get("frigate_speed_bridge","")).lower()
missing=[]
if geom not in ("true","1","yes"):
  missing.append("frigate_geometry_bridge")
if speed not in ("true","1","yes"):
  missing.append("frigate_speed_bridge")
print(",".join(missing) if missing else "ok")
' 2>/dev/null || echo "parse_err")"
    if [[ "$BRIDGE_PROBE" == "ok" ]]; then
      ok "Frigate bridge flags present (geometry+speed)"
    else
      warn "AI /health missing bridges ($BRIDGE_PROBE) — upsert .env + restart AI once"
      ensure_demo_validation_env "$ROOT" "${ENV_FILE:-$ROOT/.env}" 2>/dev/null || true
      [[ -f "$ROOT/scripts/_restart_ai.py" ]] && python3 "$ROOT/scripts/_restart_ai.py" || true
      sleep 10
      BODY2="$(curl -sf --max-time 8 "$AI_URL/health" 2>/dev/null || true)"
      BRIDGE_PROBE2="$(printf '%s' "$BODY2" | python3 -c 'import json,sys
d=json.load(sys.stdin)
geom=str(d.get("frigate_geometry_bridge","")).lower()
speed=str(d.get("frigate_speed_bridge","")).lower()
missing=[]
if geom not in ("true","1","yes"):
  missing.append("frigate_geometry_bridge")
if speed not in ("true","1","yes"):
  missing.append("frigate_speed_bridge")
print(",".join(missing) if missing else "ok")
' 2>/dev/null || echo "parse_err")"
      if [[ "$BRIDGE_PROBE2" == "ok" ]]; then
        ok "Frigate bridge flags present after env upsert + AI restart"
      else
        fail "Frigate bridge flags still missing after heal ($BRIDGE_PROBE2) — see docs/LIVE-RTSP-CHECKLIST.md"
      fi
    fi

    # Install gaps: face / Gemini honesty (STRICT_INSTALL_HEALTH=1 upgrades WARN→FAIL).
    FACE_LOADED="$(printf '%s' "$BODY" | python3 -c 'import json,sys
d=json.load(sys.stdin)
v=d.get("face_loaded")
print("1" if v in (True,1,"1","true","True") else "0")
' 2>/dev/null || echo 0)"
    if [[ "$FACE_LOADED" == "1" ]]; then
      ok "AI face_loaded=true"
    else
      if [[ "${STRICT_INSTALL_HEALTH:-0}" == "1" ]]; then
        fail "AI face_loaded missing/false (InsightFace stack)"
      else
        warn "AI face_loaded missing/false — run ensure-ai-stack / install-ai-models"
      fi
    fi

    GEMINI_CFG="$(printf '%s' "$BODY" | python3 -c 'import json,sys
d=json.load(sys.stdin)
v=d.get("gemini_configured", d.get("gemini_enabled"))
print("1" if v in (True,1,"1","true","True") else "0")
' 2>/dev/null || echo 0)"
    if [[ "$GEMINI_CFG" == "1" ]]; then
      ok "AI gemini_configured=true"
    else
      if [[ "${STRICT_INSTALL_HEALTH:-0}" == "1" ]]; then
        fail "gemini_configured missing — set GEMINI_API_KEY or ~/.citevision_gemini_key.tmp"
      else
        warn "gemini_configured missing — cabin/face VLM needs GEMINI_API_KEY (keyfile ~/.citevision_gemini_key.tmp)"
      fi
    fi

    # Live Gemini reachability: /health gemini_reachable is lazy unless pinged;
    # under STRICT, call scripts/lib/probe-gemini.sh (list models, no key echo).
    if [[ "${STRICT_INSTALL_HEALTH:-0}" == "1" ]]; then
      if [[ -x "$ROOT/scripts/lib/probe-gemini.sh" ]] || [[ -f "$ROOT/scripts/lib/probe-gemini.sh" ]]; then
        if bash "$ROOT/scripts/lib/probe-gemini.sh" "$ROOT" "${ENV_FILE:-$ROOT/.env}"; then
          ok "gemini_probe reachable (STRICT)"
        else
          fail "gemini_probe FAILED — cle invalide/quota/reseau (Set-CiteVisionGeminiKey.ps1)"
        fi
      else
        fail "scripts/lib/probe-gemini.sh missing"
      fi
    else
      GEMINI_REACH="$(printf '%s' "$BODY" | python3 -c 'import json,sys
d=json.load(sys.stdin)
v=d.get("gemini_reachable")
print("1" if v in (True,1,"1","true","True") else "0")
' 2>/dev/null || echo 0)"
      if [[ "$GEMINI_REACH" == "1" ]]; then
        ok "AI gemini_reachable=true"
      else
        warn "AI gemini_reachable=false (lazy until VLM job or GEMINI_HEALTH_PING=1)"
      fi
    fi
  fi
fi

# Parasitic ghost module must never ship beside the real identity package.
if [[ -f "$ROOT/ai-engine/src/citevision_ai/face.py" ]]; then
  fail "ghost ai-engine/src/citevision_ai/face.py present — remove; use identity/ InsightFace package"
else
  ok "no ghost citevision_ai/face.py"
fi

# When face watchlist entries exist, Frigate YAML should enable face_recognition.
WATCH_N="$(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d citevision -tAc \
  "SELECT COALESCE(SUM(jsonb_array_length(entries)),0)::int FROM surveillance_lists WHERE list_type='face_watchlist' AND is_active=TRUE;" \
  2>/dev/null | tr -d '[:space:]' || echo 0)"
WATCH_N="${WATCH_N:-0}"
YAML_CANDIDATES=(
  "$ROOT/infra/frigate-config/frigate.generated.yml"
  "$ROOT/infra/frigate-config/config.yml"
)
if [[ "$WATCH_N" =~ ^[1-9][0-9]*$ ]]; then
  FACE_REC_OK=0
  for y in "${YAML_CANDIDATES[@]}"; do
    if [[ -f "$y" ]] && grep -A8 -E 'face_recognition:' "$y" 2>/dev/null | grep -qE 'enabled:[[:space:]]*true'; then
      FACE_REC_OK=1
      break
    fi
  done
  if [[ "$FACE_REC_OK" == "1" ]]; then
    ok "Frigate face_recognition.enabled with watchlist entries ($WATCH_N)"
  else
    warn "watchlist entries=$WATCH_N but face_recognition.enabled not found in generated Frigate YAML — enroll/sync may be pending"
  fi
else
  ok "face watchlist empty (face_recognition optional until enroll via UI Settings)"
fi
echo

echo "--- backend ---"
if curl -sf --max-time 5 "$API_URL/health" >/dev/null 2>&1 || curl -sf --max-time 5 "$API_URL/api/v1/health" >/dev/null 2>&1; then
  ok "API reachable at $API_URL"
else
  warn "API not responding at $API_URL — attempting _restart_backend.sh"
  if [[ -f "$ROOT/scripts/_restart_backend.sh" ]]; then
    bash "$ROOT/scripts/_restart_backend.sh" >/dev/null 2>&1 || true
    sleep 15
    if curl -sf --max-time 5 "$API_URL/health" >/dev/null 2>&1 || curl -sf --max-time 5 "$API_URL/api/v1/health" >/dev/null 2>&1; then
      ok "API reachable at $API_URL after heal"
    else
      fail "API still down at $API_URL after restart"
    fi
  else
    fail "API not responding at $API_URL (missing _restart_backend.sh)"
  fi
fi
echo

echo "--- rules-engine (MQTT liveness) ---"
RULES_RAW="$(curl -sf --max-time 5 "$RULES_URL/health" 2>/dev/null || true)"
if [[ -z "$RULES_RAW" ]]; then
  warn "rules-engine /health unreachable — restarting via _start-rules-engine.sh"
  if [[ -f "$ROOT/scripts/_start-rules-engine.sh" ]]; then
    bash "$ROOT/scripts/_start-rules-engine.sh" >/dev/null 2>&1 || true
    sleep 5
    RULES_RAW="$(curl -sf --max-time 5 "$RULES_URL/health" 2>/dev/null || true)"
  fi
fi
if [[ -z "$RULES_RAW" ]]; then
  fail "rules-engine unreachable at $RULES_URL"
else
  RULES_EVAL="$(printf '%s' "$RULES_RAW" | python3 -c "
import json,sys
d=json.load(sys.stdin)
ar=int(d.get('active_rules') or 0)
conn=d.get('mqtt_connected')
age=d.get('last_mqtt_msg_age_sec')
try:
  age_i=int(age) if age is not None else -1
except Exception:
  age_i=-1
connected=conn in (True,1,'1','true','True')
stale_lim=int('${RULES_MQTT_STALE_SEC}')
# Missing mqtt fields = old binary still running — warn, do not hard-fail yet.
has_mqtt='mqtt_connected' in d
stale=has_mqtt and ((not connected) or (age_i >= 0 and age_i > stale_lim))
print('ar='+str(ar))
print('has_mqtt='+('1' if has_mqtt else '0'))
print('connected='+('1' if connected else '0'))
print('age='+str(age_i))
print('stale='+('1' if stale else '0'))
print('msgs='+str(d.get('mqtt_messages_total','')))
" 2>/dev/null || echo 'ar=0
has_mqtt=0
connected=0
age=-1
stale=1
msgs=')"
  R_AR="$(printf '%s\n' "$RULES_EVAL" | awk -F= '/^ar=/{print $2}')"
  R_HAS="$(printf '%s\n' "$RULES_EVAL" | awk -F= '/^has_mqtt=/{print $2}')"
  R_CONN="$(printf '%s\n' "$RULES_EVAL" | awk -F= '/^connected=/{print $2}')"
  R_AGE="$(printf '%s\n' "$RULES_EVAL" | awk -F= '/^age=/{print $2}')"
  R_STALE="$(printf '%s\n' "$RULES_EVAL" | awk -F= '/^stale=/{print $2}')"
  if [[ "${R_AR:-0}" =~ ^[0-9]+$ ]] && (( R_AR > 0 )); then
    ok "rules-engine active_rules=$R_AR"
  else
    warn "rules-engine active_rules=${R_AR:-0}"
  fi
  if [[ "$R_HAS" != "1" ]]; then
    warn "rules-engine /health missing mqtt_* fields — rebuild/restart rules-engine for MQTT watchdog"
  elif [[ "$R_STALE" == "1" ]]; then
    MOSQ_UP=0
    if docker inspect -f '{{.State.Status}}' citevision-v2-mosquitto 2>/dev/null | grep -qx running; then
      MOSQ_UP=1
    fi
    if [[ "$MOSQ_UP" == "1" ]]; then
      fail "rules-engine MQTT stale/disconnected (connected=$R_CONN age=${R_AGE}s lim=${RULES_MQTT_STALE_SEC}s) while mosquitto up — restart rules-engine / ensure watch-rules-engine"
      # Nudge watchdog if present
      mkdir -p "$ROOT/logs"
      echo "health_check_all mqtt_stale $(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$ROOT/logs/rules-engine.restart-request"
    else
      fail "rules-engine MQTT stale and mosquitto container not running"
    fi
  else
    ok "rules-engine MQTT live (connected=$R_CONN age=${R_AGE}s)"
  fi
  if ! pgrep -af 'watch-rules-engine' >/dev/null 2>&1; then
    warn "watch-rules-engine not running — start via start-full-stack or: bash scripts/watch-rules-engine.sh &"
  else
    ok "watch-rules-engine process present"
  fi
fi
echo

echo "--- ui ---"
if curl -sf --max-time 5 "$UI_URL/" >/dev/null 2>&1 || curl -sf --max-time 5 "$UI_URL/index.html" >/dev/null 2>&1; then
  ok "UI reachable at $UI_URL"
else
  if [[ "${STRICT_INSTALL_HEALTH:-0}" == "1" ]]; then
    fail "UI $UI_URL down — Start/STRICT requires Vite"
  else
    warn "UI $UI_URL down — start Vite before visual validation"
  fi
fi
echo

echo "--- mailhog ---"
if curl -sf --max-time 5 "$MAILHOG_URL/" >/dev/null 2>&1; then
  ok "Mailhog UI at $MAILHOG_URL"
else
  fail "Mailhog unreachable at $MAILHOG_URL"
fi
echo

echo "=== summary FAIL=$FAIL WARN=$WARN ==="
if (( FAIL > 0 )); then
  echo "RESULT: RED — fix FAIL items before validation"
  exit 1
fi
if (( WARN > 0 )); then
  echo "RESULT: YELLOW — proceed with caution"
  exit 0
fi
echo "RESULT: GREEN"
exit 0
