#!/usr/bin/env bash
set -uo pipefail
echo "=== login http code ==="
curl -s -o /tmp/login_resp.json -w '%{http_code}\n' -X POST http://localhost:8081/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"glory.henock@hologram.cd","password":"Hologram2026!"}'
echo "=== login body ==="
cat /tmp/login_resp.json; echo
echo "=== users ==="
docker exec -i citevision-v2-postgres psql -U citevision -d citevision -tAc "SELECT email, is_active FROM users ORDER BY created_at LIMIT 8;"
