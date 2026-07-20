#!/usr/bin/env bash
# Validation 5 règles démo avec preflight complet avant CHAQUE test.
# Docker natif WSL uniquement — ne pas utiliser Docker Desktop.
set -uo pipefail
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
ROOT=~/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"
mkdir -p "$LOGDIR"

echo "=============================================="
echo " ÉTAPE 0 — Sync code Windows -> WSL runtime"
echo "=============================================="
rsync -a /mnt/c/Users/gheno/citevision/scripts/validate_demo_five_rules.py scripts/
rsync -a /mnt/c/Users/gheno/citevision/ai-engine/src/ ai-engine/src/
rsync -a /mnt/c/Users/gheno/citevision/backend/internal/ backend/internal/
rsync -a /mnt/c/Users/gheno/citevision/rules-engine/internal/ rules-engine/internal/
rsync -a /mnt/c/Users/gheno/citevision/rules-engine/cmd/ rules-engine/cmd/
sed -i 's/\r$//' scripts/validate_demo_five_rules.py
find rules-engine/internal rules-engine/cmd -name '*.go' -exec sed -i 's/\r$//' {} +

grep -q '^DEMO_ORG_ID=' "$ENV_FILE" || echo 'DEMO_ORG_ID=74d51ead-97a7-4e41-a488-503a9b90c466' >>"$ENV_FILE"
sed -i 's/^DEFAULT_ORG_ID=.*/DEFAULT_ORG_ID=74d51ead-97a7-4e41-a488-503a9b90c466/' "$ENV_FILE" 2>/dev/null || true

echo ""
echo "=============================================="
echo " ÉTAPE 1 — Docker WSL natif (Engine, pas Desktop)"
echo "=============================================="
if ! ensure_docker_ready 120; then
  echo "[FAIL] Docker Engine natif WSL — voir logs/dockerd.log"
  exit 1
fi
for c in citevision-v2-postgres citevision-v2-redis citevision-v2-minio \
         citevision-v2-mosquitto citevision-v2-go2rtc citevision-v2-frigate citevision-v2-mailhog; do
  docker start "$c" 2>/dev/null || true
  state=$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null || echo false)
  if [ "$state" = "true" ]; then
    echo "  [OK] $c"
  else
    echo "  [FAIL] $c not running"
  fi
done
sleep 3

echo ""
echo "=============================================="
echo " ÉTAPE 2 — Backend + rules-engine + AI engine"
echo "=============================================="
# Always rebuild + restart backend after code rsync so handler/evidence changes take effect.
echo "  [rebuild] backend (force reload du code après rsync)…"
stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
free_port 8081 2>/dev/null || true
(cd backend && sed -i 's/\r$//' $(find internal cmd -name '*.go') 2>/dev/null || true && go build -o bin/citevision-api ./cmd/api)
start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:8081/health" 90 || { echo "[FAIL] backend"; exit 1; }
echo "  [OK] backend :8081 (code frais)"

# Always restart rules-engine after code rsync to reload executor.go changes.
echo "  [restart] rules-engine (force reload du code après rsync)…"
bash scripts/_start-rules-engine.sh 2>/dev/null || true
wait_http_ok "http://127.0.0.1:8010/health" 60 || { echo "[FAIL] rules-engine"; exit 1; }
echo "  [OK] rules-engine :8010 (code frais)"

# Always restart AI after code rsync so new Python code is loaded in memory.
echo "  [restart] AI engine (force reload du code après rsync)…"
bash scripts/restart-ai-engine.sh
wait_http_ok "http://127.0.0.1:8001/health" 180 || { echo "[FAIL] AI engine"; exit 1; }
echo "  [OK] AI engine :8001 (code frais)"

echo ""
echo "=============================================="
echo " ÉTAPE 3 — Frigate + streams (sans restart AI si OK)"
echo "=============================================="
export INTERNAL_API_KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST -H "X-Internal-Key: $INTERNAL_API_KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true
curl -sf -X POST -H "X-Internal-Key: $INTERNAL_API_KEY" http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial || true
# Restart Frigate ONLY if its API is actually down — unconditional restarts disrupt AI RTSP workers
if ! curl -sf --max-time 5 http://127.0.0.1:5000/api/version >/dev/null 2>&1; then
  echo "  [heal] Frigate API down — rebuild + restart"
  curl -sf -X POST -H "X-Internal-Key: $INTERNAL_API_KEY" http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild || true
  docker restart citevision-v2-frigate >/dev/null 2>&1 || true
  for i in $(seq 1 30); do
    curl -sf http://127.0.0.1:5000/api/version >/dev/null 2>&1 && break
    sleep 2
  done
  sleep 20
fi
curl -sf http://127.0.0.1:5000/api/version && echo "  [OK] Frigate API" || echo "  [WARN] Frigate API down"
sleep 10

echo ""
echo " ÉTAPE 3b — Vérification santé avant validation"
wait_http_ok "http://127.0.0.1:8081/health" 30 || {
  echo "  [heal] backend down — redémarrage"
  stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
  free_port 8081 2>/dev/null || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok "http://127.0.0.1:8081/health" 60 || exit 1
}
wait_http_ok "http://127.0.0.1:8001/health" 60 || { echo "  [FAIL] AI engine not responding after 60s"; exit 1; }
wait_http_ok "http://127.0.0.1:8010/health" 30 || { echo "  [FAIL] rules-engine not responding"; exit 1; }
echo "  [OK] backend + AI + rules-engine confirmés"

echo ""
echo "=============================================="
echo " ÉTAPE 4 — Validation (preflight par règle)"
echo "=============================================="
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Hologram2026!}"
export DEMO_ORG_ID="${DEMO_ORG_ID:-74d51ead-97a7-4e41-a488-503a9b90c466}"
export RULE_PREFLIGHT_STRICT=1
export DEMO_MIN_FRAMES=12
export DEMO_READY_TIMEOUT_SEC=240
export FRIGATE_EVENTS_WAIT_SEC=120
export DEMO_SETTLE_SEC=25
export ALERT_WAIT_SEC=240
export RULE_TIMEOUT_SEC=600
export REPORT_TAG=gated

# Par défaut les 5 règles ; override: VALIDATE_ONLY="Démo · Excès de vitesse,..."
LOG="$LOGDIR/demo-five-rules-gated-$(date +%Y%m%d-%H%M%S).log"
echo "Log: $LOG"
python3 scripts/validate_demo_five_rules.py 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}

echo ""
echo "=============================================="
echo " RÉSUMÉ"
echo "=============================================="
grep -E '^\--- PREFLIGHT|PREFLIGHT OK|PREFLIGHT BLOCKED|^=== Démo|PASS|FAIL|preflight_blocked|VALIDATION' "$LOG" | tail -40
exit "$RC"
