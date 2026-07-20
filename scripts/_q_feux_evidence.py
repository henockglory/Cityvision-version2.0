#!/usr/bin/env python3
"""Quick post-tour evidence stats."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta

since = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()


def psql(sql: str) -> str:
    return subprocess.check_output(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        text=True,
    ).strip()


ev_status = psql(
    f"SELECT COALESCE(payload->>'evidence_status','(none)'), count(*) "
    f"FROM events WHERE event_type='red_light_violation' AND ingested_at >= '{since}'::timestamptz "
    f"GROUP BY 1 ORDER BY 2 DESC;"
)
caps = psql(
    f"SELECT COALESCE(a.evidence_snapshot->'package'->'metadata'->>'capture_source','(none)'), count(*) "
    f"FROM alerts a JOIN events e ON e.id=a.event_id "
    f"WHERE e.event_type='red_light_violation' AND a.created_at >= '{since}'::timestamptz "
    f"GROUP BY 1 ORDER BY 2 DESC;"
)
alerts = psql(
    f"SELECT count(*) FROM alerts a JOIN events e ON e.id=a.event_id "
    f"WHERE e.event_type='red_light_violation' AND a.created_at >= '{since}'::timestamptz;"
)
events = psql(
    f"SELECT count(*) FROM events WHERE event_type='red_light_violation' "
    f"AND ingested_at >= '{since}'::timestamptz;"
)
print(json.dumps({
    "since": since,
    "events": int(events or 0),
    "alerts": int(alerts or 0),
    "evidence_status": ev_status,
    "alert_capture_source": caps,
}, indent=2))
