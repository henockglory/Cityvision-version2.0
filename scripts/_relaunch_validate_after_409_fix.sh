#!/usr/bin/env bash
# Sync critical E2E fixes, rebuild backend, relaunch gated validation (no full docker restart if healthy).
set -euo pipefail
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
ROOT=~/citevision-v2
cd "$ROOT"
SRC=/mnt/c/Users/gheno/citevision

rsync -a "$SRC/backend/internal/handler/" backend/internal/handler/
rsync -a "$SRC/scripts/validate_demo_five_rules.py" scripts/validate_demo_five_rules.py
find backend/internal/handler -name '*.go' -exec sed -i 's/\r$//' {} +
sed -i 's/\r$//' scripts/validate_demo_five_rules.py scripts/_run_five_rules_gated.sh

source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"

# Ensure Frigate absolute paths stay set
grep -q '^FRIGATE_BASE_YAML=' "$ENV_FILE" || echo "FRIGATE_BASE_YAML=$ROOT/infra/frigate.base.yaml" >>"$ENV_FILE"
grep -q '^FRIGATE_ENABLED=1' "$ENV_FILE" || sed -i 's|^FRIGATE_ENABLED=.*|FRIGATE_ENABLED=1|' "$ENV_FILE"

echo "=== rebuild+restart backend ==="
stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
free_port 8081 2>/dev/null || true
(cd backend && go build -o bin/citevision-api ./cmd/api)
start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:8081/health" 90

wait_http_ok "http://127.0.0.1:8001/health" 60 || bash scripts/restart-ai-engine.sh
wait_http_ok "http://127.0.0.1:8010/health" 30 || bash scripts/_start-rules-engine.sh

# Confirm Frigate still has cameras
n=$(curl -sf --max-time 8 http://127.0.0.1:5000/api/stats | python3 -c 'import sys,json; print(len((json.load(sys.stdin).get("cameras") or {})))')
echo "frigate cameras=$n"
if [ "${n:-0}" -lt 1 ]; then
  KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
  curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild
  docker restart citevision-v2-frigate >/dev/null
  sleep 35
fi

export DEMO_MODE=1 DEMO_EVIDENCE_BACKEND=strict_frigate DEMO_RESOLUTION=1080p
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"
export RULE_PREFLIGHT_STRICT=1
export DEMO_MIN_FRAMES=12
export DEMO_READY_TIMEOUT_SEC=240
export FRIGATE_EVENTS_WAIT_SEC=120
export DEMO_SETTLE_SEC=25
export ALERT_WAIT_SEC=240
export RULE_TIMEOUT_SEC=600
export REPORT_TAG=gated

STAMP=$(date +%Y%m%d-%H%M%S)
LOG="$LOGDIR/demo-five-rules-gated-${STAMP}.log"
OUTER="$LOGDIR/demo-five-rules-gated-manual-${STAMP}.outer.log"
echo "Log: $LOG"
echo "OUTER: $OUTER"
nohup python3 scripts/validate_demo_five_rules.py >"$LOG" 2>&1 &
PID=$!
echo "$PID" >"$LOGDIR/validate-demo.pid"
echo "PID=$PID"
# also mirror to outer for tracking
(
  echo "started validate PID=$PID"
  tail -f "$LOG" &
  TP=$!
  wait "$PID"
  RC=$?
  kill "$TP" 2>/dev/null || true
  echo "exit=$RC"
  exit "$RC"
) >"$OUTER" 2>&1 &
echo "STATUS=running"
