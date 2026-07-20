#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
cp -f "$WIN/scripts/_validate_rule_frigate_1hit.py" "$ROOT/scripts/_validate_rule_frigate_1hit.py"
sed -i 's/\r$//' "$ROOT/scripts/_validate_rule_frigate_1hit.py"

curl -sf http://127.0.0.1:8081/health >/dev/null
curl -sf http://127.0.0.1:8001/health >/dev/null
curl -sf http://127.0.0.1:5000/api/version >/dev/null
echo "stack ok"

# Ensure AI picks up accept_max=30 if process was started with old env — restart AI lightly
# Only if needed: check running settings via a quick capture is overkill; restart AI.
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
: > "$ROOT/logs/ai-engine.log"
bash scripts/restart-ai-engine.sh
for i in $(seq 1 40); do curl -sf http://127.0.0.1:8001/health >/dev/null && break; sleep 2; done
if ! curl -sf http://127.0.0.1:8081/health >/dev/null; then
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90
fi
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true

python3 scripts/_reset_demo_password.py 'Hologram2026!' || true

export ADMIN_PASSWORD='Hologram2026!'
export RULE_NAME='Démo · Feu rouge'
export RULE_DURATION_SEC=600
export SKIP_FRIGATE_REBUILD=1
export FRIGATE_MAX_ALIGN_MS=30000
export PYTHONUNBUFFERED=1
python3 scripts/_validate_rule_frigate_1hit.py
echo "VALIDATE_EXIT=$?"
