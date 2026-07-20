#!/usr/bin/env bash
# Fix Frigate paths (backend cwd=backend/) then rebuild cameras.
set -euo pipefail
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
ROOT=~/citevision-v2
cd "$ROOT"
ENV="$ROOT/.env"

upsert() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV"
  else
    printf '%s=%s\n' "$key" "$val" >>"$ENV"
  fi
}

upsert FRIGATE_ENABLED 1
upsert FRIGATE_CONFIG_SYNC 1
upsert FRIGATE_EVIDENCE 1
upsert FRIGATE_EVENTS 1
upsert FRIGATE_BASE_YAML "$ROOT/infra/frigate.base.yaml"
upsert FRIGATE_CONFIG_PATH "$ROOT/infra/frigate-config/config.yml"
upsert FRIGATE_GENERATED_DIR "$ROOT/infra/frigate-config"
upsert FRIGATE_URL 'http://127.0.0.1:5000'

echo "=== absolute Frigate paths ==="
grep -E '^(FRIGATE_BASE_YAML|FRIGATE_CONFIG_PATH|FRIGATE_GENERATED_DIR|FRIGATE_ENABLED)=' "$ENV"
test -s "$ROOT/infra/frigate.base.yaml" || { echo "empty base yaml"; exit 1; }

source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
LOGDIR="$ROOT/logs"

echo "=== restart backend ==="
stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
free_port 8081 2>/dev/null || true
(cd backend && go build -o bin/citevision-api ./cmd/api)
start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:8081/health" 90

echo "=== frigate rebuild ==="
curl -sS -w "\nHTTP=%{http_code}\n" --max-time 180 -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild

echo "=== restart frigate ==="
docker restart citevision-v2-frigate >/dev/null
for i in $(seq 1 45); do
  curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null && break
  sleep 2
done
sleep 30

echo "=== cameras ==="
curl -sf --max-time 8 http://127.0.0.1:5000/api/stats -o /tmp/frigate_stats.json
python3 <<'PY'
import json
d=json.load(open("/tmp/frigate_stats.json"))
cams=d.get("cameras") or {}
print("n_cameras", len(cams))
print("names", list(cams.keys())[:20])
for k,v in list(cams.items())[:12]:
    print(f"  {k}: fps={v.get('camera_fps')} det={v.get('detection_fps')}")
if not cams:
    raise SystemExit(2)
PY

echo "=== wait events ==="
ok=0
for i in $(seq 1 24); do
  n=$(curl -sf --max-time 5 'http://127.0.0.1:5000/api/events?limit=5' | python3 -c 'import sys,json; e=json.load(sys.stdin); print(len(e) if isinstance(e,list) else 0)')
  echo "  try $i events=$n"
  if [ "${n:-0}" -gt 0 ]; then ok=1; break; fi
  sleep 5
done
[ "$ok" = 1 ] && echo "[OK] events ready" || echo "[WARN] no events yet"
