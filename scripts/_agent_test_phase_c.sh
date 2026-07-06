#!/usr/bin/env bash
set -euo pipefail
ROOT="${HOME}/citevision-v2"
# shellcheck source=scripts/lib/env-utils.sh
source "${ROOT}/scripts/lib/env-utils.sh"
load_dotenv "$(ensure_env_file "$ROOT")"

EMAIL="${ADMIN_EMAIL:-glory.henock@hologram.cd}"
PASS="${ADMIN_PASSWORD:-Henockglory@03}"
API="http://127.0.0.1:${API_PORT:-8081}/api/v1"

TOK=$(curl -s -X POST "${API}/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASS}\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

ORG=$(curl -s "${API}/auth/me" -H "Authorization: Bearer ${TOK}" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("org_id") or d.get("organization_id",""))')

echo "org=${ORG}"
curl -s "${API}/orgs/${ORG}/capabilities/menu" -H "Authorization: Bearer ${TOK}" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("behaviors",len(d.get("behaviors",[])),"health",list(d.get("health",{}).keys())[:6])'

echo "scene-intent validate (speed template stub)"
curl -s -X POST "${API}/orgs/${ORG}/scene-intent/validate" \
  -H "Authorization: Bearer ${TOK}" \
  -H 'Content-Type: application/json' \
  -d '{"definition":{"bindings":{"template_id":"tpl-speeding-premium","camera_id":"00000000-0000-0000-0000-000000000001","zone_name":"Zone_test"},"condition":{"op":"eq","field":"event_type","value":"speeding"}}}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("valid",d.get("valid"),"errors",d.get("errors"))'
