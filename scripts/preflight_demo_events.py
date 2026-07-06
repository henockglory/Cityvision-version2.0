#!/usr/bin/env python3
"""Quick snapshot of demo events for E2E preflight."""
from __future__ import annotations

import json
import os
import urllib.request

API = os.environ.get("BACKEND_API_URL", "http://localhost:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
ORG = os.environ.get("DEMO_ORG_ID", "e312f375-7442-4089-8022-ed232abc09e8")


def req(method: str, url: str, token: str | None = None, body: dict | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        return json.loads(resp.read().decode())


def payload(e: dict) -> dict:
    p = e.get("payload") or {}
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except json.JSONDecodeError:
            p = {}
    return p


def main() -> None:
    login = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})
    token = login["access_token"]
    rows = req("GET", f"{API}/api/v1/orgs/{ORG}/events?limit=500", token)
    if isinstance(rows, dict):
        rows = rows.get("items", [])
    types = [
        "traffic_light_state",
        "red_light_violation",
        "speeding",
        "line_cross",
        "phone_use_violation",
        "seatbelt_violation",
    ]
    counts: dict[str, int] = {t: 0 for t in types}
    demo_counts: dict[str, int] = {t: 0 for t in types}
    for e in rows or []:
        p = payload(e)
        et = p.get("event_type") or e.get("event_type") or ""
        if et not in counts:
            continue
        counts[et] += 1
        if p.get("demo") is True:
            demo_counts[et] += 1
    print("org", ORG)
    for t in types:
        print(f"  {t}: total={counts[t]} demo={demo_counts[t]}")


if __name__ == "__main__":
    main()
