#!/usr/bin/env bash
# Bibliothèque E2E partagée (auth, caméra, zones, règles, preuves)
set -euo pipefail

E2E_API="${E2E_API:-http://localhost:8081}"
E2E_EMAIL="${E2E_EMAIL:-glory.henock@hologram.cd}"
E2E_PASS="${E2E_PASS:-Hologram2026!}"
E2E_POLL_SECS="${E2E_POLL_SECS:-90}"
E2E_RULE_SYNC_WAIT="${E2E_RULE_SYNC_WAIT:-35}"
E2E_POLYGON='[{"x":0.05,"y":0.05},{"x":0.95,"y":0.05},{"x":0.95,"y":0.95},{"x":0.05,"y":0.95}]'

e2e_root_dir() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd
}

e2e_python() {
  local root
  root="$(e2e_root_dir)"
  if [ -x "$root/ai-engine/.venv/bin/python3" ]; then
    echo "$root/ai-engine/.venv/bin/python3"
  else
    echo python3
  fi
}

e2e_ensure_stack() {
  local root
  root="$(e2e_root_dir)"
  # shellcheck source=scripts/lib/env-utils.sh
  source "$root/scripts/lib/env-utils.sh"
  bash "$root/scripts/ensure-rules-sync-env.sh"
  bash "$root/scripts/restart-api-frontend.sh"
  bash "$root/scripts/restart-ai-engine.sh"
  local env_file logdir
  env_file="$(ensure_env_file "$root")"
  logdir="$root/logs"
  stop_from_pid "$logdir/rules-engine.pid" || true
  free_port 8010 || true
  sleep 1
  export PATH="/usr/local/go/bin:$PATH"
  local go_bin
  go_bin="$(command -v go || echo /usr/local/go/bin/go)"
  start_bg rules-engine "$root/rules-engine" "$go_bin run ./cmd/rules-engine" "$logdir" "$env_file"
  for _ in $(seq 1 30); do
    curl -sf http://localhost:8010/health >/dev/null 2>&1 && break
    sleep 2
  done
}

