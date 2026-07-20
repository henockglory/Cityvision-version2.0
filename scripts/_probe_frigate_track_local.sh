#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export PYTHONPATH="$ROOT/ai-engine/src${PYTHONPATH:+:$PYTHONPATH}"
PY="$ROOT/ai-engine/.venv/bin/python"
set -a
# shellcheck disable=SC1091
source <(grep -E '^(FRIGATE_|DEMO_|EVIDENCE_|OCR_)' .env | sed 's/\r$//')
set +a

"$PY" <<'PY'
import json, urllib.request, time
from citevision_ai.config import settings
from citevision_ai.evidence.frigate_track_evidence import FrigateTrackEvidence

print("frigate_enabled", settings.frigate_enabled)
print("frigate_evidence", settings.frigate_evidence)
print("frigate_url", settings.frigate_url)
print("demo_mode", settings.demo_mode)
print("demo_evidence_backend", settings.demo_evidence_backend)
print("demo_timeline_align", settings.frigate_demo_timeline_align)
print("max_align", settings.frigate_demo_max_align_sec)
print("correlate_wait", settings.frigate_correlate_wait_sec)

cam = "55694d53-8f58-4981-91b2-7c6cd528a25d"
tr = FrigateTrackEvidence()
print("enabled", tr.enabled())
fid = tr.frigate_camera_id(cam)
print("fid", fid)
evs = tr._list_events(fid)
print("list_events", len(evs))
for e in evs[:5]:
    data = e.get("data") if isinstance(e.get("data"), dict) else {}
    print(" ", e.get("id","")[:28], "label", e.get("label"), "has_clip", e.get("has_clip"),
          "box", bool(data.get("box")), "start", e.get("start_time"))

fb = tr._demo_latest_vehicle_event(fid)
print("fallback", None if fb is None else fb.get("id"))

evt = {
    "event_id": f"local-{int(time.time())}",
    "event_type": "speeding",
    "track_id": 1,
    "class_name": "car",
    "bbox_ts": time.time(),
    "bbox": {"x": 0.3, "y": 0.4, "w": 0.2, "h": 0.25},
}
policy = {"clip": True, "clip_seconds": 6, "images": [
    {"role": "scene"}, {"role": "subject"}, {"role": "plate", "crop": "plate"}
]}
t0 = time.time()
out = tr.capture(policy, evt, org_id="org", camera_id=cam)
print(f"capture elapsed={time.time()-t0:.1f}s out_keys={None if out is None else list(out.keys())}")
if out and out.get("meta"):
    print("meta capture_source", out["meta"].get("capture_source"))
    print("meta evidence_status", out["meta"].get("evidence_status"))
    print("has scene", bool(out.get("scene")), "subject", bool(out.get("subject")),
          "clip", bool(out.get("clip_bytes")), "plate", bool(out.get("plate_jpeg")))
    print("clip_bytes", len(out["clip_bytes"]) if out.get("clip_bytes") else 0)
PY
