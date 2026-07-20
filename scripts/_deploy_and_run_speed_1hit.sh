#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

pkill -f '_validate_rule_frigate_1hit.py' 2>/dev/null || true

# Sync code
for f in \
  ai-engine/src/citevision_ai/evidence/service.py \
  ai-engine/src/citevision_ai/config.py \
  ai-engine/tests/test_speed_evidence_dedupe.py \
  scripts/_validate_rule_frigate_1hit.py
do
  cp -f "/mnt/c/Users/gheno/citevision/$f" "$ROOT/$f"
  sed -i 's/\r$//' "$ROOT/$f"
done

# Upsert align overrides in .env
upsert() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ROOT/.env"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ROOT/.env"
  else
    printf '%s=%s\n' "$key" "$val" >>"$ROOT/.env"
  fi
}
upsert FRIGATE_DEMO_MAX_ALIGN_SEC 10
upsert FRIGATE_DEMO_LOOSE_MATCH_SEC 10
upsert FRIGATE_DEMO_ACCEPT_MAX_ALIGN_SEC 10

python3 - <<'PY'
from pathlib import Path
p=Path("/home/gheno/citevision-v2/ai-engine/src/citevision_ai/evidence/service.py")
t=p.read_text()
assert "capture_retroactive" in t and "_begin_speed_evidence" in t
assert "FrameRingBuffer" in t
print("service OK")
PY

cd "$ROOT/ai-engine"
.venv/bin/python -m pytest tests/test_speed_evidence_dedupe.py -q
cd "$ROOT"

# Truncate AI log for clean signal
: > "$ROOT/logs/ai-engine.log"

bash scripts/restart-ai-engine.sh

# Backend/rules health
if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  GO_BIN=/usr/local/go/bin/go
  stop_from_pid "$ROOT/logs/backend.pid" 2>/dev/null || true
  free_port 8081
  (cd backend && "$GO_BIN" build -o bin/citevision-api ./cmd/api)
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ENV_FILE"
  wait_http_ok "http://127.0.0.1:8081/health" 90
fi
if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh
fi

# Frigate up + record
if ! curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null; then
  docker start citevision-v2-go2rtc citevision-v2-frigate || true
  docker restart citevision-v2-go2rtc citevision-v2-frigate
  sleep 30
fi
curl -sf -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true

python3 scripts/_reset_demo_password.py 'Hologram2026!'

export ADMIN_PASSWORD='Hologram2026!'
export RULE_NAME='Démo · Excès de vitesse'
export RULE_DURATION_SEC=600
export PYTHONUNBUFFERED=1
python3 scripts/_validate_rule_frigate_1hit.py
echo "EXIT=$?"

echo "=== post dedupe/frigate signals ==="
grep -c 'speed evidence dedupe skip' "$ROOT/logs/ai-engine.log" || true
grep -c 'frigate_track: bound\|frigate_track: demo\|capture_source' "$ROOT/logs/ai-engine.log" || true
grep -E 'frigate_track:|speed evidence|semaphore timeout' "$ROOT/logs/ai-engine.log" | tail -40
