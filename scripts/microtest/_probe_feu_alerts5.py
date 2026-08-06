#!/usr/bin/env python3
import subprocess

ORGS = [
    "74d51ead-97a7-4e41-a488-503a9b90c466",
    "99c16650-b07f-4acb-a999-dfc98941406f",
]


def psql(sql: str) -> str:
    r = subprocess.run(
        [
            "docker", "exec", "citevision-v2-postgres",
            "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "|", "-c", sql,
        ],
        capture_output=True, text=True,
    )
    return ((r.stdout or "") + (r.stderr or "")).strip()


print("total alerts", psql("SELECT count(*) FROM alerts;"))
print("total events", psql("SELECT count(*) FROM events;"))
for org in ORGS:
    print(f"org {org[:8]} alerts", psql(f"SELECT count(*) FROM alerts WHERE org_id='{org}'::uuid;"))
    print(f"org {org[:8]} events", psql(f"SELECT count(*) FROM events WHERE org_id='{org}'::uuid;"))
    print(
        "recent events",
        psql(
            f"SELECT id::text, created_at::text, event_type, "
            f"metadata->>'frigate_event_id', metadata->>'capture_source' "
            f"FROM events WHERE org_id='{org}'::uuid "
            f"ORDER BY created_at DESC LIMIT 8;"
        ),
    )
    print(
        "recent alerts",
        psql(
            f"SELECT id::text, created_at::text, title, "
            f"metadata->>'frigate_event_id', metadata->>'capture_source' "
            f"FROM alerts WHERE org_id='{org}'::uuid "
            f"ORDER BY created_at DESC LIMIT 8;"
        ),
    )
