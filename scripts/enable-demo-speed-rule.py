#!/usr/bin/env python3
"""Enable only the demo speeding rule and switch active video to Ligne Continue."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("BACKEND_API_URL", "http://localhost:8081")
ORG = os.environ.get("DEMO_ORG_ID", "e312f375-7442-4089-8022-ed232abc09e8")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
SPEED_RULE = "Démo · Excès de vitesse"


def req(method: str, url: str, token: str | None = None, body: dict | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> int:
    tok = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASSWORD})["access_token"]
    rules = req("GET", f"{API}/api/v1/orgs/{ORG}/rules", tok)
    if isinstance(rules, dict):
        rules = rules.get("items", rules.get("rules", []))

    enabled_count = 0
    for rule in rules:
        name = rule.get("name", "")
        if not name.startswith("Démo"):
            continue
        enabled = name == SPEED_RULE
        req("PATCH", f"{API}/api/v1/orgs/{ORG}/rules/{rule['id']}", tok, {"is_enabled": enabled})
        print(f"{name}: enabled={enabled}")
        if enabled:
            enabled_count += 1

    settings = req("GET", f"{API}/api/v1/orgs/{ORG}/demo/settings", tok)
    for video in settings.get("videos", []):
        label = (video.get("name") or "").lower()
        if "continue" in label or "ligne continue" in label:
            req(
                "PATCH",
                f"{API}/api/v1/orgs/{ORG}/demo/settings",
                tok,
                {"active_video_id": video["id"], "source_mode": "video", "active_camera_id": None},
            )
            print(f"active video: {video.get('name')} ({video['id']})")
            break

    deadline = time.time() + 45
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://localhost:8010/health", timeout=5) as resp:
                health = json.loads(resp.read())
            active = int(health.get("active_rules", -1))
            print(f"rules-engine active_rules={active}")
            if active == enabled_count:
                return 0
        except urllib.error.URLError as exc:
            print(f"rules-engine wait: {exc}")
        time.sleep(3)

    print("WARN: rules-engine did not sync in time")
    return 1


if __name__ == "__main__":
    sys.exit(main())
