#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

# Sync validator + evidence
cp -f /mnt/c/Users/gheno/citevision/scripts/_validate_rule_frigate_1hit.py "$ROOT/scripts/_validate_rule_frigate_1hit.py"
sed -i 's/\r$//' "$ROOT/scripts/_validate_rule_frigate_1hit.py"
python3 /mnt/c/Users/gheno/citevision/scripts/_tmp_sync_evidence_only.py

# Re-register demo streams (critical after go2rtc restart)
bash scripts/ensure-demo-streams.sh || true

# Health
curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null || bash scripts/restart-ai-engine.sh
for i in $(seq 1 40); do curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null && break; sleep 2; done
curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null || {
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 60
}
curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null || bash scripts/_sync_frontend_restart_wsl.sh || true

# Confirm young frigate event exists (age only — same as validator)
python3 - <<'PY'
import json,time,urllib.request
fc="cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
ok=False
for i in range(40):
  try:
    ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5",timeout=10).read())
  except Exception as e:
    print("err",e); time.sleep(3); continue
  now=time.time()
  for e in (ev or []):
    age=now-float(e.get("start_time") or 0)
    if age<=90:
      print(f"FRESH age={age:.0f}s id={str(e.get('id',''))[:16]}")
      ok=True
      break
  if ok: break
  ages=[round(now-float(e.get('start_time') or 0)) for e in (ev or [])[:3]]
  print(f"wait {i} ages={ages}")
  time.sleep(3)
raise SystemExit(0 if ok else 1)
PY

export ADMIN_PASSWORD='Hologram2026!'
export RULE_NAME='Démo · Feu rouge'
export RULE_DURATION_SEC=600
export SKIP_FRIGATE_REBUILD=1
export FRIGATE_MAX_ALIGN_MS=30000
export FRIGATE_FRESH_MAX_AGE_SEC=90
export PYTHONUNBUFFERED=1
python3 scripts/_reset_demo_password.py 'Hologram2026!' || true

echo "UI http://127.0.0.1:5174/ — lancement validation"
set +e
python3 scripts/_validate_rule_frigate_1hit.py
VC=$?
set -e
echo "VALIDATE_EXIT=$VC"

python3 - <<'PY'
import json, urllib.request
ORG="74d51ead-97a7-4e41-a488-503a9b90c466"
CAM="8ed20433-57d5-4999-a6ab-0bea028b23a3"
body=json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode()
tok=json.loads(urllib.request.urlopen(urllib.request.Request(
  "http://127.0.0.1:8081/api/v1/auth/login",data=body,
  headers={"Content-Type":"application/json"},method="POST"),timeout=15).read())["access_token"]
h={"Authorization":f"Bearer {tok}"}
raw=json.loads(urllib.request.urlopen(urllib.request.Request(
  f"http://127.0.0.1:8081/api/v1/orgs/{ORG}/alerts?limit=5&camera_id={CAM}",headers=h),timeout=20).read())
items=raw if isinstance(raw,list) else raw.get("alerts") or raw.get("items") or []
print(f"alerts_n={len(items)}")
for a in items[:5]:
  snap=a.get("evidence_snapshot") or {}
  pkg=snap.get("package") or {}
  meta=pkg.get("metadata") or {}
  print(f"  id={str(a.get('id',''))[:8]} src={meta.get('capture_source')} bbox_src={meta.get('bbox_source')} "
        f"bbox_ok={meta.get('bbox_quality_ok')} subject_ok={meta.get('subject_quality_ok')} "
        f"align={meta.get('align_delta_ms')} status={pkg.get('status')}")
print("Review: http://127.0.0.1:5174/ → Alertes")
PY
curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null && echo UI_OK || echo UI_DOWN
exit $VC
