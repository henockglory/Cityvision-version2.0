#!/usr/bin/env python3
import urllib.request, json, sys

with urllib.request.urlopen("http://127.0.0.1:8001/cameras", timeout=8) as r:
    d = json.loads(r.read())

cams = d.get("cameras") or []
if cams:
    print("Keys:", list(cams[0].keys()))
    print("Full cam[0]:", json.dumps(cams[0], default=str)[:500])
else:
    print("No cameras")
