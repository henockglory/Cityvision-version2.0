#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
GO_BIN=/usr/local/go/bin/go
LOGDIR=$ROOT/logs

# Ensure backend
if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
  free_port 8081
  [[ -x backend/bin/citevision-api ]] || (cd backend && $GO_BIN build -o bin/citevision-api ./cmd/api)
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90
fi

python3 scripts/_reset_demo_password.py 'Hologram2026!'

# Enable ONLY speed rule, rebuild frigate WITH record, restart frigate, repair streams
python3 - <<'PY'
import json,urllib.request
API="http://127.0.0.1:8081"; ORG="74d51ead-97a7-4e41-a488-503a9b90c466"; RULE="Démo · Excès de vitesse"
login=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/auth/login",
  data=json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode(),
  headers={"Content-Type":"application/json"}, method="POST")).read())
tok=login["access_token"]
rules=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules", headers={"Authorization":f"Bearer {tok}"})).read())
for r in rules:
  name=str(r.get("name",""))
  if name.startswith("Démo"):
    urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}",
      data=json.dumps({"is_enabled": name==RULE}).encode(),
      headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, method="PATCH"))
urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/demo/settings",
  data=json.dumps({"source_mode":"video","active_video_id":"e774ae7a-137c-4c2f-901a-7324bb64c8b2","active_camera_id":None}).encode(),
  headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, method="PATCH"))
print("speed rule ON")
PY

echo "=== rebuild frigate ==="
curl -sS -w "\nHTTP=%{http_code}\n" --max-time 180 -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild || true

python3 - <<'PY'
from pathlib import Path
import re
text=Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml").read_text()
cam="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
m=re.search(rf"{re.escape(cam)}:.*?record:\s*\n\s*enabled:\s*(true|false)", text, re.S)
print("record", m.group(1) if m else "?")
assert m and m.group(1)=="true", "record must be on"
PY

docker restart citevision-v2-go2rtc citevision-v2-frigate
sleep 40
curl -sS -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams
sleep 15

echo "=== wait NEW events ==="
python3 - <<'PY'
import json,time,urllib.request
fc="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
ok=False
for i in range(48):
  try:
    st=json.loads(urllib.request.urlopen("http://127.0.0.1:5000/api/stats", timeout=8).read())
    cam=(st.get("cameras") or {}).get(fc) or {}
    fps=float(cam.get("camera_fps") or 0); det=float(cam.get("detection_fps") or 0)
  except Exception as e:
    print("stats", e); time.sleep(5); continue
  try:
    ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5", timeout=8).read())
  except Exception as e:
    print("ev", e); time.sleep(5); continue
  now=time.time()
  young=9999
  if isinstance(ev,list) and ev:
    young=min(now-float(e["start_time"]) for e in ev if isinstance(e.get("start_time"),(int,float)))
  print(f"try {i} fps={fps:.1f} det={det:.1f} young={young:.0f}s n={len(ev) if isinstance(ev,list) else 0}")
  if fps>0 and young<=30:
    ok=True; break
  time.sleep(5)
print("EVENTS", "OK" if ok else "FAIL")
raise SystemExit(0 if ok else 2)
PY

# AI up
if ! curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
  bash scripts/restart-ai-engine.sh
fi
if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh
fi

# Capture once while rule is ON (record stays on)
python3 - <<'PY'
import json,urllib.request,time,subprocess
ORG="74d51ead-97a7-4e41-a488-503a9b90c466"; CAM="55694d53-8f58-4981-91b2-7c6cd528a25d"
r=subprocess.run(["docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-t","-A","-c",
  f"SELECT payload FROM events e WHERE e.camera_id='{CAM}'::uuid AND e.event_type='speeding' ORDER BY e.ingested_at DESC LIMIT 1;"],
  capture_output=True,text=True)
raw=(r.stdout or "").strip()
evt=json.loads(raw) if raw else {"event_type":"speeding","event_id":"m","track_id":1,"camera_id":CAM,"org_id":ORG,"bbox":{"x":0.3,"y":0.3,"width":0.25,"height":0.25},"class_name":"car"}
evt["bbox_ts"]=time.time(); evt["event_type"]="speeding"; evt["evidence_status"]="pending"
body={"org_id":ORG,"event":evt,"evidence":{"enabled":True,"clip_seconds":6,"images":[{"role":"scene"},{"role":"subject"},{"role":"plate"}]}}
print("capturing…")
req=urllib.request.Request(f"http://127.0.0.1:8001/cameras/{CAM}/evidence/capture",
  data=json.dumps(body).encode(), headers={"Content-Type":"application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=240) as resp:
  data=json.loads(resp.read())
pkg=data.get("package") or (data.get("evidence") or {}).get("package") or data
meta=(pkg.get("metadata") or {}) if isinstance(pkg, dict) else {}
print("status", data.get("evidence_status") or meta.get("evidence_status"))
print("src", meta.get("capture_source"), "fev", meta.get("frigate_event_id"))
print("clip", bool(isinstance(pkg,dict) and pkg.get("clip")), "images", len((pkg or {}).get("images") or []) if isinstance(pkg,dict) else 0)
open("/tmp/last_capture.json","w").write(json.dumps(data)[:4000])
assert meta.get("capture_source")=="frigate_track" and isinstance(pkg,dict) and pkg.get("clip"), data
print("CAPTURE_OK")
PY
