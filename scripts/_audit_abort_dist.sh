#!/usr/bin/env bash
set -uo pipefail
cd ~/citevision-v2
python3 - <<'PY'
import json, collections, subprocess

def q(sql):
    return subprocess.check_output([
        "docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-tAc", sql
    ], text=True)

# sample one payload
sample = q("SELECT payload::text FROM events WHERE event_type='red_light_violation' ORDER BY occurred_at DESC LIMIT 1")
print("SAMPLE_PAYLOAD_KEYS")
try:
    p=json.loads(sample.strip().split("\n")[0] if sample.strip() else "{}")
    print(sorted(p.keys())[:40])
    print("evidence keys", list((p.get("evidence") or p.get("evidence_snapshot") or {}).keys())[:20] if isinstance(p.get("evidence") or p.get("evidence_snapshot"), dict) else None)
except Exception as e:
    print("err", e, sample[:300])

rows = q("SELECT coalesce(payload::text,'{}') || E'\\t' || coalesce(evidence_snapshot::text,'null') FROM events WHERE event_type='red_light_violation' ORDER BY occurred_at DESC LIMIT 100").splitlines()
print("n", len(rows))
ctr=collections.Counter()
for line in rows:
    if not line.strip():
        continue
    if "\t" in line:
        payload_s, snap_s = line.split("\t",1)
    else:
        payload_s, snap_s = line, "null"
    try:
        payload=json.loads(payload_s)
    except Exception:
        ctr["bad_payload"]+=1
        continue
    try:
        snap=None if snap_s in ("null","") else json.loads(snap_s)
    except Exception:
        snap=None
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    reason = None
    for src in (meta, payload, snap if isinstance(snap, dict) else {}):
        if not isinstance(src, dict):
            continue
        reason = src.get("evidence_abort_reason") or src.get("abort_reason") or src.get("frigate_abort_reason") or src.get("compose_abort")
        if reason:
            break
        es = src.get("evidence_snapshot") if isinstance(src.get("evidence_snapshot"), dict) else None
        if es:
            reason = es.get("abort_reason") or es.get("status")
            if reason: break
    if not reason:
        # derive
        if meta.get("frigate_red_light_soft_iou") is not None or payload.get("frigate_red_light_soft_iou") is not None:
            reason = "soft_iou_marked"
        elif payload.get("frigate_event_id") or meta.get("frigate_event_id"):
            reason = "correlated_no_abort_field"
        elif snap:
            reason = "has_db_evidence_snapshot"
        else:
            # look abort in nested package
            pkg = None
            for src in (payload, meta):
                if isinstance(src, dict) and isinstance(src.get("package"), dict):
                    pkg = src["package"]; break
            if pkg and pkg.get("abort_reason"):
                reason = pkg["abort_reason"]
            else:
                reason = "no_abort_persisted keys=" + ",".join(sorted(payload.keys())[:10])
    ctr[str(reason)] += 1
print("LAST100_FROM_DB")
for k,v in ctr.most_common():
    print(f"  {v:3d} {100*v/max(len([r for r in rows if r.strip()]),1):5.1f}%  {k}")

print("\nALERTS", q("SELECT count(*) FROM alerts"))
print("EVENTS by type top")
print(q("SELECT event_type||' '||count(*) FROM events GROUP BY 1 ORDER BY count(*) DESC LIMIT 15"))
PY

# Process-lifetime abort stats already known; also count no_correlation from AI logs recent
echo "=== AI log abort reasons last mentions ==="
python3 - <<'PY'
from pathlib import Path
import collections, re
log=Path("logs/ai-engine.log")
text=log.read_bytes().decode("utf-8","replace")[-5_000_000:]  # last ~5MB
# count abort_stats record patterns in logs
patterns={
 "scene_green": r"scene_green|ABORT_SCENE_GREEN|abort.*scene_green",
 "no_correlation": r"no_correlation|no Frigate match|reject.*correlation",
 "align_too_wide": r"align_too_wide|reject align",
 "IoU": r"reject IoU|soft-accept iou",
 "no_clip": r"no_clip|clip download empty",
 "clip_not_ready_timeout": r"clip_not_ready_timeout|end_time wait",
 "semaphore_timeout": r"evidence semaphore timeout|retroactive semaphore busy",
}
for name,pat in patterns.items():
  print(name, len(re.findall(pat, text, re.I)))
PY
