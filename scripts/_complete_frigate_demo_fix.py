#!/usr/bin/env python3
import json, subprocess, time, urllib.request

INTERNAL = "changeme_internal_service_key"

def post(path):
    req = urllib.request.Request(
        f"http://127.0.0.1:8081{path}",
        data=b"",
        method="POST",
        headers={"X-Internal-Key": INTERNAL},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode()

# 1) Frigate up for rebuild
subprocess.run(["docker", "start", "citevision-v2-frigate"], check=False)
for _ in range(30):
    try:
        urllib.request.urlopen("http://127.0.0.1:5000/api/version", timeout=3)
        print("frigate up")
        break
    except Exception:
        time.sleep(2)
else:
    print("WARN: frigate slow")

print("rebuild:", post("/api/v1/internal/ingest/frigate/rebuild"))

# show go2rtc header from config
with open("/home/gheno/citevision-v2/infra/frigate-config/config.yml") as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if line.startswith("go2rtc:"):
        for j in range(i, min(i + 15, len(lines))):
            print(lines[j].rstrip())
        break

subprocess.run(["docker", "restart", "citevision-v2-frigate"], check=False)
time.sleep(25)

stats = json.loads(urllib.request.urlopen("http://127.0.0.1:5000/api/stats", timeout=10).read())
print("cameras:", len(stats.get("cameras") or {}))
for k, v in sorted((stats.get("cameras") or {}).items()):
    if k.startswith("cv_"):
        print(k, "cam_fps=", v.get("camera_fps"), "det=", v.get("detection_fps"))

subprocess.run(["sudo", "lsof", "-i", ":1984", "-i", ":1985", "-i", ":8554", "-i", ":8557"], check=False)

# activate feux + resync
login = json.loads(urllib.request.urlopen(
    urllib.request.Request(
        "http://127.0.0.1:8081/api/v1/auth/login",
        data=json.dumps({"email": "glory.henock@hologram.cd", "password": "Henockglory@03"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    ), timeout=30,
).read())
org = json.loads(urllib.request.urlopen(
    urllib.request.Request(
        "http://127.0.0.1:8081/api/v1/auth/me",
        headers={"Authorization": "Bearer " + login["access_token"]},
    ), timeout=30,
).read())["org_id"]
body = json.dumps({
    "active_video_id": "aaea7c30-1c4c-4ce5-9cd6-4b1f8ded4118",
    "active_camera_id": None,
    "source_mode": "video",
}).encode()
urllib.request.urlopen(urllib.request.Request(
    f"http://127.0.0.1:8081/api/v1/orgs/{org}/demo/settings",
    data=body,
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + login["access_token"]},
    method="PATCH",
), timeout=30)
print("activated feux video")
print("resync:", post("/api/v1/internal/ingest/resync-spatial"))
