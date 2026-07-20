#!/usr/bin/env python3
import subprocess
import sys
import time

CAM108 = "37c7d7fa-12dc-450c-8c4b-ab63ed43a819"


def db_now() -> str:
    proc = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", "SELECT now()::text;"],
        capture_output=True,
        text=True,
    )
    return (proc.stdout or "").strip()


def count(sql: str) -> int:
    proc = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True,
        text=True,
    )
    for line in (proc.stdout or "").splitlines():
        if line.strip().isdigit():
            return int(line.strip())
    return 0


def main() -> int:
    marker = db_now()
    print(f"marker={marker}", flush=True)
    baseline_events = count(
        f"SELECT count(*) FROM events WHERE camera_id='{CAM108}' AND event_type='speeding' "
        f"AND occurred_at > '{marker}';"
    )
    baseline_alerts = count(
        f"SELECT count(*) FROM alerts a JOIN events e ON e.id=a.event_id "
        f"WHERE e.camera_id='{CAM108}' AND e.event_type='speeding' AND a.created_at > '{marker}';"
    )
    print(f"baseline events={baseline_events} alerts={baseline_alerts}", flush=True)
    deadline = time.time() + 600
    while time.time() < deadline:
        ev = count(
            f"SELECT count(*) FROM events WHERE camera_id='{CAM108}' AND event_type='speeding' "
            f"AND occurred_at > '{marker}';"
        )
        al = count(
            f"SELECT count(*) FROM alerts a JOIN events e ON e.id=a.event_id "
            f"WHERE e.camera_id='{CAM108}' AND e.event_type='speeding' AND a.created_at > '{marker}';"
        )
        new_ev = ev - baseline_events
        new_al = al - baseline_alerts
        print(f"new_speeding={new_ev} new_alerts={new_al}", flush=True)
        if new_ev >= 3:
            print("DONE", flush=True)
            return 0
        time.sleep(20)
    print("TIMEOUT", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
