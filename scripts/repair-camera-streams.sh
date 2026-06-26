#!/usr/bin/env bash
# Idempotent repair: re-onboard all non-virtual cameras in go2rtc (fixes bad host/32, missing cam-* streams).
set -euo pipefail

API_URL="${CITEVISION_API_URL:-http://localhost:8081/api/v1}"
EMAIL="${CITEVISION_EMAIL:-}"
PASSWORD="${CITEVISION_PASSWORD:-}"
ORG_ID="${CITEVISION_ORG_ID:-}"

if [[ -z "$EMAIL" || -z "$PASSWORD" ]]; then
  echo "Set CITEVISION_EMAIL and CITEVISION_PASSWORD (and optionally CITEVISION_ORG_ID, CITEVISION_API_URL)" >&2
  exit 1
fi

login_payload=$(printf '{"email":"%s","password":"%s"}' "$EMAIL" "$PASSWORD")
login_resp=$(curl -sS -X POST "$API_URL/auth/login" \
  -H 'Content-Type: application/json' \
  -d "$login_payload") || { echo "Login request failed" >&2; exit 1; }

token=$(echo "$login_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token') or '')" 2>/dev/null || true)

if [[ -z "$token" ]]; then
  echo "Login failed: $login_resp" >&2
  exit 1
fi

if [[ -z "$ORG_ID" ]]; then
  me_resp=$(curl -sS "$API_URL/auth/me" -H "Authorization: Bearer $token") || true
  ORG_ID=$(echo "$me_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('org_id') or d.get('organization_id') or '')" 2>/dev/null || true)
fi

if [[ -z "$ORG_ID" ]]; then
  echo "Could not resolve org id — set CITEVISION_ORG_ID" >&2
  exit 1
fi

cameras_json=$(curl -sS "$API_URL/orgs/$ORG_ID/cameras" -H "Authorization: Bearer $token") || {
  echo "Failed to list cameras" >&2
  exit 1
}

mapfile -t rows < <(echo "$cameras_json" | python3 -c "
import json, sys
cams = json.load(sys.stdin)
if not isinstance(cams, list):
    raise SystemExit('unexpected cameras response')
for cam in cams:
    meta = cam.get('metadata') or {}
    if meta.get('virtual') is True or meta.get('go2rtc_src') == 'benedicte':
        continue
    print(cam['id'] + '\t' + cam.get('name', cam['id']))
")

if [[ ${#rows[@]} -eq 0 ]]; then
  echo "No real cameras to repair."
  exit 0
fi

for row in "${rows[@]}"; do
  cam_id="${row%%$'\t'*}"
  cam_name="${row#*$'\t'}"
  echo "Repairing $cam_name ($cam_id)..."
  if curl -sf "$API_URL/orgs/$ORG_ID/cameras/$cam_id/preview" -H "Authorization: Bearer $token" >/dev/null; then
    echo "  OK"
  else
    echo "  FAILED (check backend logs / ffprobe / go2rtc)" >&2
  fi
done

echo "Done."
