#!/usr/bin/env python3
"""Start demo ingest + run speed/phone validation."""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.expanduser("~/citevision-v2")
os.chdir(ROOT)

def load_env():
    p = ".env"
    if os.path.isfile(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env()
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
KEY = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
ORG = os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")

def post(url, body=None, headers=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def patch(url, body, token, timeout=180):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def get(url, token=None, timeout=30):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(url, headers=h, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

for i in range(40):
    try:
        get(f"{API}/health", timeout=5)
        print("backend OK")
        break
    except Exception:
        time.sleep(2)
else:
    sys.exit("backend down")

post(f"{API}/api/v1/internal/demo/repair-streams", headers={"X-Internal-Key": KEY})
post(f"{API}/api/v1/internal/ingest/frigate/rebuild", headers={"X-Internal-Key": KEY})

login = post(f"{API}/api/v1/auth/login", {"email": EMAIL, "password": PASS})
token = login["access_token"]

# Speed video first (Ligne Continue)
cams = get(f"{API}/api/v1/orgs/{ORG}/cameras", token)
speed_vid = None
for c in cams if isinstance(cams, list) else cams.get("items", []):
    name = str(c.get("name", "")).lower()
    if "ligne" in name or "continue" in name:
        meta = c.get("metadata") or {}
        if isinstance(meta, str):
            meta = json.loads(meta) if meta.startswith("{") else {}
        speed_vid = meta.get("demo_video_id")
        print("speed cam", c.get("id"), "video", speed_vid)
        break

if speed_vid:
    try:
        patch(
            f"{API}/api/v1/orgs/{ORG}/demo/settings",
            {"source_mode": "video", "active_video_id": speed_vid},
            token,
            timeout=30,
        )
        print("active speed video PATCH sent (validate script will wait for pipeline)")
    except Exception as e:
        print("speed video switch warn:", e)

time.sleep(10)
cams_ai = get("http://127.0.0.1:8001/cameras")
for c in cams_ai.get("cameras", []):
    print("AI", c.get("camera_id", "")[:8], "frames", c.get("frames_processed", 0), c.get("last_error"))

env = os.environ.copy()
env["VALIDATE_ONLY"] = "Démo · Excès de vitesse,Démo · Téléphone au volant"
env["ALERT_WAIT_SEC"] = "180"
env["DEMO_SETTLE_SEC"] = "60"
env["RULE_TIMEOUT_SEC"] = "600"
env["ADMIN_PASSWORD"] = PASS
env["DEMO_ORG_ID"] = ORG

log = f"logs/validate-speed-phone-{time.strftime('%Y%m%d-%H%M%S')}.log"
print("=== validate ->", log)
with open(log, "w") as lf:
    p = subprocess.run([sys.executable, "scripts/validate_demo_five_rules.py"], env=env, stdout=lf, stderr=subprocess.STDOUT)
print("exit", p.returncode)
sys.exit(p.returncode)
