#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
LOGDIR=$ROOT/logs
GO_BIN=/usr/local/go/bin/go

# Backend/AI/rules health
if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
  free_port 8081
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90
fi
if ! curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
  bash scripts/restart-ai-engine.sh
fi
if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh
fi

# Sync AI evidence code once more + restart AI clean (Frigate stays)
cp -f /mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/service.py \
  "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"
cp -f /mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py \
  "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py"
cp -f /mnt/c/Users/gheno/citevision/scripts/_validate_rule_frigate_1hit.py \
  "$ROOT/scripts/_validate_rule_frigate_1hit.py"
sed -i 's/\r$//' "$ROOT/ai-engine/src/citevision_ai/evidence/"*.py "$ROOT/scripts/_validate_rule_frigate_1hit.py"

: > "$ROOT/logs/ai-engine.log"
bash scripts/restart-ai-engine.sh

# Repair streams + confirm media still works
curl -sf -X POST -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true
python3 - <<'PY'
import json,urllib.request,time
fc="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
ok=False
for i in range(24):
  ev=json.loads(urllib.request.urlopen(f"http://127.0.0.1:5000/api/events?cameras={fc}&limit=3", timeout=8).read())
  now=time.time()
  if not ev: time.sleep(5); continue
  young=min(now-float(e["start_time"]) for e in ev)
  eid=ev[0]["id"]
  try:
    with urllib.request.urlopen(f"http://127.0.0.1:5000/api/events/{eid}/clip.mp4", timeout=20) as r:
      n=len(r.read(4096)); code=200
  except Exception as e:
    code=getattr(e,"code",0); n=0
  print(f"precheck {i} young={young:.0f}s clip_http={code} peek={n}")
  if young<=60 and code==200 and n>500:
    ok=True; break
  time.sleep(5)
assert ok, "frigate clip not ready"
PY

# Ensure backend survived AI restart
if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90
fi
python3 scripts/_reset_demo_password.py 'Hologram2026!'

export ADMIN_PASSWORD='Hologram2026!'
export RULE_NAME='Démo · Excès de vitesse'
export RULE_DURATION_SEC=600
export PYTHONUNBUFFERED=1
# Avoid frigate rebuild during validate if possible — config already good.
# Validator still rebuilds; that's OK now that strict_frigate forces record.
python3 scripts/_validate_rule_frigate_1hit.py
echo "VALIDATE_EXIT=$?"

# Dump latest alert evidence
python3 - <<'PY'
import subprocess
sql='''
SELECT a.id::text, a.created_at,
  a.evidence_snapshot->'package'->'metadata'->>'capture_source' AS src,
  a.evidence_snapshot->'package'->'metadata'->>'frigate_event_id' AS fev,
  (a.evidence_snapshot->'package'->'clip') IS NOT NULL AS has_clip,
  jsonb_array_length(COALESCE(a.evidence_snapshot->'package'->'images','[]'::jsonb)) AS n_images
FROM alerts a
WHERE a.org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid
ORDER BY a.created_at DESC LIMIT 3;
'''
r=subprocess.run(["docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-c",sql],
  capture_output=True,text=True)
print(r.stdout or r.stderr)
PY
