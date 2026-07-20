#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

# Sync evidence soften only
python3 - <<'PY'
from pathlib import Path
s = Path("/mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py")
d = Path("/home/gheno/citevision-v2/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py")
t = s.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
assert "ship partial" in t
assert "import urllib.error" in t
d.write_text(t, encoding="utf-8", newline="\n")
print("evidence_synced")
PY
bash scripts/restart-ai-engine.sh
for i in $(seq 1 60); do curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null && break; sleep 2; done
curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null || { echo AI_FAIL; exit 1; }
curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null || bash scripts/_sync_frontend_restart_wsl.sh || true
curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null || {
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 60
}

python3 scripts/_reset_demo_password.py 'Hologram2026!' || true

export ADMIN_PASSWORD='Hologram2026!'
export RULE_NAME='Démo · Feu rouge'
export RULE_DURATION_SEC=600
export SKIP_FRIGATE_REBUILD=1
export FRIGATE_MAX_ALIGN_MS=30000
export PYTHONUNBUFFERED=1

echo "UI http://127.0.0.1:5174/ — validation feu démarre"
set +e
python3 scripts/_validate_rule_frigate_1hit.py
VC=$?
set -e
echo "VALIDATE_EXIT=$VC"

# Print latest alert evidence for UI review
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
curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null && echo UI_STILL_OK || echo UI_DOWN
exit $VC
