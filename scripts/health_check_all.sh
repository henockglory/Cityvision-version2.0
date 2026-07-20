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
UI_URL="${UI_URL:-http://127.0.0.1:5174}"
FRIGATE_URL="${FRIGATE_URL:-http://127.0.0.1:5000}"
GO2RTC_URL="${GO2RTC_URL:-http://127.0.0.1:1984}"
MAILHOG_URL="${MAILHOG_URL:-http://127.0.0.1:8025}"
PG_CONTAINER="${PG_CONTAINER:-citevision-v2-postgres}"
PG_USER="${POSTGRES_USER:-citevision}"

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

echo "--- postgres ---"
if docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1; then
  ok "pg_isready inside $PG_CONTAINER"
elif command -v pg_isready >/dev/null 2>&1 && pg_isready -h 127.0.0.1 -p "${POSTGRES_PORT:-5433}" -U "$PG_USER" >/dev/null 2>&1; then
  ok "pg_isready on host :${POSTGRES_PORT:-5433}"
else
  fail "Postgres unreachable ($PG_CONTAINER / :${POSTGRES_PORT:-5433})"
fi
echo

echo "--- containers ---"
for name in citevision-v2-postgres citevision-v2-redis citevision-v2-mosquitto citevision-v2-minio citevision-v2-mailhog citevision-v2-go2rtc; do
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
elif [[ "$FRIGATE_ST" == "missing" ]]; then
  warn "citevision-v2-frigate not present (compose --profile frigate?)"
else
  fail "citevision-v2-frigate status=$FRIGATE_ST"
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
      warn "Frigate cameras={} — backend compiler has not pushed cameras yet"
    elif [[ "$CAMS" == "err" ]]; then
      warn "could not parse Frigate /api/config"
    else
      ok "Frigate cameras count=$CAMS"
    fi
  else
    warn "Frigate /api/config empty/failed"
  fi
else
  fail "Frigate API unreachable at $FRIGATE_URL"
fi
echo

echo "--- go2rtc ---"
STREAMS_JSON="$(curl -sf --max-time 5 "$GO2RTC_URL/api/streams" || true)"
if [[ -z "$STREAMS_JSON" ]]; then
  fail "go2rtc API unreachable at $GO2RTC_URL"
else
  STREAMS="$(printf '%s' "$STREAMS_JSON" | json_len)"
  if [[ "$STREAMS" == "0" ]]; then
    warn "go2rtc streams_registered=0 — running ensure-demo-streams.sh"
    if [[ -f "$ROOT/scripts/ensure-demo-streams.sh" ]]; then
      bash "$ROOT/scripts/ensure-demo-streams.sh" || warn "ensure-demo-streams.sh exited non-zero"
      STREAMS2="$(curl -sf --max-time 5 "$GO2RTC_URL/api/streams" | json_len)"
      if [[ "$STREAMS2" == "0" ]]; then
        fail "go2rtc still streams_registered=0 after heal"
      else
        ok "go2rtc streams_registered=$STREAMS2 after heal"
      fi
    else
      fail "missing ensure-demo-streams.sh and streams=0"
    fi
  else
    ok "go2rtc streams_registered=$STREAMS"
  fi
fi
echo

echo "--- ai-engine ---"
UVICORN_N="$(pgrep -af 'uvicorn.*citevision|citevision_ai' 2>/dev/null | grep -vE 'grep|pgrep|health_check' | wc -l | tr -d ' ')"
UVICORN_N="${UVICORN_N:-0}"
if (( UVICORN_N > 1 )); then
  warn "multiple AI processes ($UVICORN_N) — restarting via scripts/_restart_ai.py"
  if [[ -f "$ROOT/scripts/_restart_ai.py" ]]; then
    python3 "$ROOT/scripts/_restart_ai.py" || warn "_restart_ai.py failed"
  fi
elif (( UVICORN_N == 0 )); then
  warn "no uvicorn citevision_ai process detected"
else
  ok "single AI process detected"
fi

HEALTH_RAW="$(curl -sS --max-time 5 -w '\n%{http_code}' "$AI_URL/health" 2>/dev/null || true)"
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
  fi
fi
echo

echo "--- backend ---"
if curl -sf --max-time 5 "$API_URL/health" >/dev/null 2>&1 || curl -sf --max-time 5 "$API_URL/api/v1/health" >/dev/null 2>&1; then
  ok "API reachable at $API_URL"
else
  warn "API not responding at $API_URL"
fi
echo

echo "--- ui ---"
if curl -sf --max-time 5 "$UI_URL/" >/dev/null 2>&1 || curl -sf --max-time 5 "$UI_URL/index.html" >/dev/null 2>&1; then
  ok "UI reachable at $UI_URL"
else
  warn "UI $UI_URL down — start Vite before visual validation"
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
