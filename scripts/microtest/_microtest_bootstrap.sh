#!/usr/bin/env bash
set -euo pipefail
cd ~/citevision-v2
bash /mnt/c/Users/gheno/citevision/scripts/microtest/_microtest_sync_wsl.sh
bash scripts/wsl-boot-stack.sh 2>/dev/null || bash scripts/health_check_all.sh || true
for i in $(seq 1 15); do
  curl -sf -m 5 http://127.0.0.1:5000/api/version && break
  sleep 5
done
curl -sf -m 5 http://127.0.0.1:5000/api/version || echo FRIGATE_STILL_DOWN
python3 scripts/_restart_ai.py
sleep 15
curl -sf -m 8 http://127.0.0.1:8001/debug/rule-blockers -o /tmp/b.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/b.json"))
print("hsv_gate_debug_present", "hsv_gate_debug" in d)
print("keys", list((d.get("hsv_gate_debug") or {}).keys())[:5])
PY
