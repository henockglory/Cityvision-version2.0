#!/usr/bin/env python3
"""Disable all demo rules + wait for active_rules=0."""
import urllib.request, json, time, sys, os

API = "http://localhost:8081"
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Henockglory@03")

# 1. Login
data = json.dumps({"email": EMAIL, "password": PASS}).encode()
req = urllib.request.Request(f"{API}/api/v1/auth/login", data=data,
                              headers={"Content-Type": "application/json"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        auth = json.loads(r.read())
except Exception as e:
    # Try alternate password
    PASS2 = "Hologram2026!"
    data2 = json.dumps({"email": EMAIL, "password": PASS2}).encode()
    req2 = urllib.request.Request(f"{API}/api/v1/auth/login", data=data2,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req2, timeout=15) as r:
        auth = json.loads(r.read())

token = auth.get("access_token") or auth.get("token")
# org_id may be nested in user dict or come from env
org = (auth.get("org_id")
       or (auth.get("user") or {}).get("org_id")
       or os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466"))
if not token:
    print(f"FAIL: no token in auth resp")
    sys.exit(1)
print(f"org={org[:8]} token=OK")

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# 2. Get rules
req = urllib.request.Request(f"{API}/api/v1/orgs/{org}/rules", headers=headers)
with urllib.request.urlopen(req, timeout=15) as r:
    rules_resp = json.loads(r.read())

rules = rules_resp if isinstance(rules_resp, list) else rules_resp.get("rules", [])
print(f"Total rules: {len(rules)}")

# 3. Disable all demo rules
disabled = 0
for rule in rules:
    name = rule.get("name", "")
    rid = rule.get("id", "")
    enabled = rule.get("is_enabled", False)
    if ("Démo" in name or "Demo" in name) and enabled:
        body = json.dumps({"is_enabled": False}).encode()
        req = urllib.request.Request(f"{API}/api/v1/orgs/{org}/rules/{rid}",
                                     data=body, headers=headers, method="PATCH")
        try:
            urllib.request.urlopen(req, timeout=10)
            print(f"  disabled: {name}")
            disabled += 1
        except Exception as e:
            print(f"  warn {name}: {e}")

print(f"Disabled {disabled} rules")

# 4. Verify rules-engine active_rules=0
for i in range(12):
    time.sleep(3)
    try:
        with urllib.request.urlopen("http://localhost:8010/health", timeout=5) as r:
            h = json.loads(r.read())
        active = int(h.get("active_rules", 1))
        if active == 0:
            print("active_rules=0 confirmed")
            sys.exit(0)
        print(f"  waiting active_rules={active}...")
    except Exception as e:
        print(f"  health check warn: {e}")

print("WARN: active_rules not 0 after 36s")
sys.exit(0)
