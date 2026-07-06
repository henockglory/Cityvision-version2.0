#!/usr/bin/env python3
"""Manual demo checklist: health → enable speed rule → alert + mail + full evidence package."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = os.environ.get("BACKEND_API_URL", "http://localhost:8081")
MAILHOG = os.environ.get("MAILHOG_PUBLIC_URL", "http://localhost:8025")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
DEMO_ORG = os.environ.get("DEMO_ORG_ID", "e312f375-7442-4089-8022-ed232abc09e8")
RULE_NAME = "Démo · Excès de vitesse"
TIMEOUT = int(os.environ.get("RULE_TIMEOUT_SEC", "420"))
SYNC_WAIT = int(os.environ.get("RULE_SYNC_WAIT_SEC", "35"))


def req(method: str, url: str, token: str | None = None, body: dict | None = None) -> dict | list:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def health(name: str, url: str) -> None:
    with urllib.request.urlopen(url, timeout=10) as resp:
        if resp.status >= 400:
            raise SystemExit(f"[FAIL] {name} HTTP {resp.status}")
    print(f"[OK] {name}")


def mail_count() -> int:
    try:
        with urllib.request.urlopen(f"{MAILHOG}/api/v2/messages?limit=1", timeout=5) as resp:
            return int(json.loads(resp.read()).get("total", 0))
    except Exception:
        return 0


def package_complete(snap: dict | None) -> bool:
    if not snap:
        return False
    pkg = snap.get("package") or {}
    if isinstance(pkg, str):
        try:
            pkg = json.loads(pkg)
        except json.JSONDecodeError:
            return False
    clip = pkg.get("clip") or {}
    has_clip = bool(clip.get("url") or clip.get("asset_id"))
    images = pkg.get("images") or []
    roles = {im.get("role") for im in images if isinstance(im, dict) and (im.get("url") or im.get("asset_id"))}
    return has_clip and "scene" in roles and "subject" in roles


def main() -> int:
    print("==> 1/5 Health gates")
    health("backend", f"{API}/health")
    health("ai-engine", f"http://localhost:{os.environ.get('AI_ENGINE_PORT', '8001')}/health")
    health("rules-engine", f"http://localhost:{os.environ.get('RULES_ENGINE_PORT', '8010')}/health")
    try:
        health("mailhog", f"{MAILHOG}/api/v2/messages?limit=1")
    except Exception as exc:
        print(f"[WARN] MailHog: {exc}")

    print("==> 2/5 force-spatial-reload")
    subprocess.run(["bash", str(ROOT / "scripts/force-spatial-reload.sh")], check=False)

    token = req("POST", f"{API}/api/v1/auth/login", body={"email": EMAIL, "password": PASS})["access_token"]
    org = DEMO_ORG
    rules = req("GET", f"{API}/api/v1/orgs/{org}/rules", token)
    if not isinstance(rules, list):
        rules = []
    rule = next((r for r in rules if r.get("name") == RULE_NAME), None)
    if not rule:
        print(f"[FAIL] Rule not found: {RULE_NAME}")
        return 1

    for r in rules:
        if str(r.get("name", "")).startswith("Démo"):
            req("PATCH", f"{API}/api/v1/orgs/{org}/rules/{r['id']}", token, {"is_enabled": False})
    time.sleep(5)

    print(f"==> 3/5 Enable {RULE_NAME}")
    req("PATCH", f"{API}/api/v1/orgs/{org}/rules/{rule['id']}", token, {"is_enabled": True})
    print(f"    sync wait {SYNC_WAIT}s…")
    time.sleep(SYNC_WAIT)

    mail_before = mail_count()
    deadline = time.time() + TIMEOUT
    ok_alert = ok_mail = ok_pkg = False

    print("==> 4/5 Wait alert + evidence + mail")
    while time.time() < deadline:
        alerts = req(
            "GET",
            f"{API}/api/v1/orgs/{org}/alerts?limit=50&include_incomplete=true",
            token,
        )
        if not isinstance(alerts, list):
            alerts = alerts.get("items", []) if isinstance(alerts, dict) else []
        for a in alerts:
            if a.get("rule_id") != rule["id"]:
                continue
            snap = a.get("evidence_snapshot") or (a.get("metadata") or {}).get("evidence_snapshot")
            if snap and isinstance(snap, str):
                try:
                    snap = json.loads(snap)
                except json.JSONDecodeError:
                    snap = {}
            ok_alert = True
            ok_pkg = package_complete(snap if isinstance(snap, dict) else None)
            if ok_pkg:
                break
        if ok_alert and ok_pkg:
            break
        time.sleep(8)

    for _ in range(12):
        if mail_count() > mail_before:
            ok_mail = True
            break
        time.sleep(5)

    print("==> 5/5 Disable rule (handoff)")
    req("PATCH", f"{API}/api/v1/orgs/{org}/rules/{rule['id']}", token, {"is_enabled": False})

    checks = [
        ("alert", ok_alert),
        ("evidence_package (clip+scene+subject)", ok_pkg),
        ("mail", ok_mail),
    ]
    print("\n=== Manual checklist (Excès de vitesse) ===")
    all_ok = True
    for label, ok in checks:
        mark = "✅" if ok else "❌"
        print(f"  {mark} {label}")
        all_ok = all_ok and ok

    if all_ok:
        print("\nPASS — Prêt pour démo manuelle UI (/rules → /demo → MailHog)")
        return 0
    print("\nFAIL — Voir logs backend/rules-engine et force-spatial-reload.sh")
    return 1


if __name__ == "__main__":
    sys.exit(main())
