#!/usr/bin/env python3
"""Quick check: AI engine health + evidence_backend mode."""
import urllib.request, json, time, sys

for i in range(25):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=5) as r:
            d = json.loads(r.read())
        print(f"AI yolo_loaded={d.get('yolo_loaded')} evidence_backend={d.get('evidence_backend')} yolo_cuda={d.get('yolo_cuda')}")
        sys.exit(0)
    except Exception as e:
        print(f"  wait ({i+1}/25): {e}", flush=True)
        time.sleep(4)
print("TIMEOUT: AI engine did not respond in 100s")
sys.exit(1)
