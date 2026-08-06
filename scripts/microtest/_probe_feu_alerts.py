#!/usr/bin/env python3
"""Find feu alerts around the HIT window and dump package metadata."""
import json
import os
import urllib.request

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081").rstrip("/")
ORG = os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
SINCE = os.environ.get("HIT1_SINCE", "2026-08-06 10:14:36+00")


def req(method, url, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


tok = req("POST", f"{API}/api/v1/auth/login", {"email": EMAIL, "password": PASS})["access_token"]
print("login ok")

# Try several alert list endpoints / filters
candidates = [
    f"{API}/api/v1/orgs/{ORG}/alerts?limit=20",
    f"{API}/api/v1/orgs/{ORG}/alerts?limit=50&since={urllib.parse.quote(SINCE)}" if False else None,
]
import urllib.parse
urls = [
    f"{API}/api/v1/orgs/{ORG}/alerts?limit=30",
]
for url in urls:
    try:
        data = req("GET", url, token=tok)
    except Exception as exc:
        print("fail", url, exc)
        continue
    items = data if isinstance(data, list) else (data.get("alerts") or data.get("items") or data.get("data") or [])
    print(f"url={url} count={len(items)} type={type(data).__name__}")
    if isinstance(data, dict):
        print("keys", list(data.keys())[:12])
    for a in items[:15]:
        if not isinstance(a, dict):
            continue
        meta = a.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        title = a.get("title") or a.get("message") or a.get("rule_name") or ""
        print(
            "alert",
            str(a.get("alert_id") or a.get("id") or "")[:12],
            "created=", a.get("created_at"),
            "rule=", a.get("rule_name") or a.get("event_type"),
            "cap=", meta.get("capture_source"),
            "scene=", meta.get("scene_light_state"),
            "fe=", str(meta.get("frigate_event_id") or "")[:24],
            "title=", str(title)[:50],
        )

# Also search by known frigate event
print("--- psql ---")
import subprocess
sql = (
    "SELECT a.id::text, a.created_at, a.rule_name, "
    "a.metadata->>'frigate_event_id', a.metadata->>'capture_source', "
    "a.metadata->>'scene_light_state', a.metadata->>'evidence_status' "
    "FROM alerts a WHERE a.org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid "
    "AND a.created_at >= '2026-08-06 10:00:00+00' "
    "ORDER BY a.created_at DESC LIMIT 20;"
)
r = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres",
     "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "|", "-c", sql],
    capture_output=True, text=True, check=False,
)
print(r.stdout or r.stderr)
