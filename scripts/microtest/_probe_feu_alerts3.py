#!/usr/bin/env python3
import subprocess

ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
RULE = "577b664f-d6cf-4431-91b7-97b8470e192b"


def psql(sql: str) -> None:
    r = subprocess.run(
        [
            "docker", "exec", "citevision-v2-postgres",
            "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "|", "-c", sql,
        ],
        capture_output=True, text=True,
    )
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    print(out if out else f"ERR:{err}")


print("=== columns ===")
psql(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_name='alerts' ORDER BY ordinal_position;"
)
print("=== recent alerts any rule ===")
psql(
    f"SELECT a.id::text, a.created_at::text, a.rule_id::text, "
    "a.metadata->>'frigate_event_id', a.metadata->>'capture_source', "
    "a.metadata->>'scene_light_state', a.metadata->>'evidence_status' "
    f"FROM alerts a WHERE a.org_id='{ORG}'::uuid "
    "AND a.created_at >= '2026-08-06 09:00:00+00' "
    "ORDER BY a.created_at DESC LIMIT 30;"
)
print("=== feu rule alerts since HIT1_SINCE ===")
psql(
    f"SELECT a.id::text, a.created_at::text, "
    "a.metadata->>'frigate_event_id', a.metadata->>'capture_source', "
    "a.metadata->>'scene_light_state', a.metadata->>'evidence_status', "
    "coalesce(a.evidence_snapshot->>'status','') "
    f"FROM alerts a WHERE a.org_id='{ORG}'::uuid AND a.rule_id='{RULE}'::uuid "
    "AND a.created_at >= '2026-08-06 10:14:36+00' "
    "ORDER BY a.created_at DESC LIMIT 10;"
)
print("=== feu rule last 5 any time ===")
psql(
    f"SELECT a.id::text, a.created_at::text, "
    "a.metadata->>'frigate_event_id', a.metadata->>'capture_source', "
    "a.metadata->>'scene_light_state' "
    f"FROM alerts a WHERE a.org_id='{ORG}'::uuid AND a.rule_id='{RULE}'::uuid "
    "ORDER BY a.created_at DESC LIMIT 5;"
)
