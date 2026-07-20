#!/usr/bin/env python3
"""Diagnose speeding pipeline for Ligne Continue demo camera."""
import json
import os
import urllib.request

ORG = "e312f375-7442-4089-8022-ed232abc09e8"
LIGNE = "01ee632c-271c-4e66-ba98-3d1d7e430c09"
API = "http://127.0.0.1:8081"
AI = "http://127.0.0.1:8001"
KEY = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")


def get(url, token=None, headers=None, body=None, method="GET"):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


print("=== AI spatial (live) ===")
sp = get(f"{AI}/cameras/{LIGNE}/spatial")
print(json.dumps(sp, indent=2))

print("\n=== Orchestrator spatial-config ===")
cfg = get(
    f"{API}/api/v1/internal/ingest/orgs/{ORG}/cameras/{LIGNE}/spatial-config",
    headers={"X-Internal-Key": KEY},
)
for z in cfg.get("zones", []):
    print(f"  zone_id={z.get('zone_id')} behavior={z.get('behavior')} config={z.get('behavior_config')}")
    poly = z.get("polygon") or []
    if poly:
        dtn = [p.get("distance_to_next_m") for p in poly if p.get("distance_to_next_m") is not None]
        print(f"    polygon points={len(poly)} calibrated_edges={len(dtn)}")

print("\n=== Rule Démo · Excès de vitesse ===")
login = get(f"{API}/api/v1/auth/login", method="POST", body={"email": EMAIL, "password": PASS})
token = login["access_token"]
rules = get(f"{API}/api/v1/orgs/{ORG}/rules", token=token)
if isinstance(rules, dict):
    rules = rules.get("items", [])
for r in rules:
    if "vitesse" in r.get("name", "").lower():
        d = r.get("definition") or {}
        print(f"  enabled={r.get('is_enabled')} name={r.get('name')}")
        print(f"  bindings={d.get('bindings')}")
        print(f"  condition={d.get('condition')}")

print("\n=== Recent speeding events (all cameras) ===")
events = get(f"{API}/api/v1/orgs/{ORG}/events?limit=200&event_type=speeding", token=token)
if isinstance(events, dict):
    events = events.get("items", [])
print(f"  count={len(events)}")
for e in events[:5]:
    print(f"  {e.get('occurred_at')} cam={e.get('camera_id')} payload={e.get('payload', {}).get('speed_kmh')}")

print("\n=== Recent events Ligne Continue (any type) ===")
all_ev = get(f"{API}/api/v1/orgs/{ORG}/events?limit=100", token=token)
if isinstance(all_ev, dict):
    all_ev = all_ev.get("items", [])
ligne = [e for e in all_ev if e.get("camera_id") == LIGNE]
types: dict[str, int] = {}
for e in ligne:
    et = (e.get("payload") or {}).get("event_type") or e.get("event_type", "?")
    types[et] = types.get(et, 0) + 1
print(f"  total={len(ligne)} types={types}")

print("\n=== Evidence capture rules (orchestrator) ===")
# infer from start camera - check backend logs tail for evidence
import subprocess
try:
    out = subprocess.run(
        ["tail", "-30", os.path.expanduser("~/citevision-v2/logs/backend.log")],
        capture_output=True,
        text=True,
        timeout=5,
    )
    for line in out.stdout.splitlines():
        if "speed" in line.lower() or "evidence" in line.lower() or "hot-reload" in line.lower():
            print(" ", line[:120])
except Exception as ex:
    print("  log skip:", ex)
