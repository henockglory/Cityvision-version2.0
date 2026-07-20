#!/usr/bin/env python3
import json, subprocess, urllib.request, time

def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())

streams = get("http://127.0.0.1:1984/api/streams")
demos = sorted(k for k in streams if k.startswith("demo-"))
print("demo streams:", demos)
print("total streams:", len(streams))

r = subprocess.run(
    ["timeout", "5", "ffprobe", "-v", "error", "-show_entries", "stream=codec_name",
     "-of", "csv=p=0", "rtsp://127.0.0.1:8554/demo-74d51ead-aaea7c30"],
    capture_output=True, text=True,
)
print("ffprobe demo feux:", r.stdout.strip() or r.stderr.strip()[:200])

stats = get("http://127.0.0.1:5000/api/stats")
for k, v in sorted((stats.get("cameras") or {}).items()):
    if k.startswith("cv_"):
        print(k, "fps", v.get("camera_fps"), "det", v.get("detection_fps"))
