#!/usr/bin/env bash
set -uo pipefail
cd ~/citevision-v2
docker exec -i citevision-v2-postgres psql -U citevision -d citevision <<'SQL'
\echo === events columns ===
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='events' ORDER BY ordinal_position;

\echo === alerts columns ===
SELECT column_name FROM information_schema.columns WHERE table_name='alerts' ORDER BY ordinal_position;

\echo === alerts count ===
SELECT count(*) FROM alerts;

\echo === org_demo_videos cols ===
SELECT column_name FROM information_schema.columns WHERE table_name='org_demo_videos' ORDER BY ordinal_position;

\echo === demo videos ===
SELECT * FROM org_demo_videos LIMIT 5;

\echo === demo settings ===
SELECT * FROM org_demo_settings LIMIT 5;
SQL

python3 - <<'PY'
import json, collections, subprocess, os
sql = r"""
SELECT COALESCE(occurred_at, detected_at, ts, created_at)::text AS t,
       metadata::text
FROM events
WHERE event_type = 'red_light_violation'
ORDER BY 1 DESC NULLS LAST
LIMIT 100;
"""
# discover time col
cols = subprocess.check_output([
  "docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-tAc",
  "SELECT string_agg(column_name,',') FROM information_schema.columns WHERE table_name='events'"
], text=True).strip()
print("cols", cols)
# pick order col
order = "id"
for c in ("occurred_at","detected_at","event_ts","ts","created_at","inserted_at"):
  if c in cols.split(","):
    order = c
    break
print("order", order)
q = f"""
COPY (
  SELECT metadata::text FROM events
  WHERE event_type = 'red_light_violation'
  ORDER BY {order} DESC NULLS LAST
  LIMIT 100
) TO STDOUT
"""
raw = subprocess.check_output([
  "docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-c", q
], text=True)
# Actually COPY via -c may not work well; use -tAc
rows = subprocess.check_output([
  "docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-tAc",
  f"SELECT metadata::text FROM events WHERE event_type='red_light_violation' ORDER BY {order} DESC NULLS LAST LIMIT 100"
], text=True).splitlines()
print("n", len(rows))
ctr=collections.Counter()
for line in rows:
  if not line.strip():
    continue
  try:
    meta=json.loads(line)
  except Exception:
    ctr["unparseable"]+=1
    continue
  reason = meta.get("evidence_abort_reason") or meta.get("abort_reason") or meta.get("frigate_abort_reason")
  if not reason:
    es = meta.get("evidence_snapshot") or {}
    if isinstance(es, dict):
      reason = es.get("abort_reason") or es.get("status")
  if not reason:
    # look for known flags
    if meta.get("frigate_red_light_soft_iou") is not None:
      reason = "soft_iou_path"
    elif meta.get("frigate_event_id"):
      reason = "has_frigate_event_id_no_abort"
    elif meta.get("scene_light") == "green" or meta.get("traffic_light_color")=="green":
      reason = "meta_scene_green"
    else:
      # dump keys for unknown
      keys=sorted(meta.keys())
      reason = "no_abort_field keys=" + ",".join(keys[:12])
  ctr[str(reason)] += 1
print("DISTRIBUTION last100")
for k,v in ctr.most_common():
  print(f"  {v:3d} {100*v/max(len(rows),1):5.1f}%  {k}")
PY

echo "=== last go2rtc stream ready ==="
grep -a 'go2rtc stream ready' logs/backend.log | grep -a aaea7c30 | tail -5
grep -a 'stream repair complete\|go2rtc stream ready' logs/backend.log | tail -15

echo "=== AI process start / DEMO_MODE log ==="
grep -a 'DEMO_MODE=\|Uvicorn running\|Application startup' logs/ai-engine.log | tail -20
