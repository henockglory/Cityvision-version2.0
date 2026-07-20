#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

echo "=== kill validators ==="
pkill -f '_validate_all_5.sh' 2>/dev/null || true
pkill -f 'validate_rule_dod.py' 2>/dev/null || true
pkill -f '_validate_rule_frigate_1hit.py' 2>/dev/null || true

echo "=== frigate status ==="
docker inspect citevision-v2-frigate --format 'Status={{.State.Status}} Health={{.State.Health.Status}}'
timeout 5 curl -sf http://127.0.0.1:5000/api/version || echo version_timeout

echo "=== restart frigate ==="
docker restart citevision-v2-frigate
for i in $(seq 1 40); do
  if timeout 3 curl -sf http://127.0.0.1:5000/api/version >/dev/null; then
    echo "frigate up after ${i}x2s"
    break
  fi
  sleep 2
done
timeout 5 curl -sf http://127.0.0.1:5000/api/version; echo

echo "=== sample boxes ==="
timeout 10 curl -sf "http://127.0.0.1:5000/api/events?limit=3" -o /tmp/frigate_evs.json || echo events_fail
python3 <<'PY'
from pathlib import Path
import json
p=Path("/tmp/frigate_evs.json")
print("size", p.stat().st_size if p.exists() else 0)
if p.exists() and p.stat().st_size>2:
    evs=json.loads(p.read_text())
    print("n", len(evs))
    for e in evs[:3]:
        data=e.get("data") or {}
        print("box", data.get("box"), "label", e.get("label"))
PY

# Sync cabin 1hit fix
cp -f /mnt/c/Users/gheno/citevision/scripts/_validate_rule_frigate_1hit.py "$ROOT/scripts/"
sed -i 's/\r$//' "$ROOT/scripts/_validate_rule_frigate_1hit.py"
grep -n '_CABIN_RULE_NAMES\|evidence_ok\|live' "$ROOT/scripts/_validate_rule_frigate_1hit.py" | head -20

# Ensure services
curl -sf http://127.0.0.1:8081/health || bash scripts/_restart_backend.sh
curl -sf http://127.0.0.1:8010/health || bash scripts/_start-rules-engine.sh
curl -sf http://127.0.0.1:8001/health >/dev/null || python3 scripts/_restart_ai.py
curl -sf http://127.0.0.1:5174/ >/dev/null || {
  cd "$ROOT/frontend"
  nohup npm run dev -- --host 127.0.0.1 --port 5174 > /tmp/citevision-vite.log 2>&1 &
  sleep 3
}

source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -X POST http://127.0.0.1:8081/api/v1/internal/ingest/resync-spatial -H "X-Internal-Key: $KEY"; echo

echo "=== ready for re-validate ==="
bash scripts/health_check_all.sh || true
