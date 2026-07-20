#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
cd ~/citevision-v2
set -a; . ./.env; set +a
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

echo "=== backend frigate health ==="
curl -sS --max-time 10 http://127.0.0.1:8081/api/v1/frigate/health || curl -sS --max-time 10 -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/frigate/status || true
echo

echo "=== rebuild with full response ==="
curl -sS -w "\nHTTP=%{http_code}\n" --max-time 120 -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild || true
echo

echo "=== FRIGATE_ENABLED in backend process env ==="
if [ -f logs/backend.pid ]; then
  pid=$(cat logs/backend.pid)
  echo "pid=$pid"
  tr '\0' '\n' < /proc/$pid/environ 2>/dev/null | grep -E '^FRIGATE_|^DEMO_|^EVIDENCE_' || echo "no env readable"
fi

echo "=== config path files ==="
ls -la infra/frigate-config/ 2>/dev/null | head -20
ls -la /home/gheno/citevision-v2/infra/frigate-config/config.yml 2>/dev/null || true
echo "--- config cameras ---"
python3 <<'PY'
import yaml, pathlib
p=pathlib.Path("infra/frigate-config/config.yml")
if not p.exists():
  print("missing", p); raise SystemExit
c=yaml.safe_load(p.read_text()) or {}
cams=c.get("cameras") or {}
print("n=", len(cams), "keys=", list(cams.keys())[:15])
print("go2rtc streams=", list(((c.get("go2rtc") or {}).get("streams") or {}).keys())[:15])
PY

echo "=== backend log tail ==="
tail -40 logs/backend.log
