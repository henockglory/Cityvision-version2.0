#!/usr/bin/env bash
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
DEST=~/citevision-v2

echo "=== Sync Windows -> WSL ==="
rsync -a \
  --exclude node_modules \
  --exclude .git \
  --exclude frontend/dist \
  --exclude 'ai-engine/.venv' \
  --exclude 'infra/data/videos' \
  "$WIN/" "$DEST/"

find "$DEST/backend" "$DEST/ai-engine" "$DEST/scripts" "$DEST/frontend/src" "$DEST/shared" \
  -type f \( -name '*.go' -o -name '*.py' -o -name '*.sh' -o -name '*.ts' -o -name '*.tsx' -o -name '*.json' \) \
  -exec sed -i 's/\r$//' {} + 2>/dev/null || true

echo "=== Build backend ==="
export PATH="$PATH:/usr/local/go/bin"
mkdir -p "$DEST/backend/bin"
(cd "$DEST/backend" && go build -o "$DEST/backend/bin/citevision-api" ./cmd/api)

ROOT="$DEST"
source "$ROOT/scripts/lib/env-utils.sh"
LOGDIR="$ROOT/logs"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

echo "=== Restart backend (required before AI pipeline) ==="
stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
free_port "${API_PORT:-8081}" 2>/dev/null || true
sleep 1
start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:${API_PORT:-8081}/health" 90

echo "=== Restart AI engine + rules-engine ==="
AI_PORT="${AI_ENGINE_PORT:-8001}"
stop_from_pid "$LOGDIR/ai-engine.pid" 2>/dev/null || true
pkill -f 'uvicorn citevision_ai.main' 2>/dev/null || true
free_port "$AI_PORT" 2>/dev/null || true
sleep 2
bash "$ROOT/scripts/ensure-demo-pipeline.sh"

echo "=== Restart frontend ==="
stop_from_pid "$LOGDIR/frontend.pid" 2>/dev/null || true
pkill -f 'vite.*5174' 2>/dev/null || true
free_port 5174 5175 5176 5177 2>/dev/null || true
sleep 1
start_bg frontend "$ROOT/frontend" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:5174/" 90

echo "=== Patch speeding rules in DB ==="
if command -v psql >/dev/null 2>&1 && [[ -n "${DATABASE_URL:-}" ]]; then
  psql "$DATABASE_URL" -f "$ROOT/scripts/patch_speed_rules_live.sql" && echo "[OK] SQL patch applied"
elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q citevision-v2-postgres; then
  docker exec -i citevision-v2-postgres psql -U citevision -d citevision \
    < "$ROOT/scripts/patch_speed_rules_live.sql" && echo "[OK] SQL patch applied (docker)"
else
  echo "[WARN] psql unavailable — run patch_speed_rules_live.sql manually"
fi

echo "=== Resync ingest ==="
curl -sf -X POST "http://127.0.0.1:${API_PORT:-8081}/api/v1/internal/resync-spatial" \
  -H "X-Internal-Key: ${INTERNAL_API_KEY:-changeme_internal_service_key}" >/dev/null 2>&1 || true
sleep 5

echo "=== Validate chain ==="
LIVE_AUDIT=1 AUDIT_DEPLOY_ONLY=1 RULE_PAUSED=1 "$ROOT/ai-engine/.venv/bin/python3" "$ROOT/scripts/validate_speed_evidence_chain.py"

echo "[OK] Deploy complete — http://localhost:5174 (Ctrl+Shift+R)"
echo "[INFO] Réactivez votre règle vitesse copie puis surveillez les nouvelles alertes."
