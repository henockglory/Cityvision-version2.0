#!/usr/bin/env bash
set -uo pipefail
ROOT=~/citevision-v2
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"

rsync -a /mnt/c/Users/gheno/citevision/ai-engine/src/ ai-engine/src/
rsync -a /mnt/c/Users/gheno/citevision/backend/internal/ingest/ backend/internal/ingest/
rsync -a /mnt/c/Users/gheno/citevision/backend/internal/handler/demo.go backend/internal/handler/
cp /mnt/c/Users/gheno/citevision/rules-engine/internal/actions/executor.go rules-engine/internal/actions/
cp /mnt/c/Users/gheno/citevision/scripts/validate_demo_five_rules.py scripts/
find ai-engine/src backend/internal scripts/validate_demo_five_rules.py -type f -exec sed -i 's/\r$//' {} +

(cd backend && go build -o bin/citevision-api ./cmd/api)
(cd rules-engine && go build -o bin/rules-engine ./cmd/rules-engine)

stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
stop_from_pid "$LOGDIR/rules-engine.pid" 2>/dev/null || true
free_port 8081 2>/dev/null || true
free_port 8010 2>/dev/null || true
start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
start_bg rules-engine "$ROOT/rules-engine" "$ROOT/rules-engine/bin/rules-engine" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:8081/health" 60
wait_http_ok "http://127.0.0.1:8010/health" 60

KEY="${INTERNAL_API_KEY}"
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild || true
docker restart citevision-v2-frigate >/dev/null 2>&1 || true
sleep 20

bash scripts/restart-ai-engine.sh 2>&1 | tail -3
sleep 8

export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"
export DEMO_ORG_ID=74d51ead-97a7-4e41-a488-503a9b90c466
export VALIDATE_ONLY="Démo · Excès de vitesse,Démo · Téléphone au volant"
export DEMO_MIN_FRAMES=10
export DEMO_READY_TIMEOUT_SEC=180
export FRIGATE_EVENTS_WAIT_SEC=120
export ALERT_WAIT_SEC=240
export RULE_TIMEOUT_SEC=600

LOG="$LOGDIR/validate-speed-phone-v2-$(date +%Y%m%d-%H%M%S).log"
python3 scripts/validate_demo_five_rules.py 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
grep -E 'Excès|Téléphone|PASS|FAIL|VALIDATION|frigate|alerts=' "$LOG" | tail -25
exit "$RC"
