#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export PATH="/usr/local/go/bin:/usr/bin:/bin:$PATH"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
LOGDIR="$ROOT/logs"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || GO_BIN="$(command -v go)"

# Backend
if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  echo "restarting backend"
  stop_from_pid "$LOGDIR/backend.pid" 2>/dev/null || true
  free_port 8081 2>/dev/null || true
  (cd backend && "$GO_BIN" build -o bin/citevision-api ./cmd/api)
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$LOGDIR" "$ENV_FILE"
  wait_http_ok "http://127.0.0.1:8081/health" 90
fi

# Rules
if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh
fi

# AI
if ! curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
  bash scripts/restart-ai-engine.sh
fi

python3 scripts/_reset_demo_password.py 'Hologram2026!'

# Enable only speed + rebuild frigate record
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
    if not name.startswith("Démo"): continue
    want=name==RULE
    urllib.request.urlopen(urllib.request.Request(
        f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}",
        data=json.dumps({"is_enabled":want}).encode(),
        headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, method="PATCH"))
print("rules ok")
PY

curl -sS -w "\nHTTP=%{http_code}\n" --max-time 180 -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/ingest/frigate/rebuild || true
curl -sS -w "\nHTTP=%{http_code}\n" --max-time 60 -X POST -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8081/api/v1/internal/demo/repair-streams || true

python3 - <<'PY'
from pathlib import Path
import re
text=Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml").read_text()
cam="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
m=re.search(rf"{re.escape(cam)}:.*?record:\s*\n\s*enabled:\s*(true|false)", text, re.S)
print("record", m.group(1) if m else "?")
PY

echo "=== health ==="
curl -sf http://127.0.0.1:8081/health && echo
curl -sf http://127.0.0.1:8001/health | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["status"],d["models_all_ok"])'
curl -sf http://127.0.0.1:8010/health | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d)'
