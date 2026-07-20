#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
echo "=== last frigate/evidence lines ==="
grep -E 'frigate_track|dedupe|ERROR|Exception|WARNING.*evidence|compose|clip|snapshot' \
  "$ROOT/logs/ai-engine.log" | tail -60

echo "=== settings ==="
"$ROOT/ai-engine/.venv/bin/python" - <<'PY'
from citevision_ai.config import settings
print("correlate_wait", settings.frigate_correlate_wait_sec)
print("max_align", settings.frigate_demo_max_align_sec)
print("accept", settings.frigate_demo_accept_max_align_sec)
print("timeline_align", settings.frigate_demo_timeline_align)
print("demo_mode", settings.demo_mode)
print("demo_backend", settings.demo_evidence_backend)
print("frigate_enabled", settings.frigate_enabled)
print("frigate_evidence", settings.frigate_evidence)
PY

echo "=== try compose path in-process ==="
"$ROOT/ai-engine/.venv/bin/python" - <<'PY'
import time, json
from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence
from citevision_ai.evidence.gate import default_evidence_policy

ft = FrigateTrackEvidence()
fid = "cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
cam = "55694d53-8f58-4981-91b2-7c6cd528a25d"
org = "74d51ead-97a7-4e41-a488-503a9b90c466"
evt = {
  "event_type":"speeding","event_id":"local-test","track_id":1,
  "camera_id":cam,"org_id":org,"class_name":"car",
  "bbox":{"x":0.3,"y":0.3,"width":0.25,"height":0.25},
  "bbox_ts": time.time(),
}
pol = default_evidence_policy()
print("enabled", ft.enabled())
fb = ft._demo_latest_vehicle_event(fid)
print("fallback", None if not fb else (fb.get("id"), fb.get("label"), fb.get("has_clip"), fb.get("has_snapshot")))
t0=time.time()
out = ft.capture(pol, evt, org_id=org, camera_id=cam)
print("elapsed", round(time.time()-t0,1))
if out is None:
  print("capture returned None")
else:
  print("keys", list(out.keys()))
  print("status", out.get("status"), "meta", {k: out.get("meta",{}).get(k) for k in ("capture_source","frigate_event_id","align_delta_ms","bbox_source")})
  print("clip_bytes", len(out.get("clip_bytes") or b""), "scene", len(out.get("scene") or b""), "subject", len(out.get("subject") or b""))
PY
