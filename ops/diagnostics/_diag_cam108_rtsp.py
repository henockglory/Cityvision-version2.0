#!/usr/bin/env python3
import json
import subprocess
import urllib.request

CAM108 = "37c7d7fa-12dc-450c-8c4b-ab63ed43a819"

def get(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read().decode())

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True,
    )
    return (r.stdout or r.stderr).strip()

print("=== AI /cameras cam108 ===")
try:
    cams = get("http://127.0.0.1:8001/cameras").get("cameras", [])
    cam = next((c for c in cams if c.get("camera_id") == CAM108), None)
    print(json.dumps(cam, indent=2) if cam else "NOT IN AI WORKERS")
except Exception as e:
    print("AI error:", e)

print("\n=== DB camera row ===")
row = psql(
    f"SELECT id::text, name, status, rtsp_url, is_enabled, metadata::text "
    f"FROM cameras WHERE id='{CAM108}';"
)
print(row or "(no row)")

print("\n=== ffprobe RTSP (from WSL) ===")
rtsp = "rtsp://admin:hids+1234@192.168.1.108:554/live"
subprocess.run(["ffprobe", "-rtsp_transport", "tcp", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height", "-of", "json", rtsp], timeout=15)

print("\n=== go2rtc stream cam-108 ===")
try:
    sname = f"cam-{CAM108}"
    with urllib.request.urlopen(f"http://127.0.0.1:1984/api/streams?src={sname}", timeout=10) as r:
        print(r.read().decode()[:500])
except Exception as e:
    print("missing:", e)

print("\n=== AI log tail (108/rtsp) ===")
subprocess.run(["bash", "-lc", "grep -E '108|37c7d7fa|rtsp|RTSP' ~/citevision-v2/logs/ai-engine.log 2>/dev/null | tail -15 || tail -5 ~/citevision-v2/logs/ai-engine.log"])
