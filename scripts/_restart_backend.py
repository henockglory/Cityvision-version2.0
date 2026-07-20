#!/usr/bin/env python3
import subprocess, time, os, urllib.request, json
from pathlib import Path

ROOT = "/home/gheno/citevision-v2"
PID_FILE = f"{ROOT}/logs/backend.pid"
LOG_FILE = f"{ROOT}/logs/backend.log"


def _load_dotenv(path: str) -> dict[str, str]:
    """Parse KEY=value from .env without requiring a sourced shell (same idea as AI DEMO_MODE)."""
    out: dict[str, str] = {}
    p = Path(path)
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


# Stop
try:
    with open(PID_FILE) as f:
        pid = int(f.read().strip())
    subprocess.run(["kill", str(pid)], capture_output=True)
    print(f"Backend stopped (pid={pid})")
    time.sleep(3)
except Exception as e:
    print(f"Stop: {e}")

# Start — must inject .env; citevision-api refuses to boot without secrets.
env = os.environ.copy()
env["PATH"] = "/usr/local/go/bin:/home/gheno/go/bin:" + env.get("PATH", "")
for k, v in _load_dotenv(f"{ROOT}/.env").items():
    env.setdefault(k, v)
# cwd is repo root (not backend/), so relative defaults like ../shared/rule-catalog miss.
env.setdefault("RULE_CATALOG_PATH", f"{ROOT}/shared/rule-catalog")
env.setdefault("SHARED_PATH", f"{ROOT}/shared")

proc = subprocess.Popen(
    [f"{ROOT}/backend/bin/citevision-api"],
    stdout=open(LOG_FILE, "a"),
    stderr=subprocess.STDOUT,
    cwd=ROOT,
    env=env,
    start_new_session=True,  # survive parent shell exit (WSL/Cursor tool sessions)
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
