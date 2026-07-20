#!/usr/bin/env python3
import json, subprocess, time, urllib.request

def post(path):
    req = urllib.request.Request(
        f"http://127.0.0.1:8081{path}",
        data=b"",
        method="POST",
        headers={"X-Internal-Key": "changeme_internal_service_key"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode()

print("rebuild:", post("/api/v1/internal/ingest/frigate/rebuild"))

with open("/home/gheno/citevision-v2/infra/frigate-config/config.yml") as f:
    in_go2rtc = False
    for line in f:
        if line.startswith("go2rtc:"):
            in_go2rtc = True
        if in_go2rtc:
            print(line.rstrip())
            if line.strip() and not line.startswith(" ") and not line.startswith("go2rtc:"):
                break

subprocess.run(["docker", "start", "citevision-v2-frigate"], check=False)
time.sleep(25)

stats = json.loads(urllib.request.urlopen("http://127.0.0.1:5000/api/stats", timeout=10).read())
for k, v in sorted((stats.get("cameras") or {}).items()):
    if k.startswith("cv_"):
        print(k, "cam_fps=", v.get("camera_fps"), "det=", v.get("detection_fps"))

subprocess.run(["sudo", "lsof", "-i", ":1984", "-i", ":1985", "-i", ":8554", "-i", ":8557"], check=False)
