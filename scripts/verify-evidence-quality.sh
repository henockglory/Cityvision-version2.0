#!/usr/bin/env bash
# Vérifie la qualité des preuves sur une alerte fixture : pas metadata_only, bbox valide, durée clip > 0.5s
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$SCRIPT_DIR/lib/env-utils.sh"

API="${API:-http://localhost:8081}"
EMAIL="${EMAIL:-glory.henock@hologram.cd}"
PASS="${PASS:-Hologram2026!}"

echo "=== verify-evidence-quality ==="

LOGIN=$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")

ALERT=$(curl -sf "$API/api/v1/orgs/$ORG/alerts?limit=30" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
items = json.load(sys.stdin)
for a in items:
    snap = a.get('evidence_snapshot') or {}
    pkg = snap.get('package') or {}
    if pkg.get('clip') or pkg.get('images'):
        print(json.dumps(a))
        break
else:
    sys.exit(1)
")

if [ -z "$ALERT" ]; then
  echo "FAIL: aucune alerte avec package preuve"
  exit 1
fi

echo "$ALERT" | python3 -c "
import sys, json
a = json.load(sys.stdin)
snap = a.get('evidence_snapshot') or {}
pkg = snap.get('package') or {}
meta = snap.get('metadata') or pkg.get('metadata') or {}
status = meta.get('evidence_status') or a.get('evidence_status')
if status == 'metadata_only':
    print('FAIL: evidence_status metadata_only')
    sys.exit(1)
bbox = snap.get('bbox') or {}
if bbox:
    w = float(bbox.get('width') or 0)
    h = float(bbox.get('height') or 0)
    if w * h <= 0:
        print('FAIL: bbox area zero')
        sys.exit(1)
dur = (pkg.get('clip') or {}).get('duration_sec') or meta.get('clip_duration_sec')
if dur is not None and float(dur) < 0.5:
    print(f'FAIL: clip duration {dur}s < 0.5')
    sys.exit(1)
print('PASS evidence quality metadata')
"

# Fetch scene JPEG magic
SCENE_URL=$(echo "$ALERT" | python3 -c "
import sys, json
a = json.load(sys.stdin)
pkg = (a.get('evidence_snapshot') or {}).get('package') or {}
for img in pkg.get('images') or []:
    if img.get('role') == 'scene' and img.get('url'):
        print(img['url']); break
")

if [ -n "$SCENE_URL" ]; then
  FULL="${API}${SCENE_URL}" 
  [[ "$SCENE_URL" == http* ]] && FULL="$SCENE_URL"
  [[ "$SCENE_URL" == /api/* ]] && FULL="${API}${SCENE_URL}"
  TMP=$(mktemp)
  HTTP=$(curl -sf -o "$TMP" -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$FULL" || echo 000)
  MAGIC=$(head -c 2 "$TMP" | xxd -p 2>/dev/null || true)
  rm -f "$TMP"
  if [ "$HTTP" != "200" ]; then
    echo "FAIL scene HTTP $HTTP"
    exit 1
  fi
  if [ "$MAGIC" != "ffd8" ]; then
    echo "FAIL scene not JPEG (magic=$MAGIC)"
    exit 1
  fi
  echo "PASS scene JPEG ffd8"
fi

echo "=== verify-evidence-quality OK ==="
