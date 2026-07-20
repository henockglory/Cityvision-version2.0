#!/usr/bin/env python3
"""Preflight gate: infra, AI models, evidence API, MailHog reachability."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081")
AI = os.environ.get("AI_ENGINE_URL", f"http://127.0.0.1:{os.environ.get('AI_ENGINE_PORT', '8001')}")
MAILHOG = os.environ.get("MAILHOG_PUBLIC_URL", "http://127.0.0.1:8025")
MINIO = os.environ.get("MINIO_ENDPOINT", "http://127.0.0.1:9003")
ORG = os.environ.get("DEMO_ORG_ID", "")
KEY = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")
PUBLIC_API = os.environ.get("PUBLIC_API_BASE", "")
CEINTURE = os.environ.get("DEMO_CEINTURE_CAMERA_ID", "")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL {msg}", file=sys.stderr)


def get_json(url: str, headers: dict | None = None, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def post_json(url: str, body: dict, headers: dict | None = None, timeout: int = 30) -> tuple[int, dict | str]:
    data = json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, raw


def resolve_ceinture_camera(token: str, org: str) -> str:
    try:
        cams = get_json(
            f"{API}/api/v1/orgs/{org}/cameras",
            headers={"Authorization": f"Bearer {token}"},
        )
        if isinstance(cams, list):
            for c in cams:
                name = str(c.get("name", "")).lower()
                if "ceinture" in name:
                    return str(c["id"])
    except Exception:
        pass
    return CEINTURE


def main() -> int:
    print("==> preflight demo pipeline")
    errors = 0

    if not PUBLIC_API:
        fail("PUBLIC_API_BASE not set")
        errors += 1
    else:
        ok(f"PUBLIC_API_BASE={PUBLIC_API}")

    try:
        urllib.request.urlopen(f"{MINIO}/minio/health/live", timeout=5)
        ok(f"MinIO reachable at {MINIO}")
    except Exception as exc:
        fail(f"MinIO unreachable ({MINIO}): {exc}")
        errors += 1

    try:
        get_json(f"{MAILHOG}/api/v2/messages?limit=1")
        ok(f"MailHog reachable at {MAILHOG}")
    except Exception as exc:
        fail(f"MailHog unreachable: {exc}")
        errors += 1

    try:
        get_json(f"{API}/health")
        ok("Backend /health")
    except Exception as exc:
        fail(f"Backend /health: {exc}")
        errors += 1

    try:
        ai = get_json(f"{AI}/health")
        for k in ("yolo_loaded", "driver_phone_model_loaded", "seatbelt_model_loaded"):
            if str(ai.get(k, "")).lower() != "true":
                fail(f"AI /health {k} not true")
                errors += 1
            else:
                ok(f"AI {k}")
    except Exception as exc:
        fail(f"AI /health: {exc}")
        errors += 1

    login = post_json(f"{API}/api/v1/auth/login", {"email": EMAIL, "password": PASS})
    if login[0] >= 400:
        fail(f"login HTTP {login[0]}")
        return 1
    token = login[1]["access_token"]  # type: ignore[index]
    org = ORG
    if not org:
        me = get_json(
            f"{API}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        org = str(me.get("org_id") or "")
    if not org:
        fail("unable to resolve org_id from /auth/me")
        return 1

    try:
        preflight = get_json(
            f"{API}/api/v1/orgs/{org}/demo/preflight",
            headers={"Authorization": f"Bearer {token}"},
        )
        if preflight.get("blocked"):
            fail(f"demo/preflight blocked: {preflight.get('suppression_reason', 'unknown')}")
            errors += 1
        else:
            ok("demo/preflight ready")
    except Exception as exc:
        fail(f"demo/preflight endpoint failed: {exc}")
        errors += 1

    cam_id = resolve_ceinture_camera(token, org)
    if not cam_id:
        fail("no ceinture camera found for evidence test")
        errors += 1
    else:
        event_id = str(uuid.uuid4())
        evidence_body = {
            "camera_id": cam_id,
            "event": {
                "event_id": event_id,
                "camera_id": cam_id,
                "event_type": "seatbelt_violation",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "track_id": 1,
                "class_name": "car",
                "confidence": 0.9,
                "metadata": {"demo": True},
            },
            "evidence": {
                "enabled": True,
                "clip_seconds": 6,
                "images": [{"role": "scene"}, {"role": "subject"}],
            },
        }
        status, resp = post_json(
            f"{API}/api/v1/internal/orgs/{org}/evidence/request",
            evidence_body,
            headers={"X-Internal-Key": KEY},
            timeout=45,
        )
        if status == 404:
            fail(f"evidence/request HTTP 404 (camera {cam_id[:8]} not running?)")
            errors += 1
        elif status >= 400:
            fail(f"evidence/request HTTP {status}: {str(resp)[:200]}")
            errors += 1
        elif isinstance(resp, dict) and (resp.get("package") or resp.get("evidence")):
            ok("evidence/request returned package or evidence payload")
        else:
            print(f"  WARN evidence/request HTTP {status} — partial/empty (demo degraded OK): {str(resp)[:120]}")

    notify_body = {
        "to": os.environ.get("ALERT_EMAIL_TO", EMAIL),
        "subject": "CitéVision preflight",
        "message": "preflight",
        "title": "Preflight démo",
        "rule_name": "Preflight",
        "severity": "info",
        "payload": {
            "event_type": "seatbelt_violation",
            "demo": True,
            "package": {"images": []},
        },
    }
    n_status, n_resp = post_json(
        f"{API}/api/v1/internal/orgs/{org}/notify/email",
        notify_body,
        headers={"X-Internal-Key": KEY},
    )
    if n_status >= 400:
        fail(f"notify/email HTTP {n_status}")
        errors += 1
    else:
        ok("notify/email accepted")

    try:
        mh = get_json(f"{MAILHOG}/api/v2/messages?limit=1")
        total = int(mh.get("total", 0))
        if total < 1:
            fail("MailHog has no messages after notify")
            errors += 1
        else:
            items = mh.get("items") or []
            html = ""
            if items:
                content = (items[0].get("Content") or {}).get("Body", "")
                html = content if isinstance(content, str) else ""
            if html.strip():
                ok(f"MailHog HTML non-empty (total={total})")
            else:
                print("  WARN MailHog message body empty (SMTP timing?)")
    except Exception as exc:
        fail(f"MailHog verify: {exc}")
        errors += 1

    if errors:
        print(f"\nFAIL preflight ({errors} error(s))")
        return 1
    print("\nPASS preflight demo pipeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
