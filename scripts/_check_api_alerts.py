#!/usr/bin/env python3
import json, urllib.request, urllib.parse, urllib.error

BASE = "http://127.0.0.1:8081"

# Login
login_data = json.dumps({"email": "glory.henock@hologram.cd", "password": "Citevision2024!"}).encode()
req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=login_data,
                              headers={"Content-Type": "application/json"})
try:
    resp = json.load(urllib.request.urlopen(req, timeout=10))
    token = resp.get("access_token", "")
    print(f"Login OK, token: {token[:20]}...")
except Exception as e:
    print(f"Login FAIL: {e}")
    exit(1)

headers = {"Authorization": f"Bearer {token}"}

# Get alerts
req2 = urllib.request.Request(f"{BASE}/api/v1/alerts?status=open&limit=50&include_incomplete=true",
                               headers=headers)
try:
    d = json.load(urllib.request.urlopen(req2, timeout=10))
    alerts = d.get("alerts") or d.get("data") or (d if isinstance(d, list) else [])
    print(f"\nAlertes via API: {len(alerts)}")
    for a in alerts[:10]:
        has_clip = bool((a.get("evidence_snapshot") or {}).get("package", {}).get("clip", {}).get("url") or
                        (a.get("evidence_snapshot") or {}).get("package", {}).get("clip", {}).get("asset_id"))
        n_img = len(((a.get("evidence_snapshot") or {}).get("package") or {}).get("images") or [])
        print(f"  {a.get('id','?')[:8]}  {a.get('created_at','?')[:19]}  status={a.get('status')}  clip={has_clip}  imgs={n_img}")
except Exception as e:
    print(f"Alerts FAIL: {e}")
    import traceback; traceback.print_exc()

# Get events
req3 = urllib.request.Request(f"{BASE}/api/v1/events?limit=20&type=speeding", headers=headers)
try:
    d = json.load(urllib.request.urlopen(req3, timeout=10))
    events = d.get("events") or d.get("data") or (d if isinstance(d, list) else [])
    print(f"\nEvents speeding via API: {len(events)}")
    for e in events[:10]:
        print(f"  {e.get('id','?')[:8]}  {e.get('created_at','?')[:19]}  type={e.get('type')}")
except Exception as e:
    print(f"Events FAIL: {e}")
