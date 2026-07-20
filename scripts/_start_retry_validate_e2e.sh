#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
pkill -f validate_demo_five_rules.py 2>/dev/null || true
pkill -f _retry_failed_demo_rules 2>/dev/null || true
sleep 1
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"

stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
free_port 8081 2>/dev/null || true
(cd backend && go build -o bin/citevision-api ./cmd/api)
start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:8081/health" 90
echo -n "backend: "; curl -sf http://127.0.0.1:8081/health; echo

if ! curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
  bash scripts/restart-ai-engine.sh
  wait_http_ok "http://127.0.0.1:8001/health" 180
fi
echo "AI ok"

if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh
  wait_http_ok "http://127.0.0.1:8010/health" 60
fi
echo -n "rules: "; curl -sf http://127.0.0.1:8010/health; echo

export DEMO_MODE=1
export DEMO_EVIDENCE_BACKEND=strict_frigate
export DEMO_RESOLUTION=1080p
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"
export RULE_PREFLIGHT_STRICT=1
export DEMO_MIN_FRAMES=12
export DEMO_READY_TIMEOUT_SEC=240
export FRIGATE_EVENTS_WAIT_SEC=90
export DEMO_SETTLE_SEC=20
export ALERT_WAIT_SEC=240
export RULE_TIMEOUT_SEC=480
export TARGET_DETECTIONS=1
export REPORT_TAG=gated-retry
export VALIDATE_ONLY='Démo · Excès de vitesse,Démo · Feu rouge,Démo · Comptage véhicules'

STAMP=$(date +%Y%m%d-%H%M%S)
LOG="$LOGDIR/demo-five-rules-retry-${STAMP}.log"
echo "START validate LOG=$LOG"
nohup python3 scripts/validate_demo_five_rules.py >"$LOG" 2>&1 &
echo $! >"$LOGDIR/validate-retry.pid"
echo "PID=$(cat "$LOGDIR/validate-retry.pid")"
sleep 3
head -20 "$LOG" || true
