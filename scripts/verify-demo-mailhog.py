#!/usr/bin/env python3
"""Verify demo org has email routing and send test via backend notify."""
import json
import os
import urllib.request

API = "http://127.0.0.1:8081"
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")


def req(method, url, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
token = login["access_token"]
org = req("GET", f"{API}/api/v1/orgs/{ORG}", token=token)
print("org default_email_to:", org.get("default_email_to"))
rules = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", token=token)
demo = [r for r in rules if str(r.get("name", "")).startswith("Démo")]
for r in demo:
    actions = r.get("actions") or []
    has_notify = any(a.get("type") == "notify" for a in actions)
    print(f"  {r['name']}: enabled={r.get('is_enabled')} notify={has_notify}")

# Test SMTP via settings if endpoint exists
try:
    req("POST", f"{API}/api/v1/orgs/{ORG}/settings/test-email", token=token, body={"to": EMAIL})
    print("test-email: OK")
except urllib.error.HTTPError as e:
    print(f"test-email: HTTP {e.code} {e.read().decode()[:200]}")

mh_before = req("GET", "http://127.0.0.1:8025/api/v2/messages?limit=1")
print("MailHog before:", mh_before.get("total", 0))
