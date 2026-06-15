#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
ENV_FILE="$(ensure_env_file "$ROOT")"
load_dotenv "$ENV_FILE"

API="${API:-http://localhost:8081}"
EMAIL="${EMAIL:-glory.henock@hologram.cd}"
PASS="${PASS:-Hologram2026!}"

echo "=== Login ==="
LOGIN=$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
ORG=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('user',{}).get('org_id') or '')")
if [[ -z "$ORG" ]]; then
  ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")
fi
echo "org=$ORG"

echo "=== Purge alertes (API admin démo) ==="
curl -sf -X POST "$API/api/v1/orgs/$ORG/demo/purge-alerts" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' | python3 -m json.tool

echo ""
echo "Liste alertes après purge:"
curl -sf "$API/api/v1/orgs/$ORG/alerts?status=open" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print('count',len(d))"
