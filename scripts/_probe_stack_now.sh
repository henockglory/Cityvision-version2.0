#!/usr/bin/env bash
curl -sf --max-time 3 http://127.0.0.1:5000/api/version || echo frigate_down
curl -sf --max-time 3 http://127.0.0.1:8001/health | head -c 200; echo
curl -sf http://127.0.0.1:8001/cameras | python3 - <<'PY'
import json,sys
raw=sys.stdin.read()
d=json.loads(raw) if raw else {}
cams=d.get("cameras") or []
print("ai_cams", len(cams))
for c in cams[:8]:
    print(c.get("camera_id","?")[:12], "run", c.get("running"), "fp", c.get("frames_processed"), "err", c.get("last_error"))
PY
tail -20 /home/gheno/citevision-v2/logs/heal-validate-red-count.log 2>/dev/null || true
