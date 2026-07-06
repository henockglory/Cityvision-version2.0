#!/usr/bin/env python3
import json, os, urllib.request
from pathlib import Path
env = {}
for line in Path(".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k,v=line.split("=",1); env[k]=v
org=env["DEFAULT_ORG_ID"]; key=env["INTERNAL_API_KEY"]
url=f"http://127.0.0.1:8081/api/v1/internal/orgs/{org}/rules/active"
req=urllib.request.Request(url, headers={"X-Internal-Key": key})
with urllib.request.urlopen(req) as r:
    data=json.loads(r.read())
print(json.dumps(data[0] if data else {}, indent=2)[:1200])
