#!/usr/bin/env python3
"""Live test: Frigate evidence capture via ai-engine API."""
import json
import time
import urllib.request

CAM = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
now = time.time()
body = {
    "org_id": ORG,
    "event": {
        "event_id": f"test-frigate-{int(now)}",
        "event_type": "speeding",
        "timestamp": now,
        "bbox_ts": now,
        "confidence": 0.92,
        "class_name": "car",
        "track_id": 999,
        "zone_id": "3883c6cb-2721-4c0d-827b-933fc8b428a6",
        "speed_kmh": 45.0,
    },
    "evidence": {
        "enabled": True,
        "clip_seconds": 6,
        "draw_bbox": True,
        "images": [
            {"role": "scene", "label": "Vue d'ensemble", "crop": "full"},
            {"role": "subject", "label": "Véhicule", "crop": "bbox", "padding_pct": 12},
        ],
    },
}
req = urllib.request.Request(
    f"http://127.0.0.1:8001/cameras/{CAM}/evidence/capture",
    data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as resp:
    out = json.loads(resp.read().decode())
pkg = out.get("package") or {}
meta = pkg.get("metadata") or out.get("meta") or {}
print("evidence_status=", out.get("evidence_status") or meta.get("evidence_status"))
print("capture_source=", meta.get("capture_source"))
print("bbox_source=", meta.get("bbox_source"))
print("frigate_bbox_embedded=", meta.get("frigate_bbox_embedded"))
print("bbox_quality_ok=", meta.get("bbox_quality_ok"))
print("bbox=", meta.get("bbox"))
print("clip=", bool((pkg.get("clip") or {}).get("asset_id")))
print("images=", [(i.get("role"), i.get("asset_id", "")[:8]) for i in (pkg.get("images") or [])])
