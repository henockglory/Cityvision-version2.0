#!/usr/bin/env bash
set -euo pipefail
API="${API:-http://127.0.0.1:8081}"
EMAIL="${1:-heegyboanerges@gmail.com}"
PASS="${2:-Hologram2026!}"

login=$(curl -sf -X POST "$API/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}") || {
  echo "LOGIN_FAILED"
  curl -s -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}"
  exit 1
}

token=$(echo "$login" | jq -r '.access_token')
echo "TOKEN_OK"

me=$(curl -sf "$API/api/v1/auth/me" -H "Authorization: Bearer $token")
org_id=$(echo "$me" | jq -r '.org_id // empty')
echo "ME: $me"
echo "ORG: $org_id"

if [[ -z "$org_id" || "$org_id" == "null" ]]; then
  echo "NO_ORG_ID"
  exit 1
fi

echo "--- dashboard/summary ---"
curl -s -w "\nHTTP:%{http_code}\n" \
  "$API/api/v1/orgs/$org_id/dashboard/summary" \
  -H "Authorization: Bearer $token" \
  -H "X-Org-ID: $org_id"

echo "--- alerts ---"
curl -s -w "\nHTTP:%{http_code}\n" \
  "$API/api/v1/orgs/$org_id/alerts" \
  -H "Authorization: Bearer $token"

echo "--- health/ready via 5174 proxy ---"
curl -s -w "\nHTTP:%{http_code}\n" http://127.0.0.1:5174/health/ready
