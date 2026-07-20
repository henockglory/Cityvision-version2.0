#!/usr/bin/env bash
set -uo pipefail
cd /home/gheno/citevision-v2
export PATH="/usr/local/go/bin:$PATH"
export HOME=/home/gheno
export SKIP_FRIGATE_REBUILD=1

echo "=== wait docker/frigate/postgres ==="
for i in $(seq 1 60); do
  ok=1
  docker ps --format '{{.Names}} {{.Status}}' 2>/dev/null | grep -q 'citevision-v2-postgres.*Up' || ok=0
  curl -sf http://127.0.0.1:5000/api/version >/dev/null 2>&1 || ok=0
  if [ "$ok" = 1 ]; then echo "infra_ok after ${i}s"; break; fi
  sleep 2
done
curl -sf http://127.0.0.1:5000/api/version || { echo frigate_still_down; docker ps; exit 1; }

echo "=== restart AI ==="
python3 scripts/_restart_ai.py || true
echo "=== restart backend ==="
python3 scripts/_restart_backend.py || true

for i in $(seq 1 30); do
  curl -sf http://127.0.0.1:8081/health >/dev/null && curl -sf http://127.0.0.1:8001/health >/dev/null && break
  sleep 2
done
curl -sf http://127.0.0.1:8081/health && echo
curl -sf http://127.0.0.1:8001/health | python3 -c 'import sys,json;d=json.load(sys.stdin);print("ai",d.get("status"),d.get("demo_mode"),d.get("models_all_ok"))'

if ! curl -sf http://127.0.0.1:5174/ >/dev/null 2>&1; then
  (cd frontend && setsid nohup npm run dev -- --host 127.0.0.1 --port 5174 >> ../logs/vite.log 2>&1 & echo $! > ../logs/vite.pid)
  sleep 5
fi

bash scripts/health_check_all.sh || true

echo "=== validate red_light ==="
stdbuf -oL -eL bash scripts/validate_rule.sh red_light 2>&1 | tee /tmp/task5_validate_red4.log
echo EXIT:$?
