#!/usr/bin/env bash
# Désactive toutes les règles sauf 3 règles de test : présence zone, franchissement ligne, intrusion zone.
set -euo pipefail

API_URL="${API_URL:-http://localhost:8081}"

TOKEN=$(curl -sf "$API_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"'"${ADMIN_EMAIL:-glory.henock@hologram.cd}"'","password":"'"${ADMIN_PASSWORD:-Hologram2026!}"'"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)

if [ -z "$TOKEN" ]; then
  echo "Login failed — run setup first"
  exit 1
fi

ORG_ID=$(curl -sf "$API_URL/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")

export TOKEN ORG_ID API_URL

RULES_JSON=$(curl -sf "$API_URL/api/v1/orgs/$ORG_ID/rules" -H "Authorization: Bearer $TOKEN")

echo "$RULES_JSON" | python3 -c "
import json, os, subprocess, sys, urllib.request

rules = json.load(sys.stdin)
api = os.environ.get('API_URL', 'http://localhost:8081')
token = os.environ.get('TOKEN', '')
org = os.environ.get('ORG_ID', '')

KEEP_ORDER = (
    ('zone_presence', ('zone_presence', 'e2e-presence', 'présence zone', 'presence')),
    ('line_cross', ('line_cross', 'franchissement', 'line cross')),
    ('intrusion', ('zone_enter', 'intrusion', 'zone enter')),
)

def should_keep(rule, kept_ids):
    if rule['id'] in kept_ids:
        return True
    return False

def pick_keep_rules(rules):
    enabled = [r for r in rules if r.get('is_enabled')]
    kept = []
    kept_ids = set()
    blob_all = {r['id']: (r.get('name') or '').lower() + ' ' + json.dumps(r.get('definition') or {}).lower() for r in enabled}
    for _label, keys in KEEP_ORDER:
        for r in enabled:
            if r['id'] in kept_ids:
                continue
            if any(k in blob_all[r['id']] for k in keys):
                kept.append(r)
                kept_ids.add(r['id'])
                break
    return kept_ids

enabled_before = sum(1 for r in rules if r.get('is_enabled'))
keep_ids = pick_keep_rules(rules)
to_disable = [r for r in rules if r.get('is_enabled') and r['id'] not in keep_ids]
print(f'Active rules before: {enabled_before}')
print(f'Keeping {len(keep_ids)} test rules, disabling {len(to_disable)}')

for r in to_disable:
    rid = r['id']
    subprocess.run([
        'curl', '-sf', '-o', '/dev/null', '-X', 'PATCH', f'{api}/api/v1/orgs/{org}/rules/{rid}',
        '-H', f'Authorization: Bearer {token}',
        '-H', f'X-Org-ID: {org}',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps({'is_enabled': False}),
    ], check=False)
    print(f'  [disabled] {r.get(\"name\", rid)}')

enabled_after = enabled_before - len(to_disable)
try:
    req = urllib.request.Request(
        f'{api}/api/v1/orgs/{org}/rules',
        headers={'Authorization': f'Bearer {token}', 'X-Org-ID': org},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        after = json.load(resp)
    enabled_after = sum(1 for r in after if r.get('is_enabled'))
except Exception as ex:
    print(f'  (re-count skipped: {ex})')

print(f'Active rules after (approx): {enabled_after}')
print('[OK] trim-test-rules complete')
" TOKEN="$TOKEN" ORG_ID="$ORG_ID" API_URL="$API_URL"
