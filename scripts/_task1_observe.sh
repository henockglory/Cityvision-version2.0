#!/usr/bin/env bash
# Parallel observation during Task1 validate — no _fix_/zone writes
set -uo pipefail
cd ~/citevision-v2
echo "=== rules-engine active ==="
curl -sf http://127.0.0.1:8010/health; echo
echo "=== backend active rules internal ==="
# shellcheck disable=SC1091
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$PWD")"
KEY="${INTERNAL_API_KEY:-changeme_internal_service_key}"
curl -sf -H "X-Internal-Key: $KEY" http://127.0.0.1:8081/api/v1/internal/rules/active | head -c 400; echo
echo "=== recent rules-engine log ==="
grep -aE 'incomplete|suppressed|alert|Publish|error|speed|Excès' logs/rules-engine.log | tail -40
echo "=== recent MQTT / backend alert path ==="
grep -aE 'incomplete|CreateAlert|alert suppressed|DispatchAuto|smtp|mail' logs/backend.log | tail -30
echo "=== alerts now ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT count(*) FROM alerts; SELECT id::text, title, created_at FROM alerts ORDER BY created_at DESC LIMIT 5;"
echo "=== mailhog ==="
curl -sf "http://127.0.0.1:8025/api/v2/messages?limit=3" | python3 -c 'import sys,json;d=json.load(sys.stdin);print("total",d.get("total"))'
echo "=== DB rules enabled ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT name, is_enabled FROM rules WHERE is_enabled;"
echo "=== recent speeding events ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT event_type, occurred_at, left(payload::text,120) FROM events WHERE event_type='speeding' ORDER BY occurred_at DESC LIMIT 5;"
