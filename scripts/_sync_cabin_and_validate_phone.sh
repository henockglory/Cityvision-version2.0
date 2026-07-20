#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision

pkill -f '_validate_all' 2>/dev/null || true
pkill -f 'validate_rule_dod' 2>/dev/null || true
pkill -f '_validate_rule_frigate_1hit' 2>/dev/null || true

cp -f "$WIN/ai-engine/src/citevision_ai/evidence/service.py" \
  "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"
cp -f "$WIN/scripts/_validate_rule_frigate_1hit.py" "$ROOT/scripts/"
sed -i 's/\r$//' "$ROOT/ai-engine/src/citevision_ai/evidence/service.py" \
  "$ROOT/scripts/_validate_rule_frigate_1hit.py"

echo "cabin types:"
sed -n '240,250p' "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"

echo "restart AI..."
python3 "$ROOT/scripts/_restart_ai.py"

source "$ROOT/scripts/lib/env-utils.sh"
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial -H "X-Internal-Key: $KEY"; echo

# Wait for frames on any cam
for i in $(seq 1 20); do
  fr=$(curl -sS http://127.0.0.1:8001/cameras | python3 -c 'import json,sys;d=json.load(sys.stdin);print(sum(int(c.get("frames_read")or 0)for c in (d.get("cameras")or[])))')
  echo "frames=$fr"
  [[ "${fr:-0}" -ge 30 ]] && break
  sleep 3
done

export RULE_DURATION_SEC=360
export VALIDATE_MODE=wait
echo "=== validate phone ==="
bash "$ROOT/scripts/validate_rule.sh" phone
echo "EXIT=$?"
find "$ROOT/validation-evidence/phone" -name report.json | sort | tail -2 | while read -r f; do
  python3 -c "import json;d=json.load(open('$f'));print('$f', d.get('result'));
[print(' ',c['id'], c['ok'], str(c.get('detail',''))[:100]) for c in (d.get('checks') or [])]"
done
