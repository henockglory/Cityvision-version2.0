#!/usr/bin/env python3
"""Recent events/alerts/evidence stats for Frigate validation."""
import json
import subprocess

SQL_EVENTS = """
SELECT event_type, count(*)::text
FROM events
WHERE ingested_at > now() - interval '25 minutes'
GROUP BY event_type ORDER BY count(*) DESC;
"""

SQL_EVIDENCE = """
SELECT
  COALESCE(metadata->>'evidence_status', 'none') AS evidence_status,
  COALESCE(metadata->>'capture_source', 'none') AS capture_source,
  count(*)::text
FROM events
WHERE ingested_at > now() - interval '25 minutes'
GROUP BY 1, 2 ORDER BY count(*) DESC;
"""

SQL_ALERTS = """
SELECT count(*)::text FROM alerts WHERE created_at > now() - interval '25 minutes';
"""

SQL_PACKAGES = """
SELECT
  COALESCE(a.evidence_snapshot->'package'->'metadata'->>'capture_source', 'none'),
  COALESCE(a.evidence_snapshot->'package'->'metadata'->>'evidence_status', 'none'),
  count(*)::text
FROM alerts a
WHERE a.created_at > now() - interval '25 minutes'
GROUP BY 1, 2;
"""


def psql(sql: str) -> list[tuple[str, ...]]:
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F|", "-c", sql],
        capture_output=True,
        text=True,
        check=False,
    )
    rows = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line and "|" in line:
            rows.append(tuple(line.split("|")))
    return rows


def main() -> None:
    print("=== Events (25 min) ===")
    for row in psql(SQL_EVENTS):
        print(f"  {row[0]}: {row[1]}")

    print("\n=== Evidence metadata on events ===")
    for row in psql(SQL_EVIDENCE):
        print(f"  status={row[0]} capture={row[1]} n={row[2]}")

    alerts = psql(SQL_ALERTS)
    print(f"\n=== Alerts (25 min): {alerts[0][0] if alerts else 0} ===")

    pkgs = psql(SQL_PACKAGES)
    if pkgs:
        print("\n=== Alert evidence packages ===")
        for row in pkgs:
            print(f"  capture={row[0]} status={row[1]} n={row[2]}")
    else:
        print("\n=== No alert evidence packages ===")


if __name__ == "__main__":
    main()
