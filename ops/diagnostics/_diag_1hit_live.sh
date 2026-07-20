#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
echo "=== record flags ==="
python3 - <<'PY'
from pathlib import Path
import re
text=Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml").read_text()
cam="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
for key in ("record","snapshots"):
  m=re.search(rf"{re.escape(cam)}:.*?{key}:\s*\n\s*enabled:\s*(true|false)", text, re.S)
  print(key, m.group(1) if m else "?")
PY
echo "=== clip probe ==="
python3 - <<'PY'
import json,urllib.request,time
fc="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=1").read())
eid=ev[0]["id"]; now=time.time(); young=now-float(ev[0]["start_time"])
try:
  with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events/{eid}/clip.mp4", timeout=20) as r:
    print("young", round(young,1), "clip", r.status, len(r.read(2048)))
except Exception as e:
  print("young", round(young,1), "clip FAIL", getattr(e,"code",e))
try:
  with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events/{eid}/snapshot.jpg", timeout=15) as r:
    print("snap", r.status, len(r.read(2048)))
except Exception as e:
  print("snap FAIL", getattr(e,"code",e))
PY
echo "=== AI signals ==="
grep -c 'speed evidence dedupe' "$ROOT/logs/ai-engine.log" || true
grep -c 'frigate_track:' "$ROOT/logs/ai-engine.log" || true
grep -E 'frigate_track:|dedupe|compose|scene_bytes|ERROR.*evidence' "$ROOT/logs/ai-engine.log" | tail -40
echo "=== rules ==="
grep -E 'incomplete_evidence|suppressed|frigate_track|evidence/request' "$ROOT/logs/rules-engine.log" | tail -15
