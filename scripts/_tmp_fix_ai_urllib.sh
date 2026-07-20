#!/usr/bin/env bash
set -uo pipefail
ROOT=~/citevision-v2
python3 /mnt/c/Users/gheno/citevision/scripts/_tmp_fix_urllib_import.py
bash "$ROOT/scripts/restart-ai-engine.sh"
for i in $(seq 1 60); do
  if curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
    echo AI_UP
    break
  fi
  sleep 2
done
curl -sf --max-time 5 http://127.0.0.1:8001/health | head -c 200; echo
curl -sf --max-time 3 -o /dev/null -w "UI %{http_code}\n" http://127.0.0.1:5174/ || echo UI_DOWN
curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null && echo BE_OK || echo BE_DOWN
