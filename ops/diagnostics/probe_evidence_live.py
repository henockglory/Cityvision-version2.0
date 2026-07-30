#!/usr/bin/env python3
"""Live probe after road evidence fixes."""
from __future__ import annotations

import json
import subprocess
import urllib.request


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        return e.output or str(e)


def main() -> None:
    print("=== HEALTH ===")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=5) as r:
            print(r.read().decode()[:300])
    except Exception as e:
        print("health fail:", e)

    print("\n=== LOG ===")
    out = sh(
        [
            "grep",
            "-a",
            "-E",
            "accept active|bound capture|frigate capture missing|skip demo vehicle|no correlated|stale anchor",
            "/home/gheno/citevision-v2/logs/ai-engine.log",
        ]
    )
    lines = [ln for ln in out.splitlines() if ln.strip()][-40:]
    print("\n".join(lines) if lines else "(no matches)")

    print("\n=== DB ===")
    sql = """
SELECT event_type,
  COALESCE(payload->>'evidence_status', 'null') AS st,
  COALESCE(payload->>'abort_reason', payload->'evidence_meta'->>'abort_reason', '?') AS reason,
  count(*)
FROM citevision.events
WHERE created_at > now() - interval '15 minutes'
  AND event_type IN ('red_light_violation','speeding')
GROUP BY 1,2,3 ORDER BY 4 DESC;
"""
    print(sh(["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql]))

    print("=== ALERTS ===")
    print(
        sh(
            [
                "docker",
                "exec",
                "citevision-v2-postgres",
                "psql",
                "-U",
                "citevision",
                "-d",
                "citevision",
                "-c",
                "SELECT count(*) AS alerts_15m FROM citevision.alerts WHERE created_at > now() - interval '15 minutes';",
            ]
        )
    )

    print("=== SAMPLE ===")
    sql2 = """
SELECT created_at, event_type,
  payload->>'evidence_status' AS st,
  payload->>'abort_reason' AS abort,
  payload->'metadata'->'subject_binding_zone' IS NOT NULL AS has_zone
FROM citevision.events
WHERE event_type IN ('red_light_violation','speeding')
ORDER BY created_at DESC LIMIT 8;
"""
    print(sh(["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql2]))


if __name__ == "__main__":
    main()
