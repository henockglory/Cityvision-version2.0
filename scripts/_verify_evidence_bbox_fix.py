#!/usr/bin/env python3
"""Verify fixed Frigate evidence: bbox visible + subject texture."""
import json
import time
import urllib.request

CAM = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
API = "http://127.0.0.1:8081/api/v1"
now = time.time()
body = {
    "org_id": ORG,
    "event": {
        "event_id": f"test-fix-{int(now)}",
        "event_type": "speeding",
        "timestamp": now,
        "bbox_ts": now,
        "confidence": 0.9,
        "class_name": "car",
        "track_id": 42,
        "zone_id": "3883c6cb-2721-4c0d-827b-933fc8b428a6",
        "speed_kmh": 55.0,
        "bbox": {"x": 0.35, "y": 0.45, "width": 0.12, "height": 0.18},
    },
    "evidence": {
        "enabled": True,
        "clip_seconds": 6,
        "draw_bbox": True,
        "images": [
            {"role": "scene", "crop": "full"},
            {"role": "subject", "crop": "bbox", "padding_pct": 12},
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
meta = (out.get("package") or {}).get("metadata") or {}
pkg = out.get("package") or {}
print("status", meta.get("evidence_status"))
print("bbox_ok", meta.get("bbox_quality_ok"), "source", meta.get("bbox_source"))
print("bbox", meta.get("bbox"))
print("frigate_emb", meta.get("frigate_bbox_embedded"))
print("subject_tex", meta.get("subject_texture"))
print("clip", bool((pkg.get("clip") or {}).get("asset_id")))

login = json.dumps({"email": "glory.henock@hologram.cd", "password": "Hologram2026!"}).encode()
with urllib.request.urlopen(
    urllib.request.Request(f"{API}/auth/login", data=login, headers={"Content-Type": "application/json"}, method="POST")
) as r:
    tok = json.loads(r.read().decode())["token"]
for img in pkg.get("images") or []:
    aid = img.get("asset_id")
    role = img.get("role")
    if not aid:
        continue
    url = f"{API}/orgs/{ORG}/assets/{aid}/content"
    data = urllib.request.urlopen(
        urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    ).read()
    path = f"/tmp/ev_{role}.jpg"
    with open(path, "wb") as f:
        f.write(data)
    print(role, len(data), path)
