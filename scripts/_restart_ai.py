#!/usr/bin/env python3
"""Redémarre le moteur IA — utilise start_bg (setsid) pour processus persistant."""
import json
import subprocess
import sys
import time
import urllib.request

ROOT = "/home/gheno/citevision-v2"


def main() -> int:
    r = subprocess.run(
        ["bash", f"{ROOT}/scripts/_restart_ai_cuda.sh"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    print(r.stdout or "", end="")
    if r.stderr:
        print(r.stderr, file=sys.stderr, end="")

    for i in range(40):
        time.sleep(3)
        try:
            resp = urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=5)
            data = json.load(resp)
            ok = str(data.get("models_all_ok", "")).lower() == "true"
            print(f"AI health: {data.get('status')} models_all_ok={data.get('models_all_ok')} (attempt {i + 1})")
            if ok:
                return 0
        except Exception as e:
            print(f"  waiting... ({e})")
    print("TIMEOUT: AI stack not fully healthy in 120s")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
