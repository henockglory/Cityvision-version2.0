#!/usr/bin/env python3
"""Mini intégration import modèle ONNX org — API + menu capabilities + reload IA."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

API = os.environ.get("CV_API", "http://127.0.0.1:8081/api/v1")
AI = os.environ.get("CV_AI", "http://127.0.0.1:8001")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
MODEL_ID = os.environ.get("TEST_MODEL_ID", "test_stub_model")


def req(method: str, url: str, data: bytes | None = None, headers: dict | None = None) -> tuple[int, dict | str]:
    h = {"Accept": "application/json", **(headers or {})}
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            body = resp.read().decode()
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body


def login() -> tuple[str, str]:
    code, payload = req(
        "POST",
        f"{API}/auth/login",
        json.dumps({"email": EMAIL, "password": PASSWORD}).encode(),
        {"Content-Type": "application/json"},
    )
    if code != 200:
        raise SystemExit(f"login failed {code}: {payload}")
    token = payload.get("access_token") or payload.get("token")
    if not token:
        raise SystemExit(f"login missing token: {payload}")
    code_me, me = req("GET", f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    org = me.get("org_id") if code_me == 200 and isinstance(me, dict) else None
    if not org:
        org = payload.get("org_id") or payload.get("organization_id")
    if not org:
        raise SystemExit("org_id not resolved")
    return token, org


def multipart_upload(token: str, org: str, onnx_path: str) -> dict:
    boundary = "----citevisiontest"
    fields = {
        "id": MODEL_ID,
        "task": "classification",
        "event_type": f"{MODEL_ID}_violation",
        "label_fr": "Modèle test intégration",
        "label_en": "Integration test model",
        "human_description_fr": "Stub ONNX pour test import wizard",
        "applies_to": "zone",
        "input_source": "crop_vehicle",
        "input_size": "224",
        "capability": "beta",
        "classes": json.dumps(["negative", "positive"]),
        "positive_classes": json.dumps(["positive"]),
    }
    body = bytearray()
    for k, v in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        body.extend(f"{v}\r\n".encode())
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="model"; filename="{MODEL_ID}.onnx"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n".encode()
    )
    body.extend(open(onnx_path, "rb").read())
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    code, payload = req(
        "POST",
        f"{API}/orgs/{org}/ai/models",
        bytes(body),
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    if code not in (200, 201):
        raise SystemExit(f"upload failed {code}: {payload}")
    return payload


def main() -> int:
    if not PASSWORD:
        print("SKIP: set ADMIN_PASSWORD", file=sys.stderr)
        return 0
    token, org = login()
    stub = tempfile.NamedTemporaryFile(suffix=".onnx", delete=False)
    stub.write(b"\x00" * 128)
    stub.close()
    try:
        up = multipart_upload(token, org, stub.name)
        print("upload:", json.dumps(up, indent=2))
        code, listed = req("GET", f"{API}/orgs/{org}/ai/models", headers={"Authorization": f"Bearer {token}"})
        assert code == 200, listed
        ids = [m["id"] for m in listed.get("models", [])]
        assert MODEL_ID in ids, f"model not listed: {ids}"
        code, menu = req("GET", f"{API}/orgs/{org}/capabilities/menu", headers={"Authorization": f"Bearer {token}"})
        assert code == 200, menu
        beh = [b["id"] for b in menu.get("behaviors", [])]
        assert f"custom:{MODEL_ID}" in beh, f"behavior missing in menu: {beh[-5:]}"
        code, reload = req("POST", f"{AI}/admin/reload-secondary-models")
        print("ai reload:", code, reload)
        code, health = req("GET", f"{AI}/health")
        hk = f"{MODEL_ID}_model_loaded"
        print(f"health[{hk}]=", health.get(hk) if isinstance(health, dict) else health)
        print("OK — import + menu + reload chain")
        return 0
    finally:
        os.unlink(stub.name)


if __name__ == "__main__":
    raise SystemExit(main())
