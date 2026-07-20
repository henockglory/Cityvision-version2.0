#!/usr/bin/env bash
curl -sf http://127.0.0.1:8001/cameras/9a3cd323-3820-46f0-aa5b-86c086a4a782/detections/latest > /tmp/det.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/det.json"))
print("keys", list(d.keys()) if isinstance(d,dict) else type(d))
tracks=d.get("tracks") or d.get("detections") or d.get("objects") or []
print("n", len(tracks) if isinstance(tracks,list) else tracks)
for t in (tracks[:12] if isinstance(tracks,list) else []):
    bbox=t.get("bbox") or {}
    cx=bbox.get("x",0)+bbox.get("width",0)/2
    cy=bbox.get("y",0)+bbox.get("height",0)/2
    # if normalized already
    print(t.get("class_name") or t.get("class") or t.get("label"), "id", t.get("track_id"), "bbox", bbox, "cy", cy)
print("meta", {k:d.get(k) for k in ("frame_width","frame_height","ts","timestamp","w","h") if k in d})
PY
