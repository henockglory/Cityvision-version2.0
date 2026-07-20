#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

# Ensure OCR_URL
grep '^OCR_URL=' .env || echo 'OCR_URL=http://127.0.0.1:8181/ocr' >> .env
sed -i 's|^OCR_URL=.*|OCR_URL=http://127.0.0.1:8181/ocr|' .env

pkill -f 'validate_rule_dod\|1hit\|validate_speeding' 2>/dev/null || true

python3 scripts/_restart_ai.py
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial -H "X-Internal-Key: $KEY" || true
echo

# Vite
if ! curl -sf --max-time 2 http://127.0.0.1:5174/ >/dev/null; then
  cd frontend
  nohup npm run dev -- --host 127.0.0.1 --port 5174 > /tmp/citevision-vite.log 2>&1 &
  sleep 4
  cd "$ROOT"
fi

# Wait ingest
for i in $(seq 1 20); do
  fr=$(curl -sS http://127.0.0.1:8001/cameras | python3 -c 'import json,sys;d=json.load(sys.stdin);print(sum(int(c.get("frames_read")or 0)for c in (d.get("cameras")or[])))' 2>/dev/null || echo 0)
  echo "frames=$fr"
  [[ "${fr:-0}" -ge 50 ]] && break
  sleep 3
done

# Probe plate
CAM=55694d53-8f58-4981-91b2-7c6cd528a25d
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
curl -sS -X POST "http://127.0.0.1:8001/cameras/$CAM/evidence/capture" \
  -H 'Content-Type: application/json' \
  -d "{\"org_id\":\"$ORG\",\"event\":{\"event_type\":\"speeding\",\"event_id\":\"ocr2-$(date +%s)\",\"camera_id\":\"$CAM\",\"confidence\":0.9,\"bbox\":{\"x\":0.4,\"y\":0.3,\"width\":0.2,\"height\":0.25},\"bbox_ts\":$(date +%s)}}" \
  -o /tmp/cap_ocr2.json -w "http=%{http_code}\n"
python3 - <<'PY'
import json
d=json.load(open("/tmp/cap_ocr2.json"))
pkg=d.get("package") or {}
meta=pkg.get("metadata") or {}
print("status", d.get("evidence_status"), "missing", meta.get("missing_roles"), "plate_status", meta.get("plate_status"))
print("roles", [i.get("role") for i in (pkg.get("images") or [])])
print("plate_number", meta.get("plate_number"), "ocr", meta.get("plate_ocr_source"))
PY

export RULE_DURATION_SEC=480
export VALIDATE_MODE=wait
export SKIP_FRIGATE_REBUILD=1
bash scripts/validate_rule.sh speeding
echo EXIT=$?
latest=$(find validation-evidence/speeding -name report.json | sort | tail -1)
python3 -c "import json;d=json.load(open('$latest'));print('result',d.get('result'));
[print(c['id'], c['ok'], str(c.get('detail',''))[:100]) for c in (d.get('checks') or [])]"
ls -la "$(dirname "$latest")/ui.png" 2>/dev/null || echo no_ui
