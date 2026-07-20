#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

python3 - <<'PY'
from pathlib import Path
win = Path("/mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai")
dst = Path("/home/gheno/citevision-v2/ai-engine/src/citevision_ai")
for rel in ["road_enforcement/traffic_light.py", "evidence/frigate_track_evidence.py"]:
    t = (win / rel).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    (dst / rel).write_text(t, encoding="utf-8", newline="\n")
tl = (dst / "road_enforcement/traffic_light.py").read_text()
assert "Prefer red" not in tl
assert 'raw_state == "red"' in tl
assert "motion < min_motion and streak < 2" in tl
fe = (dst / "evidence/frigate_track_evidence.py").read_text()
assert "_scene_light_state" in fe and "RED_LIGHT_MAX_ALIGN_SEC" in fe
print("sync_ok")
PY

bash scripts/restart-ai-engine.sh
for i in $(seq 1 60); do curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null && break; sleep 2; done
curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null
curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null || {
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 60
}
curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null || bash scripts/_sync_frontend_restart_wsl.sh || true

# Hard heal Frigate until young event
bash scripts/ensure-demo-streams.sh || true
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true
docker restart citevision-v2-go2rtc citevision-v2-frigate
sleep 20
bash scripts/ensure-demo-streams.sh || true
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true

python3 - <<'PY'
import json, time, urllib.request
fc = "cv_8ed20433-57d5-4999-a6ab-0bea028b23a3"
for i in range(60):
    try:
        ev = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5", timeout=10).read())
    except Exception as e:
        print("err", e); time.sleep(3); continue
    now = time.time()
    for e in (ev or []):
        age = now - float(e.get("start_time") or 0)
        if age <= 90:
            print(f"FRESH age={age:.0f}s"); raise SystemExit(0)
    print(f"wait {i}")
    time.sleep(3)
raise SystemExit(1)
PY

python3 scripts/_reset_demo_password.py 'Hologram2026!' || true
export ADMIN_PASSWORD='Hologram2026!'
export RULE_NAME='Démo · Feu rouge'
export RULE_DURATION_SEC=900
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
  print(f"  id={str(a.get('id',''))[:8]} src={meta.get('capture_source')} "
        f"scene_light={meta.get('scene_light_state')} align={meta.get('align_delta_ms')} "
        f"bbox_ok={meta.get('bbox_quality_ok')} subject_ok={meta.get('subject_quality_ok')}")
print("Review: http://127.0.0.1:5174/ → Alertes")
PY
grep -E 'traffic_light camera=|abort red_light|scene lamp' logs/ai-engine.log | tail -25 || true
curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null && echo UI_OK || echo UI_DOWN
exit $VC
