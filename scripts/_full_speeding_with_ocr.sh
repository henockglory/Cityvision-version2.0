#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

bash scripts/_restart_backend.sh
bash scripts/_start-rules-engine.sh
curl -sf http://127.0.0.1:8181/healthz || {
  cd infra
  docker compose --env-file "$ROOT/.env" --profile ocr up -d citevision-ocr
  sleep 10
  cd "$ROOT"
}
curl -sf http://127.0.0.1:8001/health >/dev/null || python3 scripts/_restart_ai.py

source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

# Confirm OCR reachable from host + AI env
echo "OCR=$(curl -sf http://127.0.0.1:8181/healthz)"
grep OCR_URL .env

# Restart AI once more so OCR_URL is loaded (env from .env via run-ai-engine)
python3 scripts/_restart_ai.py

curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial -H "X-Internal-Key: $KEY"; echo
sleep 8
curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial -H "X-Internal-Key: $KEY"; echo

for i in $(seq 1 24); do
  out=$(curl -sS http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
cams=json.load(sys.stdin).get("cameras") or []
fr=sum(int(c.get("frames_read") or 0) for c in cams)
print(f"n={len(cams)} fr={fr}")
')
  echo "$out"
  fr=$(echo "$out" | sed -n 's/.*fr=\([0-9]*\).*/\1/p')
  [[ "${fr:-0}" -ge 80 ]] && break
  sleep 5
done

# Probe with live camera
CAM=$(curl -sS http://127.0.0.1:8001/cameras | python3 -c 'import json,sys;cams=json.load(sys.stdin).get("cameras")or[];print(cams[0]["camera_id"] if cams else "")')
ORG=74d51ead-97a7-4e41-a488-503a9b90c466
echo "probe cam=$CAM"
curl -sS -X POST "http://127.0.0.1:8001/cameras/$CAM/evidence/capture" \
  -H 'Content-Type: application/json' \
  -d "{\"org_id\":\"$ORG\",\"event\":{\"event_type\":\"speeding\",\"event_id\":\"live-probe-$(date +%s)\",\"camera_id\":\"$CAM\",\"confidence\":0.9,\"bbox\":{\"x\":0.4,\"y\":0.3,\"width\":0.2,\"height\":0.25},\"bbox_ts\":$(date +%s)}}" \
  -o /tmp/cap_live.json -w "http=%{http_code}\n"
python3 - <<'PY'
import json
d=json.load(open("/tmp/cap_live.json"))
pkg=d.get("package") or {}
meta=pkg.get("metadata") or {}
print("status", d.get("evidence_status"), "missing", meta.get("missing_roles"), "plate_status", meta.get("plate_status"))
print("roles", [i.get("role") for i in (pkg.get("images") or [])])
print("capture_source", meta.get("capture_source"), "plate", meta.get("plate_number"), "ocr", meta.get("plate_ocr_source"))
PY

if ! curl -sf http://127.0.0.1:5174/ >/dev/null; then
  cd frontend && nohup npm run dev -- --host 127.0.0.1 --port 5174 >/tmp/citevision-vite.log 2>&1 & sleep 3; cd "$ROOT"
fi

bash scripts/health_check_all.sh || true

export RULE_DURATION_SEC=480 VALIDATE_MODE=wait SKIP_FRIGATE_REBUILD=1
bash scripts/validate_rule.sh speeding
echo EXIT=$?
latest=$(find validation-evidence/speeding -name report.json | sort | tail -1)
python3 -c "import json;d=json.load(open('$latest'));print('result',d.get('result'))"
ls -la "$(dirname "$latest")/ui.png" 2>/dev/null || echo no_ui
