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

curl -sf http://127.0.0.1:8081/health >/dev/null
curl -sf http://127.0.0.1:8001/health >/dev/null
curl -sf http://127.0.0.1:8010/health >/dev/null
curl -sf http://127.0.0.1:5000/api/version >/dev/null
curl -sf http://127.0.0.1:5174/ >/dev/null || bash scripts/_sync_frontend_restart_wsl.sh || true
echo "stack healthy"

python3 scripts/_reset_demo_password.py 'Hologram2026!' || true
curl -sf -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true

# Wait until feu cam has a downloadable young clip (tolerate Frigate clip race)
python3 <<'PY'
import json, urllib.request, time, urllib.error
fc = "cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
ok = False
for i in range(30):
    try:
        ev = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=3", timeout=8).read())
    except Exception as e:
        print(f"events_err {e}"); time.sleep(4); continue
    if not ev:
        print("no_events"); time.sleep(4); continue
    # prefer youngest with downloadable clip
    now = time.time()
    best = None
    for e in ev:
        age = now - float(e["start_time"])
        eid = e["id"]
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events/{eid}/clip.mp4", timeout=15) as r:
                n = len(r.read(2048))
            if n > 500:
                best = (age, eid, n)
                if age <= 120:
                    break
        except Exception:
            continue
    if best:
        print(f"precheck {i} young={best[0]:.0f}s clip_ok peek={best[2]} id={best[1][:24]}")
        if best[0] <= 180:
            ok = True
            break
    else:
        print(f"precheck {i} no_downloadable_clip")
    time.sleep(4)
assert ok, "feu frigate clip not ready"
print("media_ready")
open("/tmp/feu_cam_id.txt","w").write("8ed20433-57d5-4999-a6ab-0bea028b23a3")
PY

export ADMIN_PASSWORD='Hologram2026!'
export RULE_NAME='Démo · Feu rouge'
export TARGET_DETECTIONS=1
export RULE_DURATION_SEC=600
export SKIP_FRIGATE_REBUILD=1
export FRIGATE_MAX_ALIGN_MS=20000
export PYTHONUNBUFFERED=1

echo "=== validate feu 1-hit ==="
set +e
python3 scripts/_validate_rule_frigate_1hit.py
VC=$?
set -e
echo "VALIDATE_EXIT=$VC"

python3 <<'PY'
import json, urllib.request
ORG="74d51ead-97a7-4e41-a488-503a9b90c466"
cam=open("/tmp/feu_cam_id.txt").read().strip()
body=json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode()
tok=json.loads(urllib.request.urlopen(urllib.request.Request(
  "http://127.0.0.1:8081/api/v1/auth/login",data=body,
  headers={"Content-Type":"application/json"},method="POST"),timeout=15).read())["access_token"]
h={"Authorization":f"Bearer {tok}"}
raw=json.loads(urllib.request.urlopen(urllib.request.Request(
  f"http://127.0.0.1:8081/api/v1/orgs/{ORG}/alerts?limit=5&camera_id={cam}",headers=h),timeout=20).read())
items=raw if isinstance(raw,list) else raw.get("alerts") or raw.get("items") or []
ft=0
for a in items[:5]:
  snap=a.get("evidence_snapshot") or {}
  pkg=snap.get("package") or {}
  meta=pkg.get("metadata") or {}
  imgs=pkg.get("images") or []
  roles=[i.get("role") for i in imgs if isinstance(i,dict) and (i.get("url") or i.get("asset_id"))]
  clip=pkg.get("clip") or {}
  print(f"alert {str(a.get('id',''))[:8]} src={meta.get('capture_source')} align={meta.get('align_delta_ms')} roles={roles} clip={bool(clip.get('url') or clip.get('asset_id'))} et={meta.get('event_type')}")
  if meta.get("capture_source")=="frigate_track" and (clip.get("url") or clip.get("asset_id")) and "scene" in roles and "subject" in roles:
    ft+=1
print(f"frigate_complete_alerts={ft}")
urllib.request.urlopen("http://127.0.0.1:5174/",timeout=5)
print("frontend_5174=OK")
PY
exit $VC
