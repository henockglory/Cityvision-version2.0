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

# Sync compiler + evidence
cp -f /mnt/c/Users/gheno/citevision/backend/internal/frigate/compiler.go \
  "$ROOT/backend/internal/frigate/compiler.go"
cp -f /mnt/c/Users/gheno/citevision/backend/internal/frigate/compiler_test.go \
  "$ROOT/backend/internal/frigate/compiler_test.go" 2>/dev/null || true
sed -i 's/\r$//' "$ROOT/backend/internal/frigate/compiler.go"

grep -q 'strict_frigate' "$ROOT/backend/internal/frigate/compiler.go"
grep -q '^DEMO_EVIDENCE_BACKEND=strict_frigate' "$ROOT/.env"
echo "env DEMO_EVIDENCE_BACKEND=$(grep '^DEMO_EVIDENCE_BACKEND=' "$ROOT/.env")"

# Update test for strict_frigate force
cat > /tmp/patch_compiler_test.py <<'PY'
from pathlib import Path
p=Path("/home/gheno/citevision-v2/backend/internal/frigate/compiler_test.go")
if not p.exists():
  raise SystemExit(0)
text=p.read_text()
if "TestUpsertCameraStrictFrigateForcesRecord" not in text:
  text += '''

func TestUpsertCameraStrictFrigateForcesRecord(t *testing.T) {
	t.Setenv("FRIGATE_EVIDENCE", "true")
	t.Setenv("FRIGATE_DEMO_MODE", "true")
	t.Setenv("DEMO_EVIDENCE_BACKEND", "strict_frigate")
	cam := &models.Camera{ID: uuid.New()}
	agg := EvidenceAggregate{RecordEnabled: false, SnapshotsEnabled: false}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, agg, nil)
	if !cc.Entry.Record.Enabled || !cc.Entry.Snapshots.Enabled {
		t.Fatal("strict_frigate demo must force record+snapshots")
	}
}
'''
  p.write_text(text)
  print("test added")
else:
  print("test exists")
PY
python3 /tmp/patch_compiler_test.py
sed -i 's/\r$//' "$ROOT/backend/internal/frigate/compiler_test.go" 2>/dev/null || true

# Also fix Windows compiler_test for consistency
python3 - <<'PY'
from pathlib import Path
p=Path("/mnt/c/Users/gheno/citevision/backend/internal/frigate/compiler_test.go")
text=p.read_text(encoding="utf-8")
# Update old test: without strict_frigate still respects aggregate
# Add strict test if missing
if "TestUpsertCameraStrictFrigateForcesRecord" not in text:
  text += '''

func TestUpsertCameraStrictFrigateForcesRecord(t *testing.T) {
	t.Setenv("FRIGATE_EVIDENCE", "true")
	t.Setenv("FRIGATE_DEMO_MODE", "true")
	t.Setenv("DEMO_EVIDENCE_BACKEND", "strict_frigate")
	cam := &models.Camera{ID: uuid.New()}
	agg := EvidenceAggregate{RecordEnabled: false, SnapshotsEnabled: false}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, agg, nil)
	if !cc.Entry.Record.Enabled || !cc.Entry.Snapshots.Enabled {
		t.Fatal("strict_frigate demo must force record+snapshots")
	}
}
'''
  p.write_text(text, encoding="utf-8", newline="\n")
  print("windows test patched")
PY

echo "=== rebuild backend ==="
stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
free_port 8081
(cd backend && "$GO_BIN" test ./internal/frigate/ -count=1)
(cd backend && "$GO_BIN" build -o bin/citevision-api ./cmd/api)
start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
wait_http_ok http://127.0.0.1:8081/health 90

# Enable speed rule (nice to have) then rebuild frigate
python3 scripts/_reset_demo_password.py 'Hologram2026!'
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
print("speed ON")
PY

echo "=== frigate rebuild ==="
curl -sS -w "\nHTTP=%{http_code}\n" --max-time 180 -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild || true

python3 - <<'PY'
from pathlib import Path
import re
text=Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml").read_text()
cam="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
for key in ("record","snapshots"):
  m=re.search(rf"{re.escape(cam)}:.*?{key}:\s*\n\s*enabled:\s*(true|false)", text, re.S)
  print(key, m.group(1) if m else "?")
  assert m and m.group(1)=="true", f"{key} must be true"
print("CONFIG_OK")
PY

docker restart citevision-v2-frigate
sleep 40
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true
sleep 20

echo "=== wait young events with working clip ==="
python3 - <<'PY'
import json,time,urllib.request
fc="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
ok=False
for i in range(48):
  try:
    ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=5", timeout=8).read())
  except Exception as e:
    print("err", e); time.sleep(5); continue
  now=time.time()
  if not isinstance(ev,list) or not ev:
    print("empty"); time.sleep(5); continue
  young=min(now-float(e["start_time"]) for e in ev if isinstance(e.get("start_time"),(int,float)))
  eid=ev[0].get("id")
  # probe clip
  code=0
  try:
    req=urllib.request.Request(f"http://127.0.0.1:5000/api/events/{eid}/clip.mp4", method="GET")
    with urllib.request.urlopen(req, timeout=20) as r:
      data=r.read(2048); code=200; sz=len(data)
  except Exception as e:
    code=getattr(e,"code",0); sz=0
  print(f"try {i} young={young:.0f}s clip_http={code} peek={sz} id={str(eid)[:20]}")
  if young<=45 and code==200 and sz>500:
    ok=True; break
  time.sleep(5)
print("MEDIA", "OK" if ok else "FAIL")
raise SystemExit(0 if ok else 2)
PY
