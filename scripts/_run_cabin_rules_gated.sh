#!/usr/bin/env bash
# Re-test ceinture + téléphone (caméra cabine f691) avec heal ingest.
set -uo pipefail
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
ROOT=~/citevision-v2
cd "$ROOT"
export PROJECT_ROOT="$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"

echo "=== Sync validate script ==="
cp /mnt/c/Users/gheno/citevision/scripts/validate_demo_five_rules.py scripts/
sed -i 's/\r$//' scripts/validate_demo_five_rules.py

ensure_docker_ready 90 || exit 1
for c in citevision-v2-postgres citevision-v2-redis citevision-v2-minio \
         citevision-v2-mosquitto citevision-v2-go2rtc citevision-v2-frigate citevision-v2-mailhog; do
  docker start "$c" 2>/dev/null || true
done

curl -sf http://127.0.0.1:8081/health >/dev/null || {
  stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok "http://127.0.0.1:8081/health" 60
}
curl -sf http://127.0.0.1:8010/health >/dev/null || {
  (cd rules-engine && go build -o bin/rules-engine ./cmd/rules-engine)
  start_bg rules-engine "$ROOT/rules-engine" "$ROOT/rules-engine/bin/rules-engine" "$LOGDIR" "$ENV_FILE"
}
curl -sf http://127.0.0.1:8001/health >/dev/null || bash scripts/restart-ai-engine.sh

export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"
export DEMO_ORG_ID=74d51ead-97a7-4e41-a488-503a9b90c466
export VALIDATE_ONLY="Démo · Non-port ceinture,Démo · Téléphone au volant"
export RULE_PREFLIGHT_STRICT=1
export DEMO_MIN_FRAMES_CABIN=6
export DEMO_READY_TIMEOUT_SEC_CABIN=420
export FRIGATE_EVENTS_WAIT_SEC=120
export INTERNAL_API_KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
export REPORT_TAG=cabin-retest

LOG="$LOGDIR/cabin-retest-$(date +%Y%m%d-%H%M%S).log"
echo "Log: $LOG"
python3 scripts/validate_demo_five_rules.py 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
grep -E 'PREFLIGHT|ceinture|Téléphone|PASS|FAIL|heal-ingest|VALIDATION' "$LOG" | tail -30
exit "$RC"
