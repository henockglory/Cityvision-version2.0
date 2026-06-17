#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"
load_dotenv "$ROOT/.env" 2>/dev/null || true
DEMO_VIDEO_PATH="${DEMO_VIDEO_PATH:-$ROOT/data/videos/benedicte_stream.mp4}"
API_URL="${API_URL:-http://localhost:8081}"
RTSP_URL="${RTSP_URL:-rtsp://localhost:8554/benedicte}"
EXTERNAL_ID="${VIRTUAL_CAMERA_ID:-demo-benedicte}"

echo "==> Register virtual camera (idempotent: $EXTERNAL_ID)"

TOKEN=$(curl -sf "$API_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"'"${ADMIN_EMAIL:-glory.henock@hologram.cd}"'","password":"'"${ADMIN_PASSWORD:-Hologram2026!}"'"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)

if [ -z "$TOKEN" ]; then
  echo "Login failed — run setup first or set ADMIN_EMAIL/ADMIN_PASSWORD"
  exit 1
fi

ORG_ID=$(curl -sf "$API_URL/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")

CAM_JSON=$(curl -sf "$API_URL/api/v1/orgs/$ORG_ID/cameras" -H "Authorization: Bearer $TOKEN")

EXISTING=$(echo "$CAM_JSON" | python3 -c "
import sys, json
ext = '$EXTERNAL_ID'
cams = json.load(sys.stdin)
if not isinstance(cams, list):
    sys.exit(0)
for c in cams:
    meta = c.get('metadata') or {}
    if meta.get('external_id') == ext:
        print(c['id'])
        break
" 2>/dev/null || true)

if [ -n "$EXISTING" ]; then
  echo "[OK] Virtual camera already registered: $EXISTING"
  exit 0
fi

# Dedupe legacy duplicates before creating canonical camera
if docker exec citevision-v2-postgres psql -U citevision -d citevision -tAc "SELECT 1" >/dev/null 2>&1; then
  docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
    DELETE FROM cameras
    WHERE org_id = '$ORG_ID'::uuid
      AND (name ILIKE '%virtual%' OR name ILIKE '%benedicte%');
  " >/dev/null 2>&1 || true
fi

SITE_ID=$(echo "$CAM_JSON" | python3 -c "
import sys, json
cams = json.load(sys.stdin)
if isinstance(cams, list):
    for c in cams:
        if c.get('site_id'):
            print(c['site_id'])
            break
" 2>/dev/null || true)

if [ -z "$SITE_ID" ]; then
  SITE_ID=$(docker exec citevision-v2-postgres psql -U citevision -d citevision -tAc \
    "SELECT id FROM sites ORDER BY created_at LIMIT 1" 2>/dev/null | tr -d '[:space:]' || true)
fi

if [ -z "$SITE_ID" ]; then
  echo "No site_id found — complete setup wizard first"
  exit 1
fi

CAMERA_JSON=$(cat <<EOF
{
  "org_id": "$ORG_ID",
  "site_id": "$SITE_ID",
  "name": "Virtual — Benedicte",
  "vendor": "generic",
  "host": "127.0.0.1",
  "port": 8554,
  "rtsp_path": "/benedicte",
  "metadata": {
    "external_id": "$EXTERNAL_ID",
    "rtsp_url": "$RTSP_URL",
    "go2rtc_src": "benedicte",
    "virtual": true,
    "source": "benedicte.mp4",
    "video_file": "$DEMO_VIDEO_PATH",
    "ai_ingest": "file"
  }
}
EOF
)

RESP=$(curl -sf -X POST "$API_URL/api/v1/orgs/$ORG_ID/cameras" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$CAMERA_JSON")

echo "$RESP" | python3 -m json.tool
echo "==> Virtual camera registered. Orchestrator will start RTSP worker within 10s."
