#!/usr/bin/env bash
# Enable Frigate sync in WSL .env, restart backend+AI, rebuild Frigate cameras.
set -euo pipefail
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
ROOT=~/citevision-v2
cd "$ROOT"
ENV="$ROOT/.env"
test -f "$ENV"

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
upsert FRIGATE_LIVE 0
upsert FRIGATE_URL 'http://127.0.0.1:5000'
upsert FRIGATE_DEMO_MODE true
upsert DEMO_MODE 1
upsert DEMO_EVIDENCE_BACKEND strict_frigate
upsert DEMO_RESOLUTION 1080p
upsert LIVE_108_ENABLED 0
upsert EVIDENCE_BACKEND hybrid

echo "=== Frigate/demo flags ==="
grep -E '^(FRIGATE_ENABLED|FRIGATE_CONFIG_SYNC|FRIGATE_EVIDENCE|FRIGATE_EVENTS|FRIGATE_LIVE|FRIGATE_URL|FRIGATE_DEMO_MODE|DEMO_MODE|DEMO_EVIDENCE_BACKEND|EVIDENCE_BACKEND)=' "$ENV"

source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
LOGDIR="$ROOT/logs"
mkdir -p "$LOGDIR"

echo "=== restart backend (pick up FRIGATE_*) ==="
stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
free_port 8081 2>/dev/null || true
(cd backend && go build -o bin/citevision-api ./cmd/api)
start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
wait_http_ok "http://127.0.0.1:8081/health" 90

echo "=== restart AI (demo evidence flags) ==="
bash scripts/restart-ai-engine.sh
wait_http_ok "http://127.0.0.1:8001/health" 180

echo "=== repair streams + frigate rebuild ==="
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true
echo
RESP=$(curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild || echo '{"status":"curl_fail"}')
echo "$RESP"
if echo "$RESP" | grep -q disabled; then
  echo "[FAIL] Frigate still disabled after backend restart"
  exit 1
fi

echo "=== restart frigate container ==="
docker restart citevision-v2-frigate >/dev/null
for i in $(seq 1 45); do
  curl -sf --max-time 3 http://127.0.0.1:5000/api/version >/dev/null && break
  sleep 2
done
sleep 25

echo "=== verify cameras ==="
curl -sf --max-time 8 http://127.0.0.1:5000/api/stats -o /tmp/frigate_stats.json
python3 <<'PY'
import json
d=json.load(open("/tmp/frigate_stats.json"))
cams=d.get("cameras") or {}
print("n_cameras", len(cams))
print("names", list(cams.keys())[:20])
for k,v in list(cams.items())[:10]:
    print(f"  {k}: fps={v.get('camera_fps')} det={v.get('detection_fps')}")
if not cams:
    raise SystemExit(2)
PY

echo "=== wait for at least 1 Frigate event (up to 90s) ==="
ok=0
for i in $(seq 1 18); do
  n=$(curl -sf --max-time 5 'http://127.0.0.1:5000/api/events?limit=5' | python3 -c 'import sys,json; e=json.load(sys.stdin); print(len(e) if isinstance(e,list) else 0)')
  echo "  try $i events=$n"
  if [ "${n:-0}" -gt 0 ]; then ok=1; break; fi
  sleep 5
done
if [ "$ok" != 1 ]; then
  echo "[WARN] no Frigate events yet — E2E preflight may still block"
else
  echo "[OK] Frigate events present"
fi
