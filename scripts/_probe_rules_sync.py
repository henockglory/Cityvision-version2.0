#!/usr/bin/env python3
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env = {}
for line in (ROOT / ".env").read_text(encoding="utf-8", errors="ignore").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

org = env.get("DEFAULT_ORG_ID", "")
key = env.get("INTERNAL_API_KEY", "")
api = env.get("BACKEND_API_URL", "http://localhost:8081")
url = f"{api}/api/v1/internal/orgs/{org}/rules/active"
req = urllib.request.Request(url, headers={"X-Internal-Key": key})
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode())
        print(f"HTTP {r.status} rules={len(data)}")
        for row in data[:8]:
            print(f"  - {row.get('name')} enabled={row.get('is_enabled')}")
except Exception as e:
    print(f"FAIL: {e}")

with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=5) as r:
    print("rules-engine:", r.read().decode())
