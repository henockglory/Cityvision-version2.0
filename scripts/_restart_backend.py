#!/usr/bin/env python3
import subprocess, time, os, urllib.request, json

ROOT = "/home/gheno/citevision-v2"
PID_FILE = f"{ROOT}/logs/backend.pid"
LOG_FILE = f"{ROOT}/logs/backend.log"

# Stop
try:
    with open(PID_FILE) as f:
        pid = int(f.read().strip())
    subprocess.run(["kill", str(pid)], capture_output=True)
    print(f"Backend stopped (pid={pid})")
    time.sleep(3)
except Exception as e:
    print(f"Stop: {e}")

# Start
env = os.environ.copy()
env["PATH"] = "/usr/local/go/bin:/home/gheno/go/bin:" + env.get("PATH", "")

proc = subprocess.Popen(
    [f"{ROOT}/backend/bin/citevision-api"],
    stdout=open(LOG_FILE, "a"),
    stderr=subprocess.STDOUT,
    cwd=ROOT,
    env=env,
)
with open(PID_FILE, "w") as f:
    f.write(str(proc.pid))
print(f"Backend started (pid={proc.pid})")

# Wait
for i in range(15):
    time.sleep(2)
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8081/health", timeout=3)
        d = json.load(r)
        print(f"Backend health: {d.get('status')} (attempt {i+1})")
        break
    except Exception as e:
        print(f"  waiting... ({e})")
else:
    print("TIMEOUT")
