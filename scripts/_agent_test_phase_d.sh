#!/usr/bin/env bash
set -euo pipefail
ROOT="${HOME}/citevision-v2"
source "${ROOT}/scripts/lib/env-utils.sh"
load_dotenv "$(ensure_env_file "$ROOT")"

EMAIL="${ADMIN_EMAIL:-glory.henock@hologram.cd}"
PASS="${ADMIN_PASSWORD:-Henockglory@03}"
API="http://127.0.0.1:${API_PORT:-8081}/api/v1"

TOK=$(curl -sf -X POST "${API}/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASS}\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

ORG=$(curl -sf "${API}/auth/me" -H "Authorization: Bearer ${TOK}" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("org_id") or d.get("organization_id",""))')

echo "org=${ORG}"
curl -sf "${API}/orgs/${ORG}/ai/model-pack" -H "Authorization: Bearer ${TOK}" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
models=d.get('models',[])
loaded=sum(1 for m in models if m.get('loaded'))
print('models',len(models),'loaded',loaded,'gpu',d.get('gpu_loaded'))
for m in models:
    st='OK' if m.get('loaded') else 'MISSING'
    print('  [%s] %s (%s)' % (st, m.get('id'), m.get('kind')))
"

echo ""
echo "== matrice (rapide) =="
python3 "${ROOT}/scripts/generate-rule-coverage-matrix.py" | tail -3
