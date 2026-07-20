#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
# Do NOT restart anything — Frigate is healthy now.
python3 - <<'PY'
import json,urllib.request,time,subprocess
ORG="74d51ead-97a7-4e41-a488-503a9b90c466"; CAM="55694d53-8f58-4981-91b2-7c6cd528a25d"
# health
for url in ["http://127.0.0.1:8081/health","http://127.0.0.1:8001/health","http://127.0.0.1:5000/api/version"]:
  urllib.request.urlopen(url, timeout=5).read(); print("ok", url)
fc="cv_"+CAM
ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=3", timeout=8).read())
now=time.time()
print("frigate", [(e.get("label"), round(now-float(e["start_time"]),1), e.get("has_clip")) for e in ev])
r=subprocess.run(["docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-t","-A","-c",
  f"SELECT payload FROM events e WHERE e.camera_id='{CAM}'::uuid AND e.event_type='speeding' ORDER BY e.ingested_at DESC LIMIT 1;"],
  capture_output=True,text=True)
raw=(r.stdout or "").strip()
evt=json.loads(raw) if raw else {"event_type":"speeding","event_id":"m","track_id":1,"camera_id":CAM,"org_id":ORG,"bbox":{"x":0.3,"y":0.3,"width":0.2,"height":0.2},"class_name":"car"}
evt["bbox_ts"]=time.time(); evt["evidence_status"]="pending"; evt["event_type"]="speeding"
body={"org_id":ORG,"event":evt,"evidence":{"enabled":True,"clip_seconds":6,"images":[{"role":"scene"},{"role":"subject"},{"role":"plate"}]}}
print("capture…")
req=urllib.request.Request(f"http://127.0.0.1:8001/cameras/{CAM}/evidence/capture",
  data=json.dumps(body).encode(), headers={"Content-Type":"application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=240) as resp:
  data=json.loads(resp.read())
pkg=data.get("package") or (data.get("evidence") or {}).get("package") or data
meta=(pkg.get("metadata") or {}) if isinstance(pkg, dict) else {}
print("status", data.get("evidence_status") or meta.get("evidence_status"))
print("src", meta.get("capture_source"), "fev", meta.get("frigate_event_id"))
print("clip", bool(isinstance(pkg,dict) and pkg.get("clip")), "images", len((pkg or {}).get("images") or []) if isinstance(pkg,dict) else 0)
print("align_ms", meta.get("align_delta_ms"), "bbox_src", meta.get("bbox_source"))
if meta.get("capture_source")!="frigate_track" or not (isinstance(pkg,dict) and pkg.get("clip")):
  raise SystemExit(3)
print("CAPTURE_OK")
PY
grep -E 'frigate_track|dedupe' "$ROOT/logs/ai-engine.log" | tail -20
