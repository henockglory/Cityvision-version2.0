#!/usr/bin/env python3
"""Query feu alerts for gallery export debugging."""
import json
import subprocess
import urllib.request

ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
API = "http://127.0.0.1:8081"
EMAIL = "glory.henock@hologram.cd"
PASS = "Hologram2026!"


def psql(sql: str) -> str:
    r = subprocess.run(
        [
            "docker", "exec", "citevision-v2-postgres",
            "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "|", "-c", sql,
        ],
        capture_output=True, text=True, check=False,
    )
    return (r.stdout or "").strip() + (("\nERR:" + r.stderr) if r.returncode else "")


print("=== rules ===")
print(psql(
    f"SELECT id::text, name FROM rules WHERE org_id='{ORG}'::uuid "
    "AND (name ILIKE '%feu%' OR name ILIKE '%red%') ORDER BY name;"
))

print("=== alerts since 10:00 ===")
print(psql(
    f"SELECT a.id::text, a.created_at::text, a.rule_name, "
    "a.metadata->>'frigate_event_id', a.metadata->>'capture_source', "
    "a.metadata->>'scene_light_state', a.metadata->>'evidence_status', "
    "a.rule_id::text "
    f"FROM alerts a WHERE a.org_id='{ORG}'::uuid "
    "AND a.created_at >= '2026-08-06 10:00:00+00' "
    "ORDER BY a.created_at DESC LIMIT 20;"
))

print("=== alerts evidence_snapshot present ===")
print(psql(
    f"SELECT a.id::text, a.created_at::text, "
    "coalesce(a.evidence_snapshot->>'status', a.metadata->>'evidence_status') "
    f"FROM alerts a WHERE a.org_id='{ORG}'::uuid "
    "AND a.created_at >= '2026-08-06 10:00:00+00' "
    "ORDER BY a.created_at DESC LIMIT 10;"
))

# login check
try:
    req = urllib.request.Request(
        f"{API}/api/v1/auth/login",
        data=json.dumps({"email": EMAIL, "password": PASS}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        tok = json.loads(resp.read().decode())["access_token"]
    print("login OK token_len=", len(tok))
except Exception as exc:
    print("login FAIL", exc)
