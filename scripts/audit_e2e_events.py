#!/usr/bin/env python3
"""Quick audit of demo events for E2E validation."""
from __future__ import annotations

import json
import os
import urllib.request

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
ORG = "e312f375-7442-4089-8022-ed232abc09e8"
EMAIL = "glory.henock@hologram.cd"
PASS = "Hologram2026!"


def req(method: str, url: str, token: str | None = None, body: dict | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]
    re = req("GET", "http://127.0.0.1:8010/health")
    print("rules-engine:", re)
    for et in (
        "traffic_light_state",
        "red_light_violation",
        "speeding",
        "line_cross",
        "seatbelt_violation",
        "phone_use_violation",
    ):
        try:
            rows = req("GET", f"{API}/api/v1/orgs/{ORG}/events?limit=50&event_type={et}", token)
        except Exception as exc:
            print(f"{et}: error {exc}")
            continue
        if not isinstance(rows, list):
            rows = rows.get("items", []) if isinstance(rows, dict) else []
        demo = 0
        for e in rows:
            p = e.get("payload") or {}
            if isinstance(p, str):
                p = json.loads(p) if p.startswith("{") else {}
            if p.get("demo") is True:
                demo += 1
        print(f"{et}: total={len(rows)} demo={demo}")


if __name__ == "__main__":
    main()
