#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
FCAM=cv_55694d53-8f58-4981-91b2-7c6cd528a25d
curl -sf "http://127.0.0.1:5000/api/events?cameras=${FCAM}&limit=3" -o /tmp/fev.json
python3 - <<'PY'
import json
ev=json.load(open("/tmp/fev.json"))
for e in ev:
  print({
    "id": e.get("id"),
    "label": e.get("label"),
    "has_clip": e.get("has_clip"),
    "has_snapshot": e.get("has_snapshot"),
    "data_keys": list((e.get("data") or {}).keys())[:20],
    "box": (e.get("data") or {}).get("box"),
    "box2": e.get("box"),
    "top_score": e.get("top_score"),
  })
PY

"$ROOT/ai-engine/.venv/bin/python" - <<'PY'
from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence, _frigate_box_from_event, _VEHICLE_LABELS
ft=FrigateTrackEvidence()
fid="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
print("enabled", ft.enabled())
evs=ft.list_events_for_camera(fid)
print("list_events n", len(evs))
for e in evs[:5]:
  print(" ", e.get("id"), e.get("label"), "box", _frigate_box_from_event(e), "in_vehicle", str(e.get("label") or "").lower() in _VEHICLE_LABELS)
fb=ft._demo_latest_vehicle_event(fid)
print("fallback", None if fb is None else fb.get("id"))
# check if brief wait code present
import inspect
src=inspect.getsource(ft.capture)
print("has brief wait", "brief wait for any vehicle" in src)
PY
