#!/usr/bin/env python3
import subprocess

ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"
RULE = "577b664f-d6cf-4431-91b7-97b8470e192b"


def psql(sql: str) -> None:
    r = subprocess.run(
        [
            "docker", "exec", "citevision-v2-postgres",
            "psql", "-U", "citevision", "-d", "citevision", "-c", sql,
        ],
        capture_output=True, text=True,
    )
    print("SQL:", sql[:120])
    print("RC:", r.returncode)
    print("OUT:", r.stdout)
    print("ERR:", r.stderr)
    print("---")


psql(f"SELECT count(*) FROM alerts WHERE org_id='{ORG}'::uuid;")
psql(f"SELECT count(*) FROM alerts WHERE rule_id='{RULE}'::uuid;")
psql(
    "SELECT id::text, created_at::text, rule_id::text "
    f"FROM alerts WHERE org_id='{ORG}'::uuid "
    "ORDER BY created_at DESC LIMIT 5;"
)
psql(
    "SELECT id::text, created_at::text, metadata::text "
    f"FROM alerts WHERE rule_id='{RULE}'::uuid "
    "ORDER BY created_at DESC LIMIT 3;"
)
