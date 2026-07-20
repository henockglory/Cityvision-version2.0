#!/usr/bin/env bash
# Full speed+phone validation with async demo heal + Frigate gate.
set -uo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
export PATH="$PATH:/usr/local/go/bin"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"

# Sync from Windows editor
rsync -a /mnt/c/Users/gheno/citevision/backend/ backend/ --exclude bin --exclude .git
rsync -a /mnt/c/Users/gheno/citevision/ai-engine/src/ ai-engine/src/
cp /mnt/c/Users/gheno/citevision/scripts/validate_demo_five_rules.py scripts/
cp /mnt/c/Users/gheno/citevision/scripts/_validate_speed_phone_wsl.sh scripts/
cp /mnt/c/Users/gheno/citevision/scripts/_heal_frigate_now.sh scripts/ 2>/dev/null || true
find backend scripts/validate_demo_five_rules.py -type f -exec sed -i 's/\r$//' {} +

grep -q '^DEMO_ORG_ID=' "$ENV_FILE" || echo 'DEMO_ORG_ID=74d51ead-97a7-4e41-a488-503a9b90c466' >>"$ENV_FILE"
sed -i 's/^DEFAULT_ORG_ID=.*/DEFAULT_ORG_ID=74d51ead-97a7-4e41-a488-503a9b90c466/' "$ENV_FILE"

docker start citevision-v2-postgres citevision-v2-redis citevision-v2-minio citevision-v2-mosquitto \
  citevision-v2-go2rtc citevision-v2-frigate citevision-v2-mailhog 2>/dev/null || true

echo "=== rebuild backend ==="
stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
free_port 8081 2>/dev/null || true
(cd backend && go build -o "$ROOT/backend/bin/citevision-api" ./cmd/api)
(cd rules-engine && go build -o "$ROOT/rules-engine/bin/rules-engine" ./cmd/rules-engine)
start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:8081/health" 90

echo "=== heal frigate ==="
bash scripts/_heal_frigate_now.sh || true

echo "=== restart AI (only if unhealthy) ==="
if curl -sf http://127.0.0.1:8001/health >/dev/null 2>&1; then
  echo "AI already up — skip restart"
else
  bash scripts/restart-ai-engine.sh 2>&1 | tail -5
  sleep 10
fi
sleep 5
curl -sf http://127.0.0.1:8081/health && echo " backend ready"
curl -sf http://127.0.0.1:8001/health && echo " ai ready"

export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"
export DEMO_ORG_ID="${DEMO_ORG_ID:-74d51ead-97a7-4e41-a488-503a9b90c466}"
export VALIDATE_ONLY="Démo · Excès de vitesse,Démo · Téléphone au volant"
export ALERT_WAIT_SEC=180
export DEMO_SETTLE_SEC=30
export DEMO_READY_TIMEOUT_SEC=150
export FRIGATE_EVENTS_WAIT_SEC=120
export DEMO_MIN_FRAMES=15
export RULE_TIMEOUT_SEC=600

LOG="$LOGDIR/validate-speed-phone-final-$(date +%Y%m%d-%H%M%S).log"
echo "=== VALIDATE -> $LOG ==="
python3 scripts/validate_demo_five_rules.py 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
grep -E 'Excès|Téléphone|PASS|FAIL|VALIDATION|frigate|alerts=' "$LOG" | tail -20
exit "$RC"
