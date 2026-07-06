#!/bin/bash
resp=$(curl -s -w '\nHTTP:%{http_code}' -X POST http://localhost:8081/api/v1/setup/complete \
  -H 'Content-Type: application/json' \
  -d '{"org_name":"Hologram","org_slug":"hologram","admin_email":"glory.henock@hologram.cd","admin_password":"Hologram2026!","admin_full_name":"Glory Henock"}')
echo "$resp"
body="${resp%HTTP:*}"
code="${resp##*HTTP:}"
if [[ "$code" == "200" || "$code" == "201" ]]; then
  echo "$body" | python3 -m json.tool
else
  echo "Setup failed HTTP $code"
  exit 1
fi
