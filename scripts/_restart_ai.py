#!/usr/bin/env python3
"""Redémarre le moteur IA en chargeant le nouveau plate.py."""
import subprocess, time, os

ROOT = "/home/gheno/citevision-v2"
PID_FILE = f"{ROOT}/logs/ai-engine.pid"
LOG_FILE = f"{ROOT}/logs/ai-engine.log"

# Stop existing AI
try:
    with open(PID_FILE) as f:
        pid = int(f.read().strip())
    r = subprocess.run(["kill", str(pid)], capture_output=True)
    print(f"AI stopped (pid={pid}): {r.returncode}")
    time.sleep(4)
except Exception as e:
    print(f"Stop: {e}")

# Start new AI
print("Starting AI engine...")
proc = subprocess.Popen(
    ["bash", f"{ROOT}/scripts/run-ai-engine.sh"],
    stdout=open(LOG_FILE, "w"),
    stderr=subprocess.STDOUT,
    cwd=ROOT,
)
with open(PID_FILE, "w") as f:
    f.write(str(proc.pid))
print(f"AI started (pid={proc.pid})")

# Wait for it to come up
for i in range(30):
    time.sleep(2)
    try:
        import urllib.request
        r = urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=3)
        import json
        d = json.load(r)
        print(f"AI health: {d.get('status')} (attempt {i+1})")
        break
    except Exception as e:
        print(f"  waiting... ({e})")
else:
    print("TIMEOUT: AI didn't come up in 60s")
