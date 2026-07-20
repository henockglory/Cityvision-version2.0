#!/usr/bin/env bash
# Minimal stack for validation (backend must stay up even if ingest warn).
set -uo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
export PATH="$PATH:/usr/local/go/bin"
LOGDIR="$ROOT/logs"

docker start citevision-v2-postgres citevision-v2-redis citevision-v2-minio citevision-v2-mosquitto \
  citevision-v2-go2rtc citevision-v2-frigate citevision-v2-mailhog 2>/dev/null || true
sleep 3
if ! curl -sf http://127.0.0.1:5000/api/version >/dev/null 2>&1; then
  echo "=== restart Frigate (API down) ==="
  docker restart citevision-v2-frigate 2>/dev/null || true
  for i in $(seq 1 30); do
    curl -sf http://127.0.0.1:5000/api/version >/dev/null 2>&1 && break
    sleep 2
  done
fi
curl -sf http://127.0.0.1:5000/api/version && echo " frigate OK" || echo "WARN: frigate still down"

if ! curl -sf http://127.0.0.1:8081/health >/dev/null 2>&1; then
  echo "=== start backend ==="
  stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
  free_port 8081 2>/dev/null || true
  (cd backend && go build -o "$ROOT/backend/bin/citevision-api" ./cmd/api)
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok "http://127.0.0.1:8081/health" 90 || { tail -15 "$LOGDIR/backend.log"; exit 1; }
fi
echo "backend OK"

echo "=== demo pipeline (best effort) ==="
bash scripts/ensure-demo-pipeline.sh 2>&1 | tail -15 || true

KEY="${INTERNAL_API_KEY}"
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild || true
docker restart citevision-v2-frigate 2>/dev/null || true
for i in $(seq 1 25); do
  curl -sf http://127.0.0.1:5000/api/version >/dev/null 2>&1 && break
  sleep 2
done
curl -sf http://127.0.0.1:5000/api/version && echo " frigate OK" || echo "WARN: frigate still down"
sleep 15

curl -sf http://127.0.0.1:8001/cameras | python3 -c "
import sys,json
for c in json.load(sys.stdin).get('cameras',[]):
  print(c.get('camera_id','')[:8], 'frames', c.get('frames_processed',0))
" 2>/dev/null || echo "ai cameras unavailable"

rsync -a /mnt/c/Users/gheno/citevision/backend/ backend/ --exclude bin --exclude .git 2>/dev/null || true
rsync -a /mnt/c/Users/gheno/citevision/ai-engine/src/ ai-engine/src/ --exclude __pycache__ 2>/dev/null || true
cp /mnt/c/Users/gheno/citevision/scripts/validate_demo_five_rules.py scripts/ 2>/dev/null || true
cp /mnt/c/Users/gheno/citevision/scripts/_validate_speed_phone_run.py scripts/ 2>/dev/null || true
sed -i 's/\r$//' scripts/validate_demo_five_rules.py scripts/_validate_speed_phone_run.py backend/internal/handler/demo.go backend/internal/ingest/demo_heal.go 2>/dev/null || true

# Ensure Hologram org is default for demo validation [P.131]
grep -q '^DEMO_ORG_ID=' "$ENV_FILE" || echo 'DEMO_ORG_ID=74d51ead-97a7-4e41-a488-503a9b90c466' >>"$ENV_FILE"
sed -i 's/^DEFAULT_ORG_ID=.*/DEFAULT_ORG_ID=74d51ead-97a7-4e41-a488-503a9b90c466/' "$ENV_FILE" 2>/dev/null || true

echo "=== rebuild + restart backend (async demo heal) ==="
stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
free_port 8081 2>/dev/null || true
(cd backend && go build -o "$ROOT/backend/bin/citevision-api" ./cmd/api)
start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:8081/health" 90 || { tail -15 "$LOGDIR/backend.log"; exit 1; }

echo "=== restart AI engine ==="
bash scripts/restart-ai-engine.sh 2>&1 | tail -8 || true
sleep 8

export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"
export DEMO_ORG_ID="${DEMO_ORG_ID:-74d51ead-97a7-4e41-a488-503a9b90c466}"
export VALIDATE_ONLY="Démo · Excès de vitesse,Démo · Téléphone au volant"
export ALERT_WAIT_SEC=180
export DEMO_SETTLE_SEC=25
export DEMO_READY_TIMEOUT_SEC=120
export RULE_TIMEOUT_SEC=600

LOG="$LOGDIR/validate-speed-phone-$(date +%Y%m%d-%H%M%S).log"
echo "=== VALIDATE -> $LOG ==="
python3 scripts/validate_demo_five_rules.py 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
grep -E 'Excès|Téléphone|PASS|FAIL|VALIDATION' "$LOG" | tail -10
exit "$RC"
