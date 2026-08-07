#!/usr/bin/env python3
"""Lower Démo · Excès de vitesse binding + zone limit to 1 km/h for 1-hit Frigate validation.
Does NOT rewrite zone geometry (A.1). Only numeric speed_limit / rule binding.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

ORG = os.environ.get("DEMO_ORG_ID", "74d51ead-97a7-4e41-a488-503a9b90c466")
RULE_NAME = os.environ.get("RULE_NAME", "Démo · Excès de vitesse")
TARGET = float(os.environ.get("VITESSE_1HIT_LIMIT_KMH", "1") or 1)
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8081").rstrip("/")
EMAIL = os.environ.get("ADMIN_EMAIL", "glory.henock@hologram.cd")
PASS = os.environ.get("ADMIN_PASSWORD", "Hologram2026!")
INTERNAL = os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")


def psql(sql: str) -> str:
    r = subprocess.run(
        [
            "docker", "exec", "citevision-v2-postgres",
            "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql,
        ],
        capture_output=True, text=True, check=False,
    )
    return (r.stdout or "").strip()


def login() -> str:
    body = json.dumps({"email": EMAIL, "password": PASS}).encode()
    req = urllib.request.Request(
        f"{API}/api/v1/auth/login", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data.get("access_token") or data.get("token") or ""


def main() -> int:
    # Zone config limit (all speed_measurement zones for demo org cameras).
    out = psql(
        "UPDATE zones z SET behavior_config = jsonb_set("
        "COALESCE(behavior_config,'{}'::jsonb),'{config,speed_limit_kmh}',"
        f"to_jsonb({TARGET}::float8),true), updated_at=NOW() "
        "FROM cameras c WHERE c.id=z.camera_id AND c.org_id="
        f"'{ORG}'::uuid AND (z.behavior_config->>'behavior')='speed_measurement' "
        "RETURNING z.name, z.behavior_config->'config'->>'speed_limit_kmh';"
    )
    print(f"zones_patched:\n{out}", flush=True)

    # Rule binding speed_kmh (overlay used by bridge via spatial).
    rid = psql(
        f"SELECT id::text FROM rules WHERE org_id='{ORG}'::uuid AND name='{RULE_NAME}' LIMIT 1;"
    ).splitlines()
    if not rid or not rid[0].strip():
        print(f"[FAIL] rule not found: {RULE_NAME}", flush=True)
        return 2
    rule_id = rid[0].strip()
    psql(
        "UPDATE rules SET definition = jsonb_set("
        "COALESCE(definition,'{}'::jsonb),'{bindings,speed_kmh}',"
        f"to_jsonb({TARGET}::float8),true), updated_at=NOW() WHERE id='{rule_id}'::uuid;"
    )
    print(f"rule_patched id={rule_id[:8]} speed_kmh={TARGET}", flush=True)

    # Resync spatial + Frigate so speed_threshold follows limit when backend supports it.
    try:
        tok = login()
        req = urllib.request.Request(
            f"{API}/api/v1/orgs/{ORG}/cameras",
            headers={"Authorization": f"Bearer {tok}"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            cams = json.loads(resp.read().decode())
        # Trigger internal rebuild
        req2 = urllib.request.Request(
            f"{API}/internal/frigate/rebuild",
            method="POST",
            headers={"X-Internal-Key": INTERNAL},
        )
        try:
            with urllib.request.urlopen(req2, timeout=60) as resp:
                print(f"frigate_rebuild={resp.status}", flush=True)
        except Exception as exc:
            print(f"frigate_rebuild_warn={exc}", flush=True)
        # Push spatial by touching rules sync
        urllib.request.urlopen(
            urllib.request.Request(
                "http://127.0.0.1:8010/internal/sync-rules", method="POST",
            ),
            timeout=20,
        )
        print(f"cameras={len(cams) if isinstance(cams, list) else cams}", flush=True)
    except Exception as exc:
        print(f"resync_warn={exc}", flush=True)

    verify = psql(
        f"SELECT name, definition->'bindings'->>'speed_kmh' FROM rules "
        f"WHERE id='{rule_id}'::uuid;"
    )
    print(f"verify_rule={verify}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
