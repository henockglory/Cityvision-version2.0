#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

python3 - <<'PY'
from pathlib import Path
win = Path("/mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai")
dst = Path("/home/gheno/citevision-v2/ai-engine/src/citevision_ai")
for rel in [
    "road_enforcement/traffic_light.py",
    "evidence/frigate_track_evidence.py",
]:
    t = (win / rel).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    (dst / rel).write_text(t, encoding="utf-8", newline="\n")
    print("synced", rel)
tl = (dst / "road_enforcement/traffic_light.py").read_text()
fe = (dst / "evidence/frigate_track_evidence.py").read_text()
assert "Prefer red" not in tl
assert 'raw_state == "red"' in tl
assert "RED_LIGHT_MAX_ALIGN_SEC" in fe
assert "_scene_light_state" in fe
assert "abort red_light — scene lamp" in fe
assert "import urllib.error" in fe
print("markers_ok")
PY

cp -f "$WIN/ai-engine/tests/test_traffic_light_hsv.py" "$ROOT/ai-engine/tests/test_traffic_light_hsv.py"
cp -f "$WIN/scripts/_validate_rule_frigate_1hit.py" "$ROOT/scripts/_validate_rule_frigate_1hit.py"
sed -i 's/\r$//' "$ROOT/ai-engine/tests/test_traffic_light_hsv.py" "$ROOT/scripts/_validate_rule_frigate_1hit.py"

cd "$ROOT/ai-engine"
./.venv/bin/python -m pytest tests/test_traffic_light_hsv.py -q || exit 1
cd "$ROOT"

bash scripts/restart-ai-engine.sh
for i in $(seq 1 60); do curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null && break; sleep 2; done
curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null || { echo AI_FAIL; tail -30 logs/ai-engine.log; exit 1; }

if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90 || exit 1
fi
if ! curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null; then
  bash scripts/_sync_frontend_restart_wsl.sh || true
fi
if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh || true
fi

bash scripts/ensure-demo-streams.sh || true

# Wait Frigate young event
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
      print(f"FRESH age={age:.0f}s"); ok=True; break
  if ok: break
  print(f"wait {i}"); time.sleep(3)
raise SystemExit(0 if ok else 1)
PY

python3 scripts/_reset_demo_password.py 'Hologram2026!' || true
export ADMIN_PASSWORD='Hologram2026!'
export RULE_NAME='Démo · Feu rouge'
export RULE_DURATION_SEC=600
export SKIP_FRIGATE_REBUILD=1
export FRIGATE_MAX_ALIGN_MS=30000
export FRIGATE_FRESH_MAX_AGE_SEC=90
export PYTHONUNBUFFERED=1

echo "UI http://127.0.0.1:5174/"
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
        f"scene_light={meta.get('scene_light_state')} align={meta.get('align_delta_ms')}")
print("Review: http://127.0.0.1:5174/ → Alertes")
PY
# Log gates
grep -E 'abort red_light|scene lamp|reject align|Prefer' logs/ai-engine.log | tail -20 || true
curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null && echo UI_OK || echo UI_DOWN
exit $VC
