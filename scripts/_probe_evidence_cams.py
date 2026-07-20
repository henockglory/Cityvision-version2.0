#!/usr/bin/env python3
"""Probe evidence/request for demo cameras."""
import json, os, uuid, urllib.request
from datetime import datetime, timezone

def load_env():
    p = os.path.expanduser("~/citevision-v2/.env")
    if os.path.isfile(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env()
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
KEY = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
ORG = os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
CAMS = {
    "speed": "55694d53-8f58-4981-91b2-7c6cd528a25d",
    "feux": "8ed20433-57d5-4999-a6ab-0bea028b23a3",
    "phone": "f691ef55-6791-495b-a35e-be215e7ac109",
}

def post(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "X-Internal-Key": KEY}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]

for label, cam in CAMS.items():
    evt = {
        "event_id": str(uuid.uuid4()),
        "camera_id": cam,
        "event_type": "speeding" if label == "speed" else ("red_light_violation" if label == "feux" else "phone_use_violation"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "track_id": 1,
        "class_name": "car",
        "confidence": 0.9,
        "metadata": {"demo": True},
    }
    body = {
        "camera_id": cam,
        "event": evt,
        "evidence": {"enabled": True, "clip_seconds": 6, "images": [{"role": "scene"}, {"role": "subject"}]},
    }
    st, resp = post(f"{API}/api/v1/internal/orgs/{ORG}/evidence/request", body)
    pkg = resp.get("package") if isinstance(resp, dict) else None
    clip = (pkg or {}).get("clip", {}) if isinstance(pkg, dict) else {}
    imgs = len((pkg or {}).get("images") or []) if isinstance(pkg, dict) else 0
    print(f"{label} cam={cam[:8]} HTTP {st} pkg={'yes' if pkg else 'no'} clip={bool(clip.get('url') or clip.get('asset_id'))} images={imgs}")
    if isinstance(resp, dict) and resp.get("error"):
        print(f"  error: {resp.get('error')}")
