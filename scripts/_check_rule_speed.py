#!/usr/bin/env python3
import json, urllib.request
API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
body = json.dumps({"email": "glory.henock@hologram.cd", "password": "Hologram2026!"}).encode()
tok = json.loads(urllib.request.urlopen(urllib.request.Request(API + "/api/v1/auth/login", data=body, headers={"Content-Type": "application/json"})).read())["access_token"]
h = {"Authorization": f"Bearer {tok}"}
rules = json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules", headers=h)).read())
for r in rules:
    if "vitesse" in r.get("name", "").lower():
        b = (r.get("definition") or {}).get("bindings") or {}
        print(r["name"], "enabled=", r.get("is_enabled"), "speed_kmh=", b.get("speed_kmh"), "zone=", b.get("zone_name"))
