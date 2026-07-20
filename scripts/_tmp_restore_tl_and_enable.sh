#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
git show HEAD:ai-engine/src/citevision_ai/road_enforcement/traffic_light.py > /tmp/tl_head.py
python3 /mnt/c/Users/gheno/citevision/scripts/_tmp_restore_tl.py
# keep evidence quality files from Windows (bbox fail-closed) — already on WSL if restored earlier
bash "$ROOT/scripts/restart-ai-engine.sh"
for i in $(seq 1 60); do
  curl -sf --max-time 3 http://127.0.0.1:8001/health >/dev/null && echo AI_UP && break
  sleep 2
done
curl -sf --max-time 3 -o /dev/null -w "UI %{http_code}\n" http://127.0.0.1:5174/ || echo UI_DOWN
curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null && echo BE_OK || echo BE_DOWN
# re-enable feu rule for visual check (no zone writes)
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"
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
    print("enabled", r["id"][:8], "is_enabled was", r.get("is_enabled"))
    break
else:
  print("rule not found")
print("Open http://127.0.0.1:5174/ → Alertes (caméra feu)")
PY
