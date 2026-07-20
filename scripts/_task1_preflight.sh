#!/usr/bin/env bash
# Task 1 preflight — stack readiness before validate_rule.sh speeding
set -uo pipefail
cd ~/citevision-v2
# shellcheck disable=SC1091
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$PWD")"
load_dotenv "$ENV_FILE"

echo "=== ports ==="
for p in 8081 8001 8010 5000 8025 5174 1884; do
  if curl -sf --max-time 2 "http://127.0.0.1:$p/" >/dev/null 2>&1 \
     || curl -sf --max-time 2 "http://127.0.0.1:$p/health" >/dev/null 2>&1 \
     || curl -sf --max-time 2 "http://127.0.0.1:$p/api/v2/messages" >/dev/null 2>&1; then
    echo "UP $p"
  else
    # try TCP only
    if ss -lptn "sport = :$p" 2>/dev/null | grep -q LISTEN; then
      echo "LISTEN $p"
    else
      echo "DOWN $p"
    fi
  fi
done

echo "=== health ==="
curl -sf http://127.0.0.1:8081/health | head -c 200; echo
curl -sf http://127.0.0.1:8001/health | python3 -c 'import sys,json;d=json.load(sys.stdin);print({k:d.get(k) for k in ("status","demo_mode","demo_mode_source","models_all_ok")})' 2>/dev/null || echo AI_DOWN
curl -sf http://127.0.0.1:8010/health 2>/dev/null | head -c 200 || echo "rules-engine no /health"
echo
echo "=== mailhog ==="
curl -sf "http://127.0.0.1:8025/api/v2/messages?limit=5" | python3 -c 'import sys,json;d=json.load(sys.stdin);print("total",d.get("total"),"items",len(d.get("items") or []))' 2>/dev/null || echo MAILHOG_DOWN

echo "=== alerts count now ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "SELECT count(*) AS alerts FROM alerts;"
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "SELECT count(*) AS rules_enabled FROM rules WHERE is_enabled;"

echo "=== SMTP / DEMO env (masked) ==="
env | grep -E '^(DEMO_MODE|SMTP_|MAILHOG_|ALERT_EMAIL|RULES_DEDUP)' | sed 's/\(PASSWORD\|SECRET\|KEY\)=.*/\1=***/' || true
grep -E '^(DEMO_MODE|SMTP_|MAILHOG_|ALERT_EMAIL|RULES_DEDUP)=' .env 2>/dev/null | sed 's/\(PASSWORD\|SECRET\|KEY\)=.*/\1=***/' || true

echo "=== vite ==="
curl -sf -o /dev/null -w "vite_http=%{http_code}\n" http://127.0.0.1:5174/ || echo vite_down
