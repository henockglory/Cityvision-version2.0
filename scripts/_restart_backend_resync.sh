#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

bash scripts/_restart_backend.sh
bash scripts/_start-rules-engine.sh
sleep 3
curl -sf http://127.0.0.1:8081/health; echo
curl -sf http://127.0.0.1:8010/health; echo

curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial" \
  -H "X-Internal-Key: $KEY"; echo
sleep 5
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial" \
  -H "X-Internal-Key: $KEY"; echo

for i in $(seq 1 18); do
  curl -sS http://127.0.0.1:8001/cameras | python3 -c '
import json,sys
d=json.load(sys.stdin)
cams=d.get("cameras") or []
fr=sum(int(c.get("frames_read") or 0) for c in cams)
err=(cams[0].get("last_error") or "")[:60] if cams else ""
print(f"n={len(cams)} frames={fr} err={err}")
'
  fr=$(curl -sS http://127.0.0.1:8001/cameras | python3 -c 'import json,sys;d=json.load(sys.stdin);print(sum(int(c.get("frames_read")or 0)for c in (d.get("cameras")or[])))')
  if [[ "${fr:-0}" -ge 20 ]]; then
    echo INGEST_READY
    break
  fi
  sleep 5
done

# Ensure UI
if ! curl -sf http://127.0.0.1:5174/ >/dev/null; then
  cd "$ROOT/frontend"
  nohup npm run dev -- --host 127.0.0.1 --port 5174 > /tmp/citevision-vite.log 2>&1 &
  sleep 3
fi
curl -sf -o /dev/null -w "ui=%{http_code}\n" http://127.0.0.1:5174/
bash scripts/health_check_all.sh || true
