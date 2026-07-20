#!/usr/bin/env python3
import json
import subprocess
import urllib.request

API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"

body = json.dumps({"email": "glory.henock@hologram.cd", "password": "Hologram2026!"}).encode()
req = urllib.request.Request(API + "/api/v1/auth/login", data=body, headers={"Content-Type": "application/json"})
tok = json.loads(urllib.request.urlopen(req).read())["access_token"]
h = {"Authorization": f"Bearer {tok}"}

for path in [
    f"/api/v1/orgs/{ORG}/alerts?limit=20&include_incomplete=true",
    f"/api/v1/orgs/{ORG}/alerts?limit=20&include_incomplete=true&status=open",
    f"/api/v1/orgs/{ORG}/events?limit=20&event_type=speeding&include_incomplete=true",
]:
    req = urllib.request.Request(API + path, headers=h)
    try:
        data = json.loads(urllib.request.urlopen(req).read().decode())
        print(path, "->", len(data) if isinstance(data, list) else data)
    except Exception as e:
        print(path, "ERR", e)

q = """SELECT count(*) FROM alerts WHERE org_id='e312f375-7442-4089-8022-ed232abc09e8' AND title LIKE '%vitesse%';"""
out = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-c", q],
    capture_output=True,
    text=True,
)
print("DB speed alerts:", out.stdout.strip())
