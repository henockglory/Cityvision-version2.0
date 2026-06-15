#!/usr/bin/env bash
set -euo pipefail
API="${API:-http://localhost:8081}"
FE="${FE:-http://localhost:5174}"
EMAIL="${EMAIL:-glory.henock@hologram.cd}"
PASS="${PASS:-Hologram2026!}"

echo "=== Déploiement WSL (checklist opérateur) ==="
echo "1. rsync Windows → WSL (exclure node_modules, .venv, infra/data)"
echo "2. bash scripts/restart-api-frontend.sh"
echo "3. Ouvrir ${FE} (pas :5173) + Ctrl+Shift+R"
echo ""

echo "=== Login ==="
LOGIN=$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
REFRESH=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print('refresh_len',len(d.get('refresh_token','')),'expires',d.get('expires_in'))")
ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")
echo "org=$ORG $REFRESH"

echo "=== Catalog (strict supported + configSchema) ==="
curl -sf "$API/api/v1/orgs/$ORG/rules/catalog" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
items=json.load(sys.stdin)
supported=sum(1 for t in items if t.get('supported'))
with_schema=sum(1 for t in items if t.get('configSchema',{}).get('fields'))
honest=sum(1 for t in items if t.get('supported') and (t.get('configSchema') or {}).get('fields'))
print('total',len(items),'supported',supported,'with_configSchema',with_schema,'honest_activable',honest)
for t in items:
  if t.get('supported'):
    print(' +',t.get('id'),'fields=',len((t.get('configSchema') or {}).get('fields') or []))
"

echo "=== Events sample (matched_rule_id) ==="
curl -sf "$API/api/v1/orgs/$ORG/events?limit=5" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
items=json.load(sys.stdin)
if not items: print('no events'); sys.exit(0)
matched=sum(1 for e in items if e.get('matched_rule_id') or (e.get('payload') or {}).get('matched_rule_id'))
print('sample',len(items),'with_matched_rule',matched)
e=items[0]
print('type',e.get('event_type'),'label_fr',e.get('label_fr'),'rule',e.get('rule_name'))
"

echo "=== Frontend build marker ==="
curl -sf "$FE/" | head -5 || echo "frontend unreachable on $FE"
curl -sf "$FE/src/lib/buildInfo.ts" 2>/dev/null | head -3 || echo "(vite dev — marker in AppLayout footer)"

echo "=== Politique alertes (no-delete API) ==="
echo "Purge ponctuelle: POST /api/v1/orgs/{org}/demo/purge-alerts ou scripts/purge-alerts-demo.sh"
echo "Aucun DELETE /alerts — archivage uniquement via PATCH .../archive"

echo "=== Alerts (open) ==="
curl -sf "$API/api/v1/orgs/$ORG/alerts?status=open&limit=3" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
items=json.load(sys.stdin)
print('open_count_sample',len(items))
if items:
  a=items[0]
  ev=a.get('evidence_snapshot') or {}
  print('fields',list(ev.keys())[:8],'archived_at',a.get('archived_at'))
" || echo "alerts check failed"

echo "=== Ports ==="
ss -tlnp 2>/dev/null | grep -E ':5174|:8081|:8010' || netstat -tlnp 2>/dev/null | grep -E ':5174|:8081|:8010' || echo "ports check skipped"
