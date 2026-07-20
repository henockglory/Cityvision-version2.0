#!/usr/bin/env bash
# DoD validation sequence — run on WSL ~/citevision-v2
set -euo pipefail
ROOT=~/citevision-v2
cd "$ROOT"
export PATH="$PATH:/usr/local/go/bin"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

LOG="$ROOT/logs/dod-validation-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=== DoD VALIDATION $(date -Iseconds) ==="

echo "=== 1. Docker infra (go2rtc, mailhog, frigate) ==="
docker compose -f infra/docker-compose.yml --env-file "$ENV_FILE" up -d go2rtc mailhog postgres redis mosquitto minio 2>&1 | tail -8
docker compose -f infra/docker-compose.yml --env-file "$ENV_FILE" --profile frigate up -d frigate 2>&1 | tail -5
sleep 15
wait_http_ok "http://127.0.0.1:1984/api" 60 || echo "[WARN] go2rtc slow"
wait_http_ok "http://127.0.0.1:5000/api/version" 90 || echo "[WARN] frigate slow"

echo "=== 2. Frigate config rebuild ==="
curl -sf -X POST -H "X-Internal-Key: ${INTERNAL_API_KEY}" \
  http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild || echo "[WARN] frigate rebuild"

echo "=== 3. Platform health ==="
curl -sf http://127.0.0.1:8081/health/platform | python3 -m json.tool | head -30

echo "=== 4. Preflight ==="
bash scripts/preflight_platform.sh || PREFLIGHT_FAIL=1

echo "=== 5. Inject faults smoke ==="
bash scripts/inject_faults_test.sh || FAULTS_FAIL=1

echo "=== 6. Five rules métier (may take 30+ min) ==="
python3 scripts/validate_demo_five_rules.py || FIVE_FAIL=1

echo "=== 7. Frigate 3 rules x3 runs (may take 60+ min) ==="
VALIDATE_CONSECUTIVE_RUNS=1 bash scripts/_run_validate_now.sh || FRIGATE_FAIL=1

echo "=== SUMMARY ==="
echo "preflight=${PREFLIGHT_FAIL:-0} faults=${FAULTS_FAIL:-0} five=${FIVE_FAIL:-0} frigate=${FRIGATE_FAIL:-0}"
echo "Log: $LOG"
