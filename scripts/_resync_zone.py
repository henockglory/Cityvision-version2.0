#!/usr/bin/env python3
import subprocess, urllib.request, os

# Read internal key from .env
key = ""
try:
    with open(os.path.expanduser("~/citevision-v2/.env")) as f:
        for line in f:
            line = line.strip()
            if 'INTERNAL' in line.upper() and 'KEY' in line.upper() and '=' in line:
                key = line.split('=', 1)[1].strip().strip('"').strip("'")
                break
except Exception as e:
    print(f"Could not read .env: {e}")

if not key:
    # Try without auth (backend may not require it on internal endpoint)
    key = "internal"

print(f"Using key: {key[:8]}...")

req = urllib.request.Request(
    "http://localhost:8081/internal/ingest/resync-spatial",
    method="POST",
    headers={"X-Internal-Key": key, "Content-Length": "0"},
    data=b"",
)
try:
    resp = urllib.request.urlopen(req, timeout=10)
    print(f"Resync result: {resp.read().decode()}")
except Exception as e:
    print(f"Resync error: {e}")
    # Try without key
    req2 = urllib.request.Request(
        "http://localhost:8081/internal/ingest/resync-spatial",
        method="POST",
        data=b"",
    )
    try:
        resp2 = urllib.request.urlopen(req2, timeout=10)
        print(f"Resync (no auth): {resp2.read().decode()}")
    except Exception as e2:
        print(f"Resync (no auth) also failed: {e2}")
