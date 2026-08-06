#!/usr/bin/env python3
import json
import subprocess

ORG = "74d51ead-97a7-4e41-a488-503a9b90c466"


def psql(sql: str) -> str:
    r = subprocess.run(
        [
            "docker", "exec", "citevision-v2-postgres",
            "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-F", "|", "-c", sql,
        ],
        capture_output=True, text=True,
    )
    return ((r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")).strip()


rows = psql(
    f"SELECT id::text, occurred_at::text, severity, "
    f"coalesce(evidence_snapshot::text,'null'), coalesce(payload::text,'null') "
    f"FROM events WHERE org_id='{ORG}'::uuid AND event_type='red_light_violation' "
    f"ORDER BY occurred_at DESC LIMIT 6;"
)
print("raw rows count", len([x for x in rows.splitlines() if x.strip()]))
for i, line in enumerate(rows.splitlines(), 1):
    parts = line.split("|", 4)
    if len(parts) < 5:
        print("bad line", line[:120])
        continue
    eid, ots, sev, snap_raw, payload_raw = parts
    try:
        snap = json.loads(snap_raw) if snap_raw != "null" else {}
    except Exception:
        snap = {}
    try:
        payload = json.loads(payload_raw) if payload_raw != "null" else {}
    except Exception:
        payload = {}
    meta = {}
    if isinstance(snap, dict):
        pkg = snap.get("package") or snap
        if isinstance(pkg, dict):
            meta = pkg.get("metadata") or {}
    if not meta and isinstance(payload, dict):
        meta = payload.get("metadata") or payload
    print(
        f"#{i} event={eid[:12]} occurred={ots} sev={sev} "
        f"fe={str(meta.get('frigate_event_id') or '')[:28]} "
        f"cap={meta.get('capture_source')} scene={meta.get('scene_light_state')} "
        f"bbox_src={meta.get('bbox_source')} evidence={meta.get('evidence_status')} "
        f"texture={meta.get('subject_texture')} "
        f"images={len((snap.get('package') or snap).get('images') or []) if isinstance(snap, dict) else 0}"
    )