e2e_login() {
  local login token org
  login=$(curl -sf -X POST "$E2E_API/api/v1/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$E2E_EMAIL\",\"password\":\"$E2E_PASS\"}")
  E2E_TOKEN=$(echo "$login" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
  E2E_ORG=$(curl -sf "$E2E_API/api/v1/auth/me" -H "Authorization: Bearer $E2E_TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")
  export E2E_TOKEN E2E_ORG
}

e2e_resolve_camera() {
  local info
  info=$(curl -sf "$E2E_API/api/v1/orgs/$E2E_ORG/cameras" -H "Authorization: Bearer $E2E_TOKEN" | python3 -c "
import sys, json
cams = json.load(sys.stdin)
cam = None
for c in cams:
    n = (c.get('name') or '').lower()
    if 'virtual' in n or 'benedicte' in n:
        cam = c
        break
if cam is None and cams:
    cam = cams[0]
if not cam:
    sys.exit(1)
print(cam['id'], cam.get('site_id', ''))
")
  E2E_CAMERA_ID=$(echo "$info" | awk '{print $1}')
  E2E_SITE_ID=$(echo "$info" | awk '{print $2}')
  export E2E_CAMERA_ID E2E_SITE_ID
}

e2e_ensure_zone() {
  local name="$1"
  local kind="${2:-}"
  local polygon="${3:-$E2E_POLYGON}"
  E2E_ZONE_NAME="$name"
  E2E_ZONE_ID=$(ZONE_NAME="$name" curl -sf "$E2E_API/api/v1/orgs/$E2E_ORG/zones?camera_id=$E2E_CAMERA_ID" \
    -H "Authorization: Bearer $E2E_TOKEN" | python3 -c "
import sys, json, os
zones = json.load(sys.stdin)
name = os.environ.get('ZONE_NAME', '')
for z in zones:
    if z.get('name') == name:
        print(z['id']); break
")
  if [ -z "${E2E_ZONE_ID:-}" ]; then
    local body
    body=$(python3 -c "import json; print(json.dumps({
        'name': '$name', 'site_id': '$E2E_SITE_ID', 'camera_id': '$E2E_CAMERA_ID',
        'polygon': $polygon, 'color': '#3b82f6', 'zone_kind': '$kind'
    }))")
    E2E_ZONE_ID=$(curl -sf -X POST "$E2E_API/api/v1/orgs/$E2E_ORG/zones" \
      -H "Authorization: Bearer $E2E_TOKEN" -H 'Content-Type: application/json' \
      -d "$body" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
    echo "[E2E] created zone=$E2E_ZONE_ID name=$name kind=$kind"
  else
    echo "[E2E] reuse zone=$E2E_ZONE_ID name=$name"
  fi
  export E2E_ZONE_ID E2E_ZONE_NAME
}

e2e_ensure_line() {
  local name="$1"
  E2E_LINE_NAME="$name"
  E2E_LINE_ID=$(LINE_NAME="$name" curl -sf "$E2E_API/api/v1/orgs/$E2E_ORG/lines?camera_id=$E2E_CAMERA_ID" \
    -H "Authorization: Bearer $E2E_TOKEN" | python3 -c "
import sys, json, os
lines = json.load(sys.stdin)
name = os.environ.get('LINE_NAME', '')
for l in lines:
    if l.get('name') == name:
        print(l['id']); break
" 2>/dev/null || true)
  if [ -z "${E2E_LINE_ID:-}" ]; then
    local body='{"name":"'"$name"'","site_id":"'"$E2E_SITE_ID"'","camera_id":"'"$E2E_CAMERA_ID"'","start_point":{"x":0.1,"y":0.5},"end_point":{"x":0.9,"y":0.5},"direction":"both"}'
    E2E_LINE_ID=$(curl -sf -X POST "$E2E_API/api/v1/orgs/$E2E_ORG/lines" \
      -H "Authorization: Bearer $E2E_TOKEN" -H 'Content-Type: application/json' \
      -d "$body" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
    echo "[E2E] created line=$E2E_LINE_ID name=$name"
  fi
  export E2E_LINE_ID E2E_LINE_NAME
}

e2e_create_rule() {
  local name="$1"
  local template_id="$2"
  local event_type="$3"
  local extra_json="${4:-}"
  if [ -z "$extra_json" ]; then extra_json='{}'; fi
  local zone_name="${5:-$E2E_ZONE_NAME}"
  local class_filter="${6:-person}"
  local duration="${7:-3}"
  local py rule_def resp
  py="$(e2e_python)"
  rule_def=$(EXTRA_JSON="$extra_json" EVENT_TYPE="$event_type" ZONE_NAME="$zone_name" \
    CLASS_FILTER="$class_filter" TEMPLATE_ID="$template_id" DURATION="$duration" \
    E2E_CAMERA_ID="$E2E_CAMERA_ID" "$py" -c "
import json, os
extra = json.loads(os.environ['EXTRA_JSON'])
children = [
    {'op': 'eq', 'field': 'event_type', 'value': os.environ['EVENT_TYPE']},
]
if os.environ.get('ZONE_NAME'):
    children.append({'op': 'eq', 'field': 'zone_id', 'value': os.environ['ZONE_NAME']})
if os.environ.get('CLASS_FILTER') and os.environ['CLASS_FILTER'] != 'any':
    children.append({'op': 'matches_class', 'field': 'class_name', 'value': os.environ['CLASS_FILTER']})
children.extend(extra.get('extra_conditions', []))
definition = {
    'condition': {'op': 'AND', 'children': children},
    'actions': [{'type': 'alert', 'config': {'severity': extra.get('severity', 'medium')}}],
    'camera_id': os.environ['E2E_CAMERA_ID'],
    'bindings': {
        'template_id': os.environ['TEMPLATE_ID'],
        'camera_id': os.environ['E2E_CAMERA_ID'],
        'zone_name': os.environ.get('ZONE_NAME', ''),
        'duration_seconds': int(os.environ['DURATION']),
        'class_filter': os.environ.get('CLASS_FILTER', 'person'),
    },
}
if extra.get('sequence'):
    definition['condition'] = extra['sequence']
print(json.dumps(definition))
")
  resp=$(curl -sf -X POST "$E2E_API/api/v1/orgs/$E2E_ORG/rules" \
    -H "Authorization: Bearer $E2E_TOKEN" -H 'Content-Type: application/json' \
    -d "{\"name\":\"$name\",\"description\":\"e2e auto\",\"priority\":10,\"definition\":$rule_def}" 2>&1) || {
    echo "[E2E] rule create failed: $resp" >&2
    return 1
  }
  E2E_RULE_ID=$(echo "$resp" | "$py" -c "import sys,json; print(json.load(sys.stdin)['id'])")
  echo "[E2E] rule=$E2E_RULE_ID event=$event_type tpl=$template_id"
  sleep "$E2E_RULE_SYNC_WAIT"
  export E2E_RULE_ID
}

e2e_wait_event() {
  local event_type="$1"
  local class_filter="${2:-}"
  local zone_name="${3:-}"
  local found=0
  local i match
  for i in $(seq 1 "$E2E_POLL_SECS"); do
    match=$(curl -sf "$E2E_API/api/v1/orgs/$E2E_ORG/events?limit=40&rule_linked=true" \
      -H "Authorization: Bearer $E2E_TOKEN" | EVENT_TYPE="$event_type" CLASS="$class_filter" ZONE="$zone_name" python3 -c "
import sys, json, os
et_want = os.environ.get('EVENT_TYPE','')
cls = os.environ.get('CLASS','')
zone = os.environ.get('ZONE','')
for e in json.load(sys.stdin):
    p = e.get('payload') or e
    et = p.get('event_type') or e.get('event_type')
    if et != et_want:
        continue
    if cls and p.get('class_name') != cls:
        continue
    if zone and p.get('zone_id') != zone:
        continue
    mr = e.get('matched_rule_id') or p.get('matched_rule_id')
    if not mr:
        continue
    print(json.dumps({'event_type': et, 'matched_rule_id': mr, 'class_name': p.get('class_name'), 'zone_id': p.get('zone_id')}))
    break
" 2>/dev/null || true)
    if [ -n "$match" ]; then
      echo "PASS event ${event_type} after ${i}s: $match"
      E2E_MATCHED_RULE=$(echo "$match" | python3 -c "import sys,json; print(json.load(sys.stdin).get('matched_rule_id',''))")
      export E2E_MATCHED_RULE
      return 0
    fi
    sleep 1
  done
  echo "FAIL: no event $event_type in ${E2E_POLL_SECS}s"
  return 1
}

e2e_assert_evidence() {
  local rule_id="${1:-$E2E_MATCHED_RULE}"
  local ok_ev=0 ok_al=0 j k
  for j in $(seq 1 45); do
  local ev
  ev=$(curl -sf "$E2E_API/api/v1/orgs/$E2E_ORG/events?limit=30&rule_linked=true" -H "Authorization: Bearer $E2E_TOKEN" \
    | RULE_ID="$rule_id" python3 -c "
import sys,json,os
rid=os.environ.get('RULE_ID','')
for e in json.load(sys.stdin):
    mr=e.get('matched_rule_id') or (e.get('payload') or {}).get('matched_rule_id')
    if rid and mr and mr!=rid: continue
    pkg=(e.get('evidence_snapshot') or {}).get('package') or {}
    clip=(pkg.get('clip') or {}).get('url') or ''
    roles={i.get('role') for i in (pkg.get('images') or []) if i.get('url')}
    if clip and 'scene' in roles and 'subject' in roles:
        print('ok'); break
" 2>/dev/null || true)
    [ "$ev" = ok ] && ok_ev=1 && break
    sleep 2
  done
  for k in $(seq 1 30); do
  local al
  al=$(curl -sf "$E2E_API/api/v1/orgs/$E2E_ORG/alerts?limit=20" -H "Authorization: Bearer $E2E_TOKEN" \
    | RULE_ID="$rule_id" python3 -c "
import sys,json,os
rid=os.environ.get('RULE_ID','')
for a in json.load(sys.stdin):
    if rid and a.get('rule_id') and a.get('rule_id')!=rid: continue
    pkg=(a.get('evidence_snapshot') or {}).get('package') or {}
    clip=(pkg.get('clip') or {}).get('url') or ''
    roles={i.get('role') for i in (pkg.get('images') or []) if i.get('url')}
    if clip and 'scene' in roles and 'subject' in roles:
        print('ok'); break
" 2>/dev/null || true)
    [ "$al" = ok ] && ok_al=1 && break
    sleep 2
  done
  if [ "$ok_ev" -eq 1 ] && [ "$ok_al" -eq 1 ]; then
    echo "PASS evidence complete (event+alert)"
    return 0
  fi
  echo "FAIL evidence event=$ok_ev alert=$ok_al"
  return 1
}

e2e_optional_module() {
  "$(e2e_python)" -c "import $1" 2>/dev/null
}
