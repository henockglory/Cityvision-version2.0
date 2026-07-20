#!/usr/bin/env python3
"""E1: verifie qu'un asset evidence (subject.jpg) est servi par l'API backend."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "")


def main() -> int:
    body = json.dumps({"email": EMAIL, "password": PASS}).encode()
    req = urllib.request.Request(
        f"{API}/api/v1/auth/login", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        token = json.loads(resp.read())["access_token"]

    sql = (
        "SELECT org_id::text, evidence_snapshot->'package'->'images'->1->>'asset_id' "
        "FROM events WHERE event_type='speeding' AND evidence_snapshot ? 'package' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )
    out = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision",
         "-d", "citevision", "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    if not out or "|" not in out:
        print(f"[FAIL] pas d'evenement avec package: {out!r}")
        return 1
    org_id, asset_id = out.split("|", 1)
    url = f"{API}/api/v1/orgs/{org_id}/evidence/asset?key={urllib.parse.quote(asset_id, safe='')}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read()
    ok = len(data) > 1024 and data[:2] == b"\xff\xd8"
    print(f"asset={asset_id}")
    print(f"[{'OK' if ok else 'FAIL'}] {len(data)} octets, JPEG={data[:2] == bytes([0xFF, 0xD8])}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
