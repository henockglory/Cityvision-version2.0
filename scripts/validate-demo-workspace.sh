#!/usr/bin/env bash
# Validate demo workspace: settings API, optional upload, go2rtc stream, demo tagging, retention cap.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="${API_BASE:-http://localhost:8081/api/v1}"
EMAIL="${DEMO_EMAIL:-glory.henock@hologram.cd}"
PASS="${DEMO_PASS:-Hologram2026!}"
GO2RTC="${GO2RTC_API:-http://localhost:1984/api/streams}"
MAX_DEMO_EVENTS="${MAX_DEMO_EVENTS:-20}"

echo "==> Login"
TOKEN=$(curl -sf -X POST "$API/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" | jq -r '.access_token')
ORG=$(curl -sf "$API/auth/me" -H "Authorization: Bearer $TOKEN" | jq -r '.org_id // .organization_id // empty')
if [[ -z "$ORG" || "$ORG" == "null" ]]; then
  echo "FAIL: could not resolve org_id"
  exit 1
fi
echo "Org: $ORG"

echo "==> GET demo/settings"
SETTINGS=$(curl -sf "$API/orgs/$ORG/demo/settings" \
  -H "Authorization: Bearer $TOKEN" -H "X-Org-ID: $ORG")
echo "$SETTINGS" | jq '{title, nav_label, source_mode, videos: (.videos | length), stream: .active_go2rtc_src}'

NAV=$(echo "$SETTINGS" | jq -r '.nav_label // empty')
[[ -n "$NAV" ]] && echo "OK: nav_label present" || echo "WARN: nav_label missing"

STREAM=$(echo "$SETTINGS" | jq -r '.active_go2rtc_src // empty')
if [[ -n "$STREAM" ]]; then
  echo "==> go2rtc stream: $STREAM"
  curl -sf "$GO2RTC" | jq -e ".[\"$STREAM\"]" >/dev/null && echo "OK: stream registered" || echo "WARN: stream not in go2rtc yet"
else
  echo "INFO: no active stream (empty state — upload required)"
fi

UPLOAD_START=
if [[ -n "${DEMO_VIDEO_PATH:-}" && -f "${DEMO_VIDEO_PATH}" ]]; then
  echo "==> Upload demo video: $DEMO_VIDEO_PATH"
  UPLOAD_START=$(date +%s)
  UP=$(curl -sf -X POST "$API/orgs/$ORG/demo/videos" \
    -H "Authorization: Bearer $TOKEN" -H "X-Org-ID: $ORG" \
    -F "video=@${DEMO_VIDEO_PATH}")
  VID=$(echo "$UP" | jq -r '.id')
  echo "Video id: $VID"
  for i in $(seq 1 60); do
    ST=$(curl -sf "$API/orgs/$ORG/demo/videos/$VID/status" \
      -H "Authorization: Bearer $TOKEN" -H "X-Org-ID: $ORG")
    STATUS=$(echo "$ST" | jq -r '.status')
    PROGRESS=$(echo "$ST" | jq -r '.progress')
    echo "  poll $i: $STATUS ($PROGRESS%)"
    [[ "$STATUS" == "ready" ]] && break
    [[ "$STATUS" == "failed" ]] && echo "FAIL: transcode failed" && exit 1
    sleep 5
  done
  NEW_STREAM=$(curl -sf "$API/orgs/$ORG/demo/settings" \
    -H "Authorization: Bearer $TOKEN" -H "X-Org-ID: $ORG" | jq -r '.active_go2rtc_src')
  echo "Active stream after upload: $NEW_STREAM"
  if [[ -n "$UPLOAD_START" ]]; then
    ELAPSED=$(( $(date +%s) - UPLOAD_START ))
    echo "Switch time: ${ELAPSED}s (target < 180s for upload+transcode)"
  fi
fi

echo "==> PATCH demo title + nav_label"
curl -sf -X PATCH "$API/orgs/$ORG/demo/settings" \
  -H "Authorization: Bearer $TOKEN" -H "X-Org-ID: $ORG" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Validation démo workspace","nav_label":"Démo Kinshasa"}' | jq -r '.title, .nav_label'

echo "==> Demo events (demo tag, total cap $MAX_DEMO_EVENTS)"
EVENTS=$(curl -sf "$API/orgs/$ORG/events?include_incomplete=true" \
  -H "Authorization: Bearer $TOKEN" -H "X-Org-ID: $ORG" || echo '[]')
DEMO_COUNT=$(echo "$EVENTS" | jq '(
  if type == "array" then .
  elif (has("items") and (.items | type == "array")) then .items
  elif (has("data") and (.data | type == "array")) then .data
  else []
  end
) | map(select(.payload.demo == true or .payload.demo == "true")) | length')
echo "Demo-tagged events: $DEMO_COUNT"
if [[ "$DEMO_COUNT" -gt "$MAX_DEMO_EVENTS" ]]; then
  echo "FAIL: demo events exceed cap ($DEMO_COUNT > $MAX_DEMO_EVENTS)"
  exit 1
fi
echo "OK: retention cap respected"

if [[ "${DEMO_DO_RESET:-0}" == "1" ]]; then
  echo "==> POST demo/reset (DEMO_DO_RESET=1)"
  curl -sf -X POST "$API/orgs/$ORG/demo/reset" \
    -H "Authorization: Bearer $TOKEN" -H "X-Org-ID: $ORG" | jq .
else
  echo "INFO: skip reset (set DEMO_DO_RESET=1 to enable)"
fi

echo "PASS: validate-demo-workspace"
