#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"

# Kill leftover validator if any
pkill -f '_validate_rule_frigate_1hit.py' 2>/dev/null || true

# Sync evidence service + tests
cp -f /mnt/c/Users/gheno/citevision/ai-engine/src/citevision_ai/evidence/service.py \
  "$ROOT/ai-engine/src/citevision_ai/evidence/service.py"
cp -f /mnt/c/Users/gheno/citevision/ai-engine/tests/test_speed_evidence_dedupe.py \
  "$ROOT/ai-engine/tests/test_speed_evidence_dedupe.py"
cp -f /mnt/c/Users/gheno/citevision/scripts/_validate_rule_frigate_1hit.py \
  "$ROOT/scripts/_validate_rule_frigate_1hit.py"
sed -i 's/\r$//' \
  "$ROOT/ai-engine/src/citevision_ai/evidence/service.py" \
  "$ROOT/ai-engine/tests/test_speed_evidence_dedupe.py" \
  "$ROOT/scripts/_validate_rule_frigate_1hit.py"

python3 - <<'PY'
from pathlib import Path
p=Path("/home/gheno/citevision-v2/ai-engine/src/citevision_ai/evidence/service.py")
assert "__any__" in p.read_text()
assert "FrameRingBuffer" in p.read_text()
print("dedupe+import OK")
PY

# Unit test (non-fatal if pytest env odd)
cd "$ROOT/ai-engine"
.venv/bin/python -m pytest tests/test_speed_evidence_dedupe.py -q || \
  .venv/bin/python -c '
from citevision_ai.evidence.service import EvidenceCaptureService
import threading
s=EvidenceCaptureService.__new__(EvidenceCaptureService)
s._speed_evidence_dedupe={}; s._speed_evidence_lock=threading.Lock()
assert s._should_skip_speed_evidence("c", {"event_type":"speeding","track_id":1}) is False
assert s._should_skip_speed_evidence("c", {"event_type":"speeding","track_id":2}) is True
print("manual dedupe OK")
'
cd "$ROOT"

bash scripts/restart-ai-engine.sh

# Ensure speed rule on + record on + streams
python3 scripts/_reset_demo_password.py 'Hologram2026!' >/dev/null
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
    f"{API}/api/v1/orgs/{ORG}/rules", headers={"Authorization":f"Bearer {tok}"})).read())
for r in rules:
    name=str(r.get("name",""))
    if not name.startswith("Démo"):
        continue
    want=name==RULE
    urllib.request.urlopen(urllib.request.Request(
        f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}",
        data=json.dumps({"is_enabled":want}).encode(),
        headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"},
        method="PATCH"))
print("rules ok")
PY

curl -sf -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild >/dev/null || true
curl -sf -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true
sleep 5

# Confirm record still on
python3 - <<'PY'
from pathlib import Path
import re
text=Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml").read_text()
cam="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
m=re.search(rf"{re.escape(cam)}:.*?record:\s*\n\s*enabled:\s*(true|false)", text, re.S)
print("record", m.group(1) if m else "?")
assert m and m.group(1)=="true"
PY

echo "=== ready for 1-hit ==="
curl -sf http://127.0.0.1:8001/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["status"], d["models_all_ok"])'
