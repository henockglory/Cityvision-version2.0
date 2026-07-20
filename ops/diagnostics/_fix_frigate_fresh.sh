#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
docker restart citevision-v2-go2rtc citevision-v2-frigate
sleep 25
python3 scripts/_try_login.py >/dev/null
python3 - <<'PY'
import json, os, time, urllib.parse, urllib.request
API = "http://127.0.0.1:8081"
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
INTERNAL = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
login = json.loads(urllib.request.urlopen(urllib.request.Request(
    f"{API}/api/v1/auth/login",
    data=json.dumps({"email": "glory.henock@hologram.cd", "password": "Hologram2026!"}).encode(),
    headers={"Content-Type": "application/json"}, method="POST",
)).read())
tok = login["access_token"]
vid = "aaea7c30-1c4c-4ce5-9cd6-4b1f8ded4118"
urllib.request.urlopen(urllib.request.Request(
    f"{API}/api/v1/orgs/{ORG}/demo/settings",
    data=json.dumps({"source_mode": "video", "active_video_id": vid, "active_camera_id": None}).encode(),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {tok}"}, method="PATCH",
))
urllib.request.urlopen(urllib.request.Request(
    f"{API}/api/v1/internal/ingest/resync-spatial",
    data=b"{}",
    headers={"Content-Type": "application/json", "X-Internal-Key": INTERNAL}, method="POST",
))
cam = "cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
for i in range(18):
    qs = urllib.parse.urlencode({"cameras": cam, "limit": 3})
    evs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?{qs}").read())
    now = time.time()
    if evs:
        st = evs[0].get("start_time", 0)
        age = now - float(st)
        print(f"poll {i} youngest_age={age:.0f}s", flush=True)
        if age <= 30:
            print("FRESH_OK", flush=True)
            raise SystemExit(0)
    time.sleep(10)
print("FRESH_FAIL", flush=True)
raise SystemExit(1)
PY
