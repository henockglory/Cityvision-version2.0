#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

if ! curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null; then
  free_port 8081 || true
  start_bg backend "$ROOT/backend" "$ROOT/backend/bin/citevision-api" "$ROOT/logs" "$ENV_FILE"
  wait_http_ok http://127.0.0.1:8081/health 90 || true
fi
if ! curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null; then
  bash scripts/restart-ai-engine.sh || true
fi
if ! curl -sf --max-time 3 http://127.0.0.1:5174/ >/dev/null; then
  bash scripts/_sync_frontend_restart_wsl.sh || true
fi
if ! curl -sf --max-time 3 http://127.0.0.1:8010/health >/dev/null; then
  bash scripts/_start-rules-engine.sh || true
fi

echo "UI $(curl -sf --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:5174/ || echo DOWN)"
echo "BE $(curl -sf --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8081/health || echo DOWN)"
echo "AI $(curl -sf --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/health || echo DOWN)"

python3 - <<'PY'
import json, urllib.request
API="http://127.0.0.1:8081"
ORG="74d51ead-97a7-4e41-a488-503a9b90c466"
body=json.dumps({"email":"glory.henock@hologram.cd","password":"Hologram2026!"}).encode()
tok=json.loads(urllib.request.urlopen(urllib.request.Request(
  f"{API}/api/v1/auth/login",data=body,headers={"Content-Type":"application/json"},method="POST"),timeout=15).read())["access_token"]
h={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}
rules=json.loads(urllib.request.urlopen(urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules",headers=h),timeout=20).read())
items=rules if isinstance(rules,list) else rules.get("rules") or rules.get("items") or []
for r in items:
  if r.get("name")=="Démo · Feu rouge":
    data=json.dumps({"is_enabled":True}).encode()
    req=urllib.request.Request(f"{API}/api/v1/orgs/{ORG}/rules/{r['id']}",data=data,headers=h,method="PATCH")
    urllib.request.urlopen(req,timeout=30).read()
    print("enabled Démo · Feu rouge")
    break
print("Visual: http://127.0.0.1:5174/ → Alertes")
PY
