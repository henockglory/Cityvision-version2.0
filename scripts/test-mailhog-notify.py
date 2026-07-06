#!/usr/bin/env python3
"""Send test email via backend internal notify (MailHog)."""
import json
import os
import urllib.request

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
ORG = os.environ.get("DEMO_ORG_ID", "e312f375-7442-4089-8022-ed232abc09e8")
KEY = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
TO = os.environ.get("ALERT_EMAIL_TO", "glory.henock@hologram.cd")

body = json.dumps({
    "to": TO,
    "subject": "CitéVision — test MailHog démo",
    "message": "Test SMTP MailHog",
    "title": "Test démo",
    "rule_name": "Test",
    "severity": "info",
    "payload": {"event_type": "test", "demo": True},
}).encode()

req = urllib.request.Request(
    f"{API}/api/v1/internal/orgs/{ORG}/notify/email",
    data=body,
    headers={"Content-Type": "application/json", "X-Internal-Key": KEY},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        print("notify:", resp.status, resp.read().decode()[:200])
except urllib.error.HTTPError as e:
    print("ERR", e.code, e.read().decode()[:300])

mh = json.loads(urllib.request.urlopen("http://127.0.0.1:8025/api/v2/messages?limit=1").read())
print("MailHog total:", mh.get("total"))
