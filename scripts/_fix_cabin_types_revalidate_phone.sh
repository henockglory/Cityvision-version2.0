#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
# Stop validators
pkill -f '_validate_all_5b' 2>/dev/null || true
pkill -f 'validate_rule_dod' 2>/dev/null || true
pkill -f '_validate_rule_frigate_1hit' 2>/dev/null || true

# Sync service.py cabin types
cp -f /mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/service.py \
  "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"
sed -i 's/\r$//' "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"
grep -n 'phone_driving\|driver_phone\|seatbelt"' "$ROOT/ai-engine/src/citevision_ai/evidence/service.py" | head -10

# Restart AI to pick up cabin types
python3 "$ROOT/scripts/_restart_ai.py" || true

source "$ROOT/scripts/lib/env-utils.sh"
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial -H "X-Internal-Key: $KEY"; echo

# Quick phone-only validate
export RULE_DURATION_SEC=300
export VALIDATE_MODE=wait
bash "$ROOT/scripts/validate_rule.sh" phone 2>&1 | tee "$ROOT/logs/validate-phone-cabin-fix.log" | tail -80
