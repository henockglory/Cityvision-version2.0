#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
source "$ROOT/scripts/lib/env-utils.sh"
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

curl -sf http://127.0.0.1:8081/health || bash "$ROOT/scripts/_restart_backend.sh"
curl -sf http://127.0.0.1:8010/health || bash "$ROOT/scripts/_start-rules-engine.sh"
curl -sf http://127.0.0.1:5174/ >/dev/null || {
  cd "$ROOT/frontend"
  nohup npm run dev -- --host 127.0.0.1 --port 5174 >/tmp/citevision-vite.log 2>&1 &
  sleep 3
}

curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial -H "X-Internal-Key: $KEY" || true
echo
sleep 8
curl -sS http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
for c in json.load(sys.stdin).get("cameras") or []:
  print(c.get("camera_id")[:8], "fr", c.get("frames_read"), "fp", c.get("frames_processed"))
'

# Confirm cabin types loaded in running process via a quick import check in venv
"$ROOT/ai-engine/.venv/bin/python" -c '
from citevision_ai.evidence.service import EvidenceCaptureService
print("cabin", sorted(EvidenceCaptureService._CABIN_EVENT_TYPES))
'

export RULE_DURATION_SEC=360
export VALIDATE_MODE=wait
bash "$ROOT/scripts/validate_rule.sh" phone
ec=$?
echo EXIT=$ec
find "$ROOT/validation-evidence/phone" -name report.json | sort | tail -3 | while read -r f; do
  python3 -c "import json;d=json.load(open('$f'));print('$f', d.get('result'))"
done
