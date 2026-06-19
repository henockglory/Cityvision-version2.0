#!/usr/bin/env bash
# Purge alerts, events, and MinIO evidence for the logged-in org (DB + object storage).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/env-utils.sh
source "$SCRIPT_DIR/lib/env-utils.sh"

API="${API:-http://localhost:8081}"
EMAIL="${EMAIL:-glory.henock@hologram.cd}"
PASS="${PASS:-Hologram2026!}"

echo "=== purge alerts + events + MinIO evidence ==="

curl -sf "$API/health" >/dev/null || {
  echo "FAIL: backend not reachable at $API"
  exit 1
}

LOGIN=$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
ORG=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('org_id',''))")

if [ -z "$TOKEN" ] || [ -z "$ORG" ]; then
  echo "FAIL: login"
  exit 1
fi

echo "org_id=$ORG"

RESULT=$(curl -sf -X POST "$API/api/v1/orgs/$ORG/maintenance/purge" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")
echo "$RESULT" | python3 -m json.tool

count_list() {
  python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)"
}

ALERTS=$(curl -sf "$API/api/v1/orgs/$ORG/alerts?limit=5" -H "Authorization: Bearer $TOKEN" | count_list)
EVENTS=$(curl -sf "$API/api/v1/orgs/$ORG/events?limit=5" -H "Authorization: Bearer $TOKEN" | count_list)
echo "alerts_remaining=$ALERTS events_remaining=$EVENTS"

# Belt-and-suspenders: wipe entire evidence bucket if MinIO is reachable
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q citevision-v2-minio; then
  echo "=== MinIO bucket wipe (citevision-evidence) ==="
  docker run --rm --entrypoint /bin/sh --network infra_default \
    -e MINIO_ROOT_USER="${MINIO_ROOT_USER:-citevision}" \
    -e MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-changeme_minio}" \
    minio/mc:latest -c '
      mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
      mc rm --recursive --force local/citevision-evidence/ 2>/dev/null || true
      mc mb --ignore-existing local/citevision-evidence
      echo "MinIO citevision-evidence bucket cleared"
    ' || echo "WARN: MinIO direct wipe skipped (check docker network)"
fi

echo "=== purge OK ==="
