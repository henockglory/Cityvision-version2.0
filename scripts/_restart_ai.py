#!/usr/bin/env python3
"""Redémarre le moteur IA — tue tous les uvicorn citevision_ai résiduels."""
import json
import subprocess
import time
import urllib.request

ROOT = "/home/gheno/citevision-v2"
PID_FILE = f"{ROOT}/logs/ai-engine.pid"
LOG_FILE = f"{ROOT}/logs/ai-engine.log"


def kill_all_ai() -> None:
    subprocess.run(["pkill", "-f", "uvicorn citevision_ai.main:app"], capture_output=True)
    time.sleep(3)
    # Belt-and-suspenders: kill pid file if still alive
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        subprocess.run(["kill", "-9", str(pid)], capture_output=True)
    except Exception:
        pass
    time.sleep(2)


kill_all_ai()
print("Stopped all citevision_ai uvicorn processes")

print("Starting AI engine...")
with open(LOG_FILE, "w") as logf:
    proc = subprocess.Popen(
        ["bash", f"{ROOT}/scripts/run-ai-engine.sh"],
        stdout=logf,
        stderr=subprocess.STDOUT,
        cwd=ROOT,
    )
print(f"Launcher pid={proc.pid}")

# Resolve real uvicorn child pid
uvicorn_pid = None
for _ in range(15):
    time.sleep(1)
    r = subprocess.run(
        ["pgrep", "-f", "uvicorn citevision_ai.main:app"],
        capture_output=True, text=True,
    )
    pids = [int(x) for x in r.stdout.split() if x.strip().isdigit()]
    if pids:
        uvicorn_pid = pids[-1]
        break
if uvicorn_pid:
    with open(PID_FILE, "w") as f:
        f.write(str(uvicorn_pid))
    print(f"AI uvicorn pid={uvicorn_pid}")
else:
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))

for i in range(30):
    time.sleep(2)
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=3)
        data = json.load(resp)
        print(f"AI health: {data.get('status')} (attempt {i + 1})")
        break
    except Exception as e:
        print(f"  waiting... ({e})")
else:
    print("TIMEOUT: AI didn't come up in 60s")
