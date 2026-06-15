#!/usr/bin/env bash
# Scénario E2E : zone → règle présence (personne) → événement zone_presence → alerte liée
#
# Prérequis :
#   - API (:8081), rules-engine (:8010), AI engine avec caméra Benedicte/virtual active
#   - bash scripts/restart-api-frontend.sh (ou start-linux.sh) après déploiement
#
# Checklist manuelle opérateur :
#   1. Dessiner une zone sur le flux Benedicte couvrant les personnes
#   2. Activer « Présence dans une zone » avec objet = Personne, durée 3–5 s
#   3. Vérifier le journal d'événements (type zone_presence, class_name=person)
#   4. Confirmer l'alerte avec matched_rule_id dans l'UI
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$SCRIPT_DIR/lib/env-utils.sh"

API="${API:-http://localhost:8081}"
EMAIL="${EMAIL:-glory.henock@hologram.cd}"
PASS="${PASS:-Hologram2026!}"
CLEANUP="${CLEANUP:-0}"
POLL_SECS="${POLL_SECS:-90}"
ZONE_NAME="${ZONE_NAME:-e2e-presence-test}"
DURATION="${DURATION:-3}"

echo "=== E2E zone_presence → alerte (Benedicte) ==="

bash "$SCRIPT_DIR/ensure-rules-sync-env.sh"
bash "$SCRIPT_DIR/restart-api-frontend.sh"
bash "$SCRIPT_DIR/restart-ai-engine.sh"
ENV_FILE="$(ensure_env_file "$SCRIPT_DIR/..")"
LOGDIR="$SCRIPT_DIR/../logs"
stop_from_pid "$LOGDIR/rules-engine.pid" || true
free_port 8010 || true
sleep 1
export PATH="/usr/local/go/bin:$PATH"
GO_BIN="$(command -v go || echo /usr/local/go/bin/go)"
start_bg rules-engine "$SCRIPT_DIR/../rules-engine" "$GO_BIN run ./cmd/rules-engine" "$LOGDIR" "$ENV_FILE"
for _ in $(seq 1 30); do
  if curl -sf http://localhost:8010/health >/dev/null 2>&1; then break; fi
  sleep 2
done
ACTIVE_RULES="$(curl -sf http://localhost:8010/health | python3 -c 'import sys,json; print(json.load(sys.stdin).get("active_rules",0))' 2>/dev/null || echo 0)"
echo "rules-engine active_rules=$ACTIVE_RULES (sync poll ~30s after rule create)"

LOGIN=$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")
echo "org=$ORG"

