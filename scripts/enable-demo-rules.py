#!/usr/bin/env python3
"""Re-enable all Démo · * rules after validate_demo handoff."""
from __future__ import annotations

import json
import os
import urllib.request

API = os.environ.get("BACKEND_API_URL", "http://localhost:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Henockglory@03")


def req(method: str, url: str, token: str | None = None, body: dict | None = None) -> dict | list:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def main() -> int:
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]
    me = req("GET", f"{API}/api/v1/auth/me", token)
    org = me.get("org_id", "")
    rules = req("GET", f"{API}/api/v1/orgs/{org}/rules", token)
    if not isinstance(rules, list):
        rules = []
    enabled = 0
    for r in rules:
        name = str(r.get("name", ""))
        if not name.startswith("Démo"):
            continue
        if r.get("is_enabled"):
            print(f"SKIP already on: {name}")
            continue
        req("PATCH", f"{API}/api/v1/orgs/{org}/rules/{r['id']}", token, {"is_enabled": True})
        print(f"ENABLED: {name}")
        enabled += 1
    print(f"Done — {enabled} rule(s) enabled for org {org}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
