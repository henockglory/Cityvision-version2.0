#!/usr/bin/env bash
set -uo pipefail
cd ~/citevision-v2
# shellcheck disable=SC1091
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$PWD")"
load_dotenv "$ENV_FILE"

echo "=== red_light last 100 abort / evidence reasons from DB ==="
python3 - <<'PY'
import os, json, collections
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("NO_PSYCOPG2")
    raise SystemExit(0)

user=os.environ.get("POSTGRES_USER","citevision")
pw=os.environ.get("POSTGRES_PASSWORD","changeme_postgres")
db=os.environ.get("POSTGRES_DB","citevision")
host=os.environ.get("POSTGRES_HOST","127.0.0.1")
port=os.environ.get("POSTGRES_PORT","5433")
url=os.environ.get("POSTGRES_URL") or f"postgresql://{user}:{pw}@{host}:{port}/{db}"
conn=psycopg2.connect(url)
cur=conn.cursor(cursor_factory=RealDictCursor)

# events table shape
cur.execute("""
SELECT column_name FROM information_schema.columns
WHERE table_name='events' ORDER BY ordinal_position
""")
print("events_cols", [r["column_name"] for r in cur.fetchall()])

cur.execute("""
SELECT event_type, count(*) FROM events
WHERE event_type ILIKE '%red_light%' OR event_type ILIKE '%traffic%'
GROUP BY 1 ORDER BY 2 DESC LIMIT 20
""")
print("event_types", cur.fetchall())

cur.execute("""
SELECT id::text, event_type, created_at, metadata
FROM events
WHERE event_type = 'red_light_violation'
ORDER BY created_at DESC
LIMIT 100
""")
rows=cur.fetchall()
print("red_light_violation_n", len(rows))
reasons=collections.Counter()
for r in rows:
    meta=r["metadata"] if isinstance(r["metadata"], dict) else {}
    if isinstance(r["metadata"], str):
        try: meta=json.loads(r["metadata"])
        except Exception: meta={}
    # common abort / evidence fields
    reason = (
        meta.get("evidence_abort_reason")
        or meta.get("abort_reason")
        or meta.get("frigate_abort_reason")
        or meta.get("evidence_status")
        or meta.get("compose_abort")
        or meta.get("incomplete_reason")
    )
    if not reason:
        # dig nested
        snap = meta.get("evidence_snapshot") or meta.get("evidence") or {}
        if isinstance(snap, dict):
            reason = snap.get("abort_reason") or snap.get("status") or snap.get("reason")
    if not reason:
        # package completeness
        reason = meta.get("evidence_backend") or "unknown_no_abort_field"
        if meta.get("frigate_event_id"):
            reason = "has_frigate_id:" + str(meta.get("evidence_status") or meta.get("capture_source") or "okish")
        if meta.get("frigate_red_light_soft_iou") is not None:
            reason = "soft_iou_accepted"
    reasons[str(reason)] += 1
print("REASON_DISTRIBUTION")
for k,v in reasons.most_common():
    print(f"  {v:4d} {100*v/max(len(rows),1):5.1f}%  {k}")

# alerts incomplete_evidence
cur.execute("""
SELECT column_name FROM information_schema.columns
WHERE table_name='alerts' ORDER BY ordinal_position
""")
print("alerts_cols", [r["column_name"] for r in cur.fetchall()][:40])

cur.execute("""
SELECT status, count(*) FROM alerts
WHERE created_at > now() - interval '14 days'
GROUP BY 1 ORDER BY 2 DESC
""")
print("alert_status_14d", cur.fetchall())

cur.execute("""
SELECT a.id::text, a.created_at, a.status, a.metadata
FROM alerts a
ORDER BY a.created_at DESC LIMIT 5
""")
print("sample_alerts_meta_keys")
for r in cur.fetchall():
    meta=r["metadata"] if isinstance(r["metadata"], dict) else {}
    if isinstance(r["metadata"], str):
        try: meta=json.loads(r["metadata"])
        except Exception: meta={}
    print(r["created_at"], r["status"], list(meta.keys())[:30] if meta else None)

conn.close()
PY

echo
echo "=== Mailhog messages ==="
curl -sf http://127.0.0.1:8025/api/v2/messages?limit=50 | python3 -c '
import sys,json
try:
 d=json.load(sys.stdin)
except Exception as e:
 print("mailhog fail",e); raise SystemExit(0)
total=d.get("total",0); items=d.get("items") or []
print("mailhog_total", total, "items", len(items))
for m in items[:15]:
  print(m.get("Created"), (m.get("Content") or {}).get("Headers",{}).get("Subject",["?"])[0][:80])
' 2>/dev/null || echo "mailhog unavailable"

echo
echo "=== Frigate recent red_light-ish events ==="
curl -sf "http://127.0.0.1:5000/api/events?limit=30&include_thumbnails=0" | python3 -c '
import sys,json,statistics
d=json.load(sys.stdin)
print("n", len(d))
open_n=0
deltas=[]
for e in d[:30]:
  lab=e.get("label"); st=e.get("start_time"); en=e.get("end_time")
  cam=e.get("camera")
  if en is None:
    open_n+=1
  elif st is not None:
    deltas.append(float(en)-float(st))
  print(f"  cam={str(cam)[:20]} label={lab} start={st} end={en} delta={None if en is None or st is None else round(float(en)-float(st),2)}")
print("open_events", open_n)
if deltas:
  print("delta_mean", round(statistics.mean(deltas),2), "median", round(statistics.median(deltas),2), "min", round(min(deltas),2), "max", round(max(deltas),2))
' 2>/dev/null || echo "frigate events fail"
