#!/usr/bin/env bash
set -uo pipefail
FCAM=cv_55694d53-8f58-4981-91b2-7c6cd528a25d
curl -sf "http://127.0.0.1:5000/api/events?cameras=${FCAM}&limit=8" -o /tmp/fev.json
python3 - <<'PY'
import json,time
now=time.time()
print("now", now)
ev=json.load(open("/tmp/fev.json"))
for e in ev:
    st=float(e.get("start_time") or 0)
    et=e.get("end_time")
    print({
      "id": e.get("id"),
      "label": e.get("label"),
      "age_start": round(now-st,1),
      "end_time": et,
      "age_end": (round(now-float(et),1) if isinstance(et,(int,float)) else None),
      "has_clip": e.get("has_clip"),
      "has_snapshot": e.get("has_snapshot"),
      "score": e.get("top_score") or e.get("score"),
    })
PY

echo "=== config retain/objects for speed cam ==="
python3 - <<'PY'
import yaml
from pathlib import Path
p=Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml")
d=yaml.safe_load(p.read_text())
cam=d.get("cameras",{}).get("cv_55694d53-8f58-4981-91b2-7c6cd528a25d",{})
print(yaml.dump(cam, default_flow_style=False)[:2500])
print("--- record ---")
print(yaml.dump(d.get("record") or {}, default_flow_style=False)[:800])
print("--- objects ---")
print(yaml.dump(d.get("objects") or {}, default_flow_style=False)[:800])
PY

echo "=== go2rtc streams now ==="
curl -sf http://127.0.0.1:1984/api/streams | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d), list(d)[:10])'
