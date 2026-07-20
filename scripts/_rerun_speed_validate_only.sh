#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

cp -f "$WIN/scripts/_validate_rule_frigate_1hit.py" "$ROOT/scripts/_validate_rule_frigate_1hit.py"
sed -i 's/\r$//' "$ROOT/scripts/_validate_rule_frigate_1hit.py"

# Health gates
curl -sf http://127.0.0.1:8081/health >/dev/null
curl -sf http://127.0.0.1:8001/health >/dev/null
curl -sf http://127.0.0.1:8010/health >/dev/null
curl -sf http://127.0.0.1:5000/api/version >/dev/null
curl -sf http://127.0.0.1:5174/ >/dev/null
curl -sf http://127.0.0.1:5174/health >/dev/null
echo "stack+frontend healthy"

curl -sf -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true

python3 scripts/_reset_demo_password.py 'Hologram2026!' || true

# Media precheck
python3 <<'PY'
import json, urllib.request, time, urllib.error
fc="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
ok=False
for i in range(12):
  ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=2",timeout=8).read())
  if not ev: time.sleep(3); continue
  eid=ev[0]["id"]; young=time.time()-float(ev[0]["start_time"])
  try:
    with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events/{eid}/clip.mp4",timeout=15) as r:
      n=len(r.read(2048)); code=200
  except urllib.error.HTTPError as e:
    code,n=e.code,0
  print(f"precheck {i} young={young:.0f}s http={code} peek={n}")
  if young<=90 and code==200 and n>500:
    ok=True; break
  time.sleep(3)
assert ok
print("media_ready")
PY

export ADMIN_PASSWORD='Hologram2026!'
export RULE_NAME='Démo · Excès de vitesse'
export TARGET_DETECTIONS=1
export RULE_DURATION_SEC=360
export SKIP_FRIGATE_REBUILD=1
export FRIGATE_MAX_ALIGN_MS=20000
export PYTHONUNBUFFERED=1
python3 scripts/_validate_rule_frigate_1hit.py
echo "VALIDATE_EXIT=$?"

# Confirm UI from WSL + print alert
python3 <<'PY'
import json, urllib.request
ORG="74d51ead-97a7-4e41-a488-503a9b90c466"
CAM="55694d53-8f58-4981-91b2-7c6cd528a25d"
body=json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode()
tok=json.loads(urllib.request.urlopen(urllib.request.Request(
  "http://127.0.0.1:8081/api/v1/auth/login",data=body,
  headers={"Content-Type":"application/json"},method="POST"),timeout=15).read())["access_token"]
h={"Authorization":f"Bearer {tok}"}
raw=json.loads(urllib.request.urlopen(urllib.request.Request(
  f"http://127.0.0.1:8081/api/v1/orgs/{ORG}/alerts?limit=3&camera_id={CAM}",headers=h),timeout=20).read())
items=raw if isinstance(raw,list) else raw.get("alerts") or raw.get("items") or []
for a in items[:3]:
  snap=a.get("evidence_snapshot") or {}
  pkg=snap.get("package") or {}
  meta=pkg.get("metadata") or {}
  imgs=pkg.get("images") or []
  roles=[i.get("role") for i in imgs if isinstance(i,dict) and (i.get("url") or i.get("asset_id"))]
  clip=pkg.get("clip") or {}
  print(f"alert {str(a.get('id',''))[:8]} src={meta.get('capture_source')} align_ms={meta.get('align_delta_ms')} roles={roles} clip={bool(clip.get('url') or clip.get('asset_id'))}")
urllib.request.urlopen("http://127.0.0.1:5174/",timeout=5)
urllib.request.urlopen("http://127.0.0.1:5174/health",timeout=5)
print("UI http://127.0.0.1:5174/ OK (page + proxy backend)")
PY
