#!/usr/bin/env python3
import subprocess

ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
FE = "1786011659.60253-djyxh9"


def psql(sql: str) -> str:
    r = subprocess.run(
        [
            "docker", "exec", "citevision-v2-postgres",
            "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "|", "-c", sql,
        ],
        capture_output=True, text=True,
    )
    return ((r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")).strip()


print("event cols sample:", psql(
    "SELECT column_name FROM information_schema.columns WHERE table_name='events' ORDER BY 1;"
)[:500])
print("---")
print("events by type:", psql(
    f"SELECT event_type, count(*) FROM events WHERE org_id='{ORG}'::uuid GROUP BY 1 ORDER BY 2 DESC LIMIT 20;"
))
print("---")
print("red_light events:", psql(
    f"SELECT id::text, occurred_at::text, event_type, "
    f"metadata->>'frigate_event_id', metadata->>'capture_source', metadata->>'scene_light_state' "
    f"FROM events WHERE org_id='{ORG}'::uuid AND event_type ILIKE '%red%' "
    f"ORDER BY occurred_at DESC LIMIT 10;"
))
print("---")
print("find FE:", psql(
    f"SELECT id::text, occurred_at::text, event_type, metadata->>'capture_source', "
    f"metadata->>'scene_light_state', metadata->>'evidence_status' "
    f"FROM events WHERE org_id='{ORG}'::uuid "
    f"AND metadata->>'frigate_event_id' LIKE '{FE}%' LIMIT 5;"
))
