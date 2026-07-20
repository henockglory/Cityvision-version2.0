#!/usr/bin/env python3
import json
import subprocess
import urllib.request

CAM108 = "37c7d7fa-12dc-450c-8c4b-ab63ed43a819"
ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"


def psql(sql: str) -> str:
    proc = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True,
        text=True,
    )
    return (proc.stdout or proc.stderr).strip()


def main():
    print("=== DB rules ===")
    print(psql(
        "SELECT name, is_enabled, definition->'evidence'->'images'->1->>'crop', "
        "definition->'bindings'->>'live_traffic', definition->'bindings'->>'speed_limit_kmh' "
        f"FROM rules WHERE org_id='{ORG}' "
        "AND (definition->'condition'->>'value'='speeding' OR name ILIKE '%vitesse%' OR name ILIKE '%speed%') "
        "ORDER BY updated_at DESC LIMIT 5;"
    ))
    print("\n=== DB events 1h cam108 ===")
    print(psql(
        f"SELECT count(*) FROM events WHERE camera_id='{CAM108}' "
        "AND event_type='speeding' AND occurred_at > now() - interval '1 hour';"
    ))
    print("\n=== DB events 30min cam108 ===")
    print(psql(
        f"SELECT count(*) FROM events WHERE camera_id='{CAM108}' "
        "AND event_type='speeding' AND occurred_at > now() - interval '30 minutes';"
    ))
    print("\n=== DB alerts 1h (via events cam108) ===")
    print(psql(
        f"SELECT count(*) FROM alerts a JOIN events e ON e.id=a.event_id "
        f"WHERE e.camera_id='{CAM108}' AND a.created_at > now() - interval '1 hour';"
    ))
    print("\n=== Latest 5 alerts cam108 (title, created) ===")
    print(psql(
        f"SELECT a.title, a.created_at::text FROM alerts a JOIN events e ON e.id=a.event_id "
        f"WHERE e.camera_id='{CAM108}' ORDER BY a.created_at DESC LIMIT 5;"
    ))
    print("\n=== spatial-config ===")
    req = urllib.request.Request(
        f"http://127.0.0.1:8081/api/v1/internal/ingest/orgs/{ORG}/cameras/{CAM108}/spatial-config",
        headers={"X-Internal-Key": "changeme_internal_service_key"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode())
    for z in data.get("zones", []):
        if z.get("behavior") == "speed_measurement":
            cfg = (z.get("behavior_config") or {}).get("config") or z.get("behavior_config") or {}
            print(json.dumps({"zone": z.get("zone_id"), "limit": cfg.get("speed_limit_kmh"), "live_traffic": cfg.get("live_traffic"), "cooldown": cfg.get("cooldown_sec")}, indent=2))


if __name__ == "__main__":
    main()
