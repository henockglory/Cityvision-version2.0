#!/usr/bin/env python3
import json, os, urllib.request

def load_env(path):
    if not os.path.isfile(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env(os.path.expanduser("~/citevision-v2/.env"))
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
KEY = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
ORG = os.environ.get("DEMO_ORG_ID", "e312f375-7442-4089-8022-ed232abc09e8")

def post(url, body, headers=None):
    data = json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode()[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]

def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, r.read().decode()[:500]

print("PUBLIC_API_BASE", os.environ.get("PUBLIC_API_BASE", "(unset)"))
print("DEMO_ORG_ID", ORG)
st, body = post(f"{API}/api/v1/auth/login", {"email": EMAIL, "password": PASS})
print("login", st, body[:120])
if st >= 400:
    raise SystemExit(1)
token = json.loads(body)["access_token"]
st, body = get(f"{API}/api/v1/orgs/{ORG}/cameras", {"Authorization": f"Bearer {token}"})
print("cameras", st, body[:400])
st, body = post(
    f"{API}/api/v1/internal/orgs/{ORG}/notify/email",
    {"to": EMAIL, "subject": "test", "message": "test", "title": "t", "rule_name": "r", "severity": "info", "payload": {}},
    {"X-Internal-Key": KEY},
)
print("notify", st, body[:200])
