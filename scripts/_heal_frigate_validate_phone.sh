#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

echo "=== frigate heal ==="
docker restart citevision-v2-frigate
for i in $(seq 1 45); do
  if timeout 4 curl -sf http://127.0.0.1:5000/api/version >/dev/null; then
    echo "frigate OK after ${i}"
    timeout 4 curl -sf http://127.0.0.1:5000/api/version; echo
    break
  fi
  sleep 2
done

# Ensure go2rtc streams + frigate cameras have fps
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
bash scripts/ensure-demo-streams.sh || true
curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild -H "X-Internal-Key: $KEY" || true
echo
sleep 5
curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial -H "X-Internal-Key: $KEY" || true
echo

sleep 15
timeout 5 curl -sf http://127.0.0.1:5000/api/stats | python3 -c '
import json,sys
d=json.load(sys.stdin)
for k,v in (d.get("cameras") or {}).items():
  print(k[:36], "fps", v.get("camera_fps"), "det", v.get("detection_fps"))
' || echo stats_fail

bash scripts/health_check_all.sh
hc=$?
if [[ $hc -ne 0 ]]; then
  echo "health still red — abort"
  exit 1
fi

export RULE_DURATION_SEC=360
export VALIDATE_MODE=wait
echo "=== validate phone ==="
bash scripts/validate_rule.sh phone
echo EXIT=$?
find validation-evidence/phone -name report.json | sort | tail -2 | while read -r f; do
  python3 -c "import json;d=json.load(open('$f'));print('$f', d.get('result'));
checks=d.get('checks') or []
print(' fails', [c['id'] for c in checks if not c.get('ok')])"
done