# Résoudre caméra virtual / Benedicte (+ site_id requis pour créer une zone)
CAM_INFO=$(curl -sf "$API/api/v1/orgs/$ORG/cameras" -H "Authorization: Bearer $TOKEN" | python3 -c "
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
CAMERA_ID=$(echo "$CAM_INFO" | awk '{print $1}')
SITE_ID=$(echo "$CAM_INFO" | awk '{print $2}')
if [ -z "$CAMERA_ID" ] || [ -z "$SITE_ID" ]; then
  echo "FAIL: caméra ou site_id introuvable"
  exit 1
fi
echo "camera=$CAMERA_ID site=$SITE_ID"

# Zone de test (coordonnées normalisées 0–1, grande zone centrale)
POLYGON='[{"x":0.05,"y":0.05},{"x":0.95,"y":0.05},{"x":0.95,"y":0.95},{"x":0.05,"y":0.95}]'

# Réutiliser zone existante ou en créer une
ZONE_ID=$(curl -sf "$API/api/v1/orgs/$ORG/zones?camera_id=$CAMERA_ID" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json, os
zones = json.load(sys.stdin)
name = os.environ.get('ZONE_NAME', 'e2e-presence-test')
for z in zones:
    if z.get('name') == name:
        print(z['id']); break
")

if [ -z "${ZONE_ID:-}" ]; then
  ZONE_RESP=$(curl -sf -X POST "$API/api/v1/orgs/$ORG/zones" \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d "{\"name\":\"$ZONE_NAME\",\"site_id\":\"$SITE_ID\",\"camera_id\":\"$CAMERA_ID\",\"polygon\":$POLYGON,\"color\":\"#3b82f6\"}")
  ZONE_ID=$(echo "$ZONE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
  echo "created zone=$ZONE_ID name=$ZONE_NAME"
else
  echo "reusing zone=$ZONE_ID name=$ZONE_NAME"
fi

# Définition règle tpl-zone-presence
RULE_DEF=$(python3 -c "
import json
definition = {
    'condition': {
        'op': 'AND',
        'children': [
            {'op': 'eq', 'field': 'event_type', 'value': 'zone_presence'},
            {'op': 'eq', 'field': 'zone_id', 'value': '$ZONE_NAME'},
            {'op': 'matches_class', 'field': 'class_name', 'value': 'person'},
        ],
    },
    'actions': [{'type': 'alert', 'config': {'severity': 'low'}}],
    'camera_id': '$CAMERA_ID',
    'bindings': {
        'template_id': 'tpl-zone-presence',
        'camera_id': '$CAMERA_ID',
        'zone_name': '$ZONE_NAME',
        'duration_seconds': $DURATION,
        'class_filter': 'person',
    },
}
print(json.dumps(definition))
")

RULE_RESP=$(curl -sf -X POST "$API/api/v1/orgs/$ORG/rules" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"name\":\"E2E $ZONE_NAME\",\"description\":\"auto e2e\",\"priority\":10,\"definition\":$RULE_DEF}")
RULE_ID=$(echo "$RULE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "created rule=$RULE_ID — attente resync orchestrator + rules-engine (~35s)…"
sleep 35

FOUND=0
for i in $(seq 1 "$POLL_SECS"); do
  EVENTS=$(curl -sf "$API/api/v1/orgs/$ORG/events?limit=30&rule_linked=true" -H "Authorization: Bearer $TOKEN" || echo '[]')
  MATCH=$(echo "$EVENTS" | RULE_ID="$RULE_ID" python3 -c "
import sys, json, os
rule_id = os.environ.get('RULE_ID', '')
items = json.load(sys.stdin)
for e in items:
    payload = e.get('payload') or e
    et = e.get('event_type') or payload.get('event_type')
    cn = payload.get('class_name')
    zid = payload.get('zone_id')
    mr = e.get('matched_rule_id') or payload.get('matched_rule_id')
    if et == 'zone_presence' and cn == 'person' and mr:
        print(json.dumps({'event_type': et, 'class_name': cn, 'zone_id': zid, 'matched_rule_id': mr}))
        break
" 2>/dev/null || true)
  if [ -n "$MATCH" ]; then
    echo "PASS après ${i}s: $MATCH"
    FOUND=1
    break
  fi
  sleep 1
done

if [ "$FOUND" -eq 0 ]; then
  echo "FAIL: aucun événement zone_presence + person + matched_rule_id en ${POLL_SECS}s"
  echo "=== Diagnostic (derniers événements bruts) ==="
  curl -sf "$API/api/v1/orgs/$ORG/events?limit=10" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
for e in json.load(sys.stdin):
    p = e.get('payload') or e
    print('-', p.get('event_type'), 'class=', p.get('class_name'), 'zone=', p.get('zone_id'), 'rule=', e.get('matched_rule_id') or p.get('matched_rule_id'))
" || true
  echo "Vérifiez : AI engine actif, zone couvre les personnes, DISABLE_AI_INGEST≠1"
  if [ "$CLEANUP" = "1" ]; then
    curl -sf -X DELETE "$API/api/v1/orgs/$ORG/rules/$RULE_ID" -H "Authorization: Bearer $TOKEN" >/dev/null || true
    curl -sf -X DELETE "$API/api/v1/orgs/$ORG/zones/$ZONE_ID" -H "Authorization: Bearer $TOKEN" >/dev/null || true
  fi
  exit 1
fi

# Evidence package: clip URL + scene + subject images (event puis alerte)
EVIDENCE_OK=0
for j in $(seq 1 60); do
  EVENT_EVIDENCE=$(curl -sf "$API/api/v1/orgs/$ORG/events?limit=20&rule_linked=true" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json, os
rule_id = os.environ.get('RULE_ID', '')
items = json.load(sys.stdin)
for e in items:
    mr = e.get('matched_rule_id') or (e.get('payload') or {}).get('matched_rule_id')
    if mr != rule_id:
        continue
    snap = e.get('evidence_snapshot') or {}
    pkg = snap.get('package') or {}
    clip = (pkg.get('clip') or {}).get('url') or ''
    images = pkg.get('images') or []
    roles = {i.get('role') for i in images if i.get('url')}
    if clip and 'scene' in roles and 'subject' in roles:
        print(json.dumps({'clip': clip, 'images': len(images), 'roles': sorted(roles)}))
        break
" RULE_ID="$RULE_ID" 2>/dev/null || true)
  if [ -n "$EVENT_EVIDENCE" ]; then
    echo "PASS evidence event après ${j}s: $EVENT_EVIDENCE"
    EVIDENCE_OK=1
    break
  fi
  sleep 2
done

if [ "$EVIDENCE_OK" -eq 0 ]; then
  echo "WARN: evidence_snapshot incomplet sur événement (clip + 2 images) — MinIO/API upload ?"
  curl -sf "$API/api/v1/orgs/$ORG/events?limit=5" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
for e in json.load(sys.stdin):
    snap = e.get('evidence_snapshot') or {}
    pkg = snap.get('package') or {}
    print('- evidence keys:', list(snap.keys()), 'package:', bool(pkg), 'clip:', bool((pkg.get('clip') or {}).get('url')))
" || true
fi

ALERT_EVIDENCE_OK=0
for k in $(seq 1 45); do
  ALERT_EVIDENCE=$(curl -sf "$API/api/v1/orgs/$ORG/alerts?limit=20" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json, os
rule_id = os.environ.get('RULE_ID', '')
items = json.load(sys.stdin)
for a in items:
    if a.get('rule_id') != rule_id:
        continue
    snap = a.get('evidence_snapshot') or {}
    pkg = snap.get('package') or {}
    clip = (pkg.get('clip') or {}).get('url') or ''
    images = pkg.get('images') or []
    roles = {i.get('role') for i in images if i.get('url')}
    if clip and 'scene' in roles and 'subject' in roles:
        print(json.dumps({'alert_id': a.get('id'), 'clip': clip[:80], 'roles': sorted(roles)}))
        break
" RULE_ID="$RULE_ID" 2>/dev/null || true)
  if [ -n "$ALERT_EVIDENCE" ]; then
    echo "PASS evidence alerte après ${k}s: $ALERT_EVIDENCE"
    ALERT_EVIDENCE_OK=1
    break
  fi
  sleep 2
done

if [ "$ALERT_EVIDENCE_OK" -eq 0 ]; then
  echo "WARN: evidence_snapshot incomplet sur alerte — vérifiez rules-engine buildEvidenceSnapshot"
fi

if [ "$EVIDENCE_OK" -eq 0 ] || [ "$ALERT_EVIDENCE_OK" -eq 0 ]; then
  echo "FAIL: preuves médias incomplètes (event=$EVIDENCE_OK alert=$ALERT_EVIDENCE_OK)"
  echo "Vérifiez MinIO (docker compose), MINIO_* dans .env, AI engine logs"
  if [ "$CLEANUP" = "1" ]; then
    curl -sf -X DELETE "$API/api/v1/orgs/$ORG/rules/$RULE_ID" -H "Authorization: Bearer $TOKEN" >/dev/null || true
    curl -sf -X DELETE "$API/api/v1/orgs/$ORG/zones/$ZONE_ID" -H "Authorization: Bearer $TOKEN" >/dev/null || true
  fi
  exit 1
fi

if [ "$CLEANUP" = "1" ]; then
  curl -sf -X DELETE "$API/api/v1/orgs/$ORG/rules/$RULE_ID" -H "Authorization: Bearer $TOKEN" >/dev/null || true
  curl -sf -X DELETE "$API/api/v1/orgs/$ORG/zones/$ZONE_ID" -H "Authorization: Bearer $TOKEN" >/dev/null || true
  echo "cleanup: rule et zone supprimées"
fi

echo "=== E2E OK ==="
