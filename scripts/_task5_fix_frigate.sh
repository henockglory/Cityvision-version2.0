#!/usr/bin/env bash
set -uo pipefail
cd /home/gheno/citevision-v2
docker ps -a --filter name=citevision-v2-frigate
echo "--- state ---"
docker inspect citevision-v2-frigate --format '{{.State.Status}} health={{.State.Health.Status}} err={{.State.Error}}' 2>&1 || true
echo "--- ports ---"
ss -ltn | grep -E ':5000|:1984' || true
echo "--- restart frigate ---"
docker restart citevision-v2-frigate
for i in $(seq 1 45); do
  if curl -sf http://127.0.0.1:5000/api/version; then
    echo
    echo "frigate_ok after ${i}s"
    break
  fi
  sleep 2
done
docker ps --filter name=frigate --format '{{.Names}} {{.Status}}'
curl -sf http://127.0.0.1:8081/health || python3 scripts/_restart_backend.py
curl -sf http://127.0.0.1:8001/health >/dev/null || python3 scripts/_restart_ai.py
bash scripts/health_check_all.sh
