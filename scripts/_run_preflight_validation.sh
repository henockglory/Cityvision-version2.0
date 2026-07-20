#!/usr/bin/env bash
# Validation séquentielle avec preflight strict par règle.
set -uo pipefail
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
ROOT=~/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"

echo "=============================================="
echo " ÉTAPE 0 — Sync Windows -> WSL runtime"
echo "=============================================="
rsync -a "$WIN/backend/internal/" backend/internal/ --exclude .git
rsync -a "$WIN/ai-engine/src/" ai-engine/src/
rsync -a "$WIN/rules-engine/internal/actions/" rules-engine/internal/actions/
cp "$WIN/scripts/validate_demo_five_rules.py" scripts/
find backend/internal ai-engine/src scripts/validate_demo_five_rules.py -type f -exec sed -i 's/\r$//' {} + 2>/dev/null || true
grep -q '^DEMO_ORG_ID=' "$ENV_FILE" || echo 'DEMO_ORG_ID=74d51ead-97a7-4e41-a488-503a9b90c466' >>"$ENV_FILE"
sed -i 's/^DEFAULT_ORG_ID=.*/DEFAULT_ORG_ID=74d51ead-97a7-4e41-a488-503a9b90c466/' "$ENV_FILE" 2>/dev/null || true
echo "  sync OK"

echo ""
echo "=============================================="
echo " ÉTAPE 1 — Docker (postgres, go2rtc, frigate…)"
echo "=============================================="
if ! docker info >/dev/null 2>&1; then
  echo "  [FAIL] Docker daemon inaccessible — lancer Docker Desktop / service docker"
  exit 1
fi
if ! docker compose -f infra/docker-compose.yml --env-file "$ENV_FILE" up -d 2>&1 | tail -8; then
  echo "  [WARN] docker compose up partial"
fi
sleep 8
for c in citevision-v2-postgres citevision-v2-redis citevision-v2-minio \
         citevision-v2-mosquitto citevision-v2-go2rtc citevision-v2-frigate citevision-v2-mailhog; do
  if docker ps --format '{{.Names}}' | grep -qx "$c"; then
    echo "  [OK] $c running"
  else
    echo "  [FAIL] $c not running"
  fi
done
if ! curl -sf http://127.0.0.1:5433 >/dev/null 2>&1; then
  sleep 5
fi

echo ""
echo "=============================================="
echo " ÉTAPE 2 — Rebuild backend + rules-engine"
echo "=============================================="
(cd backend && go build -o bin/citevision-api ./cmd/api) && echo "  backend build OK"
(cd rules-engine && go build -o bin/rules-engine ./cmd/rules-engine) && echo "  rules-engine build OK"

stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
stop_from_pid "$LOGDIR/rules-engine.pid" 2>/dev/null || true
free_port 8081 2>/dev/null || true
free_port 8010 2>/dev/null || true
start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
start_bg rules-engine "$ROOT/rules-engine" "$ROOT/rules-engine/bin/rules-engine" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:8081/health" 90 || { tail -20 "$LOGDIR/backend.log"; exit 1; }
wait_http_ok "http://127.0.0.1:8010/health" 90 || { tail -20 "$LOGDIR/rules-engine.log"; exit 1; }
echo "  API + rules-engine UP"

echo ""
echo "=============================================="
echo " ÉTAPE 3 — Heal Frigate + demo streams"
echo "=============================================="
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST -H "X-Internal-Key: $KEY" "$BACKEND_API_URL/api/v1/internal/demo/repair-streams" && echo "  repair-streams OK" || echo "  repair-streams WARN"
curl -sf -X POST -H "X-Internal-Key: $KEY" "$BACKEND_API_URL/api/v1/internal/ingest/frigate/rebuild" && echo "  frigate rebuild OK" || echo "  frigate rebuild WARN"
if ! curl -sf http://127.0.0.1:5000/api/version >/dev/null 2>&1; then
  docker restart citevision-v2-frigate
  sleep 20
fi
curl -sf http://127.0.0.1:5000/api/version && echo "  Frigate API OK" || echo "  Frigate API FAIL"

echo ""
echo "=============================================="
echo " ÉTAPE 4 — AI engine (sans restart si healthy)"
echo "=============================================="
if curl -sf http://127.0.0.1:8001/health | grep -q '"yolo_loaded":"true"'; then
  echo "  AI déjà OK (skip restart)"
else
  bash scripts/restart-ai-engine.sh 2>&1 | tail -5
  sleep 10
fi
if ! curl -sf http://127.0.0.1:8001/health >/dev/null 2>&1; then
  echo "  AI down — restart forcé"
  bash scripts/restart-ai-engine.sh 2>&1 | tail -5
  sleep 12
fi
curl -sf http://127.0.0.1:8001/health | python3 -c "import sys,json; h=json.load(sys.stdin); print('  yolo',h.get('yolo_provider'),'frames_models',h.get('models_all_ok'))"

echo ""
echo "=============================================="
echo " ÉTAPE 5 — Validation (preflight strict / règle)"
echo "=============================================="
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"
export DEMO_ORG_ID="${DEMO_ORG_ID:-74d51ead-97a7-4e41-a488-503a9b90c466}"
export RULE_PREFLIGHT_STRICT=1
export DEMO_MIN_FRAMES=15
export DEMO_READY_TIMEOUT_SEC=180
export FRIGATE_EVENTS_WAIT_SEC=120
export DEMO_SETTLE_SEC=25
export ALERT_WAIT_SEC=240
export RULE_TIMEOUT_SEC=600
# Modifier VALIDATE_ONLY pour tester un sous-ensemble ou les 5 :
export VALIDATE_ONLY="${VALIDATE_ONLY:-Démo · Excès de vitesse,Démo · Téléphone au volant}"

LOG="$LOGDIR/validate-preflight-$(date +%Y%m%d-%H%M%S).log"
echo "  log -> $LOG"
python3 scripts/validate_demo_five_rules.py 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}

echo ""
echo "=============================================="
echo " RÉSUMÉ"
echo "=============================================="
grep -E 'PREFLIGHT:|^\s+\[(OK|FAIL)\]|PASS|FAIL|preflight_blocked|VALIDATION' "$LOG" | tail -40
exit "$RC"
