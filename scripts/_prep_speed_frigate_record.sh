#!/usr/bin/env bash
# Enable speed rule → rebuild Frigate → verify record/snapshots → run 1-hit.
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

# Sync critical files from Windows
for f in \
  scripts/_validate_rule_frigate_1hit.py \
  scripts/_run_speed_1hit_wsl.sh \
  ai-engine/src/citevision_ai/evidence/service.py
do
  if [ -f "/mnt/c/Users/gheno/citevision/$f" ]; then
    cp -f "/mnt/c/Users/gheno/citevision/$f" "$ROOT/$f"
    sed -i 's/\r$//' "$ROOT/$f"
  fi
done

# Ensure FrameRingBuffer not truncated
python3 - <<'PY'
from pathlib import Path
p=Path("/home/gheno/citevision-v2/ai-engine/src/citevision_ai/evidence/service.py")
line=p.read_text().splitlines()[24]
assert "FrameRingBuffer" in line, repr(line)
print("service.py OK:", line)
PY

python3 scripts/_reset_demo_password.py 'Hologram2026!'

# Login + enable only speed rule
python3 - <<'PY'
import json, urllib.request
API="http://127.0.0.1:8081"
ORG="74d51ead-97a7-4e41-a488-503a9b90c466"
RULE="Démo · Excès de vitesse"
login=json.loads(urllib.request.urlopen(urllib.request.Request(
    f"{API}/api/v1/auth/login",
    data=json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode(),
    headers={"Content-Type":"application/json"}, method="POST")).read())
tok=login["access_token"]
rules=json.loads(urllib.request.urlopen(urllib.request.Request(
    f"{API}/api/v1/orgs/{ORG}/rules",
    headers={"Authorization":f"Bearer {tok}"})).read())
for r in rules:
    name=str(r.get("name",""))
    if not name.startswith("Démo"):
        continue
    want = name==RULE
    body=json.dumps({"is_enabled":want}).encode()
    urllib.request.urlopen(urllib.request.Request(
        f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}",
        data=body, headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"},
        method="PATCH"))
    print(f"  {name}: enabled={want}")
print("rules patched")
PY

echo "=== rebuild frigate ==="
curl -sS -w "\nHTTP=%{http_code}\n" --max-time 180 -X POST \
  -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild

echo "=== record flags in config ==="
python3 - <<'PY'
from pathlib import Path
text=Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml").read_text()
# crude: find speed cam block
cam="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
idx=text.find(cam)
print("cam_idx", idx)
chunk=text[idx:idx+800] if idx>=0 else text[:500]
print(chunk)
# also grep record enabled near cam
import re
m=re.search(rf"{re.escape(cam)}:.*?record:\s*\n\s*enabled:\s*(true|false)", text, re.S)
print("record_enabled_match", m.group(1) if m else None)
m2=re.search(rf"{re.escape(cam)}:.*?snapshots:\s*\n\s*enabled:\s*(true|false)", text, re.S)
print("snapshots_enabled_match", m2.group(1) if m2 else None)
PY

echo "=== restart frigate + repair streams ==="
docker restart citevision-v2-frigate
sleep 35
curl -sS -w "\nHTTP=%{http_code}\n" --max-time 60 -X POST \
  -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams
sleep 15

echo "=== fps + fresh events ==="
curl -sf http://127.0.0.1:5000/api/stats -o /tmp/fs.json
python3 - <<'PY'
import json,time,urllib.request
d=json.load(open("/tmp/fs.json"))
cams=d.get("cameras") or {}
fc="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
for k,v in cams.items():
    mark=" <<" if k==fc else ""
    print(f"  {k}: fps={v.get('camera_fps')} det={v.get('detection_fps')}{mark}")
# wait fresh
ok=False
for i in range(36):
    url=f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5"
    ev=json.loads(urllib.request.urlopen(url, timeout=8).read())
    now=time.time()
    if isinstance(ev,list) and ev:
        ages=[now-float(e["start_time"]) for e in ev if isinstance(e.get("start_time"),(int,float))]
        young=min(ages) if ages else 99999
        print(f"  try {i} youngest={young:.0f}s has_clip={ev[0].get('has_clip')}")
        if young<=40:
            ok=True
            break
    else:
        print(f"  try {i} events=0")
    time.sleep(5)
print("FRESH", "OK" if ok else "FAIL")
raise SystemExit(0 if ok else 2)
PY
