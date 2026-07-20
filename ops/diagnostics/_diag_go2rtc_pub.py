#!/usr/bin/env python3
import json, subprocess, sys, time, urllib.request
import numpy as np

print("=== STEP 3 streams after manual ===")
with urllib.request.urlopen("http://127.0.0.1:1984/api/streams") as r:
    d = json.load(r)
print("test-manual-pub" in d, list(d.keys())[:8])

print("=== STEP 4 pipe test ===")
cmd = ["ffmpeg","-loglevel","warning","-y","-f","rawvideo","-pix_fmt","bgr24","-s","1280x720","-r","15","-i","pipe:0","-c:v","libx264","-preset","ultrafast","-tune","zerolatency","-profile:v","baseline","-pix_fmt","yuv420p","-g","15","-bf","0","-f","rtsp","-rtsp_transport","tcp","rtsp://127.0.0.1:8554/test-pipe-pub"]
p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
frame = np.zeros((720,1280,3), dtype=np.uint8)
frame[:,:,1] = 128
err = None
for i in range(30):
    try:
        p.stdin.write(frame.tobytes())
        p.stdin.flush()
    except Exception as e:
        err = e
        break
    time.sleep(1/15)
try:
    p.stdin.close()
except Exception:
    pass
rc = p.wait(timeout=5)
stderr = p.stderr.read().decode(errors="replace") if p.stderr else ""
print("rc", rc, "err", err)
print("stderr", stderr[-800:])

print("=== STEP 5 pipe stream check ===")
with urllib.request.urlopen("http://127.0.0.1:1984/api/streams") as r:
    d = json.load(r)
print("test-pipe-pub" in d, "test-manual-pub" in d, list(d.keys())[:12])

print("=== STEP 6 AI cameras ===")
cid = "d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
found = False
for port in (8000, 8080, 5000, 8001, 9000, 8010):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/cameras", timeout=2) as r:
            raw = r.read()
            print(f"OK port {port} len {len(raw)}")
            data = json.loads(raw)
            cams = data if isinstance(data, list) else data.get("cameras", data.get("items", [data]))
            for c in cams:
                if isinstance(c, dict) and c.get("id") == cid:
                    print(json.dumps(c, indent=2))
                    found = True
                    break
    except Exception as e:
        print(f"port {port}: {type(e).__name__}: {e}")
    if found:
        break
if not found:
    print("camera not found on tried ports")
