#!/usr/bin/env python3
import json, os, subprocess, urllib.request
API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
CAM = "01ee632c-271c-4e66-ba98-3d1d7e430c09"
key = ""
for line in open(os.path.expanduser("~/citevision-v2/.env")):
    if line.startswith("INTERNAL_API_KEY="):
        key = line.strip().split("=", 1)[1]
        break
req = urllib.request.Request(
    f"{API}/api/v1/internal/ingest/orgs/{ORG}/cameras/{CAM}/spatial-config",
    headers={"X-Internal-Key": key},
)
with urllib.request.urlopen(req, timeout=15) as r:
    d = json.load(r)
for z in d.get("zones", []):
    cfg = (z.get("behavior_config") or {}).get("config") or z.get("behavior_config") or {}
    print(z.get("name"), z.get("behavior"), cfg)
