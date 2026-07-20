#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "health api=$(curl -sf http://127.0.0.1:8081/health || echo DOWN)"
echo "health rules=$(curl -sf http://127.0.0.1:8010/health || echo DOWN)"
echo "health ai=$(curl -sf http://127.0.0.1:8001/health | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("status"),d.get("models_all_ok"))' 2>/dev/null || echo DOWN)"
echo "ui=$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:5174/ || echo 000)"

# Restart rules if down
if ! curl -sf http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh || true
  sleep 5
fi
if ! curl -sf http://127.0.0.1:8081/health >/dev/null; then
  bash scripts/_restart_backend.sh || true
  sleep 3
fi

curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial" -H "X-Internal-Key: $KEY" || true
echo
sleep 8
curl -sf -X POST "http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial" -H "X-Internal-Key: $KEY" || true
echo

for i in $(seq 1 20); do
  python3 - <<'PY'
import json,urllib.request
d=json.load(urllib.request.urlopen("http://127.0.0.1:8001/cameras", timeout=5))
cams=d.get("cameras") or []
fr=sum(int(c.get("frames_read") or 0) for c in cams)
err=(cams[0].get("last_error") or "")[:70] if cams else ""
print(f"n={len(cams)} frames={fr} err={err}")
open("/tmp/cv_frames","w").write(str(fr))
PY
  fr=$(cat /tmp/cv_frames 2>/dev/null || echo 0)
  if [[ "${fr:-0}" -ge 20 ]]; then
    echo INGEST_READY
    break
  fi
  sleep 5
done

bash scripts/health_check_all.sh || true
