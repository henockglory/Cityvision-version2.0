#!/usr/bin/env bash
set -uo pipefail
cd ~/citevision-v2
python3 - <<'PY'
import json, collections, subprocess

def q(sql):
    return subprocess.check_output([
        "docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-tAc", sql
    ], text=True)

print("event types:")
print(q("SELECT event_type, count(*) FROM events GROUP BY event_type ORDER BY count(*) DESC"))

# inspect evidence_snapshot structure
snap = q("SELECT evidence_snapshot::text FROM events WHERE event_type='red_light_violation' AND evidence_snapshot IS NOT NULL ORDER BY occurred_at DESC LIMIT 3")
for i,line in enumerate(snap.splitlines()):
    if not line.strip(): continue
    d=json.loads(line)
    print(f"\nSNAP{i} type={type(d)} keys={list(d.keys())[:30] if isinstance(d,dict) else d}")
    if isinstance(d, dict):
        print("  abort?", d.get("abort_reason"), d.get("status"), d.get("reason"))
        pkg=d.get("package")
        if isinstance(pkg, dict):
            print("  package keys", list(pkg.keys())[:20])
            print("  package status", pkg.get("status"), pkg.get("abort_reason"), pkg.get("metadata"))

# last 100: classify from evidence_snapshot + payload.metadata
rows = q("""
SELECT payload::text, coalesce(evidence_snapshot::text,'null')
FROM events WHERE event_type='red_light_violation'
ORDER BY occurred_at DESC LIMIT 100
""").splitlines()

# psql -tAc with two cols uses | separator by default? Actually -tAc uses | 
# Wait we used comma? We used SELECT a, b without -F so default | 
ctr=collections.Counter()
parsed=0
for line in rows:
    if not line.strip(): continue
    # default delimiter |
    if '|' in line:
        payload_s, snap_s = line.split('|',1)
    else:
        continue
    parsed += 1
    payload=json.loads(payload_s)
    snap=None if snap_s=='null' else json.loads(snap_s)
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    status = payload.get("evidence_status")
    reason = meta.get("evidence_abort_reason") or meta.get("abort_reason")
    if not reason and isinstance(snap, dict):
        reason = snap.get("abort_reason") or snap.get("status") or snap.get("reason")
        pkg = snap.get("package") if isinstance(snap.get("package"), dict) else None
        if not reason and pkg:
            reason = pkg.get("abort_reason") or pkg.get("status")
            pm = pkg.get("metadata") if isinstance(pkg.get("metadata"), dict) else {}
            if not reason and pm.get("abort_reason"):
                reason = pm["abort_reason"]
    if not reason:
        reason = f"evidence_status={status}" if status else "unknown"
        # refine from meta flags
        if meta.get("frigate_red_light_soft_iou") is not None:
            reason = "soft_iou_in_meta"
        elif meta.get("scene_light"):
            reason = f"scene_light={meta.get('scene_light')}"
        elif isinstance(snap, dict) and snap:
            # summarize snap
            reason = "snap_keys=" + ",".join(list(snap.keys())[:8])
    ctr[str(reason)] += 1

print("\nparsed", parsed)
print("LAST100 classification")
for k,v in ctr.most_common():
    print(f"  {v:3d} {100*v/max(parsed,1):5.1f}%  {k}")

# Also process abort-stats percentages
stats={"align_too_wide":182,"scene_green":107,"clip_not_ready_timeout":8}
tot=sum(stats.values())
print("\nPROCESS abort-stats red_light (current AI process lifetime)")
for k,v in stats.items():
    print(f"  {v:3d} {100*v/tot:5.1f}%  {k}")
print("  NOTE: no_correlation and IoU rejects are NOT in abort_stats counters for this process snapshot;")
print("  IoU reject typically exhausts correlate wait then records no_correlation.")
print("  Log tail (~5MB) relative hits: scene_green=1337 no_correlation=1755 align=1345 IoU=5163 no_clip=1 timeout=8 semaphore=1621")
PY
