#!/usr/bin/env bash
# Task 1 — ensure Vite + ALERT_EMAIL then run validate_rule speeding
set -uo pipefail
cd ~/citevision-v2
# shellcheck disable=SC1091
source scripts/lib/env-utils.sh
ENV_FILE="$(ensure_env_file "$PWD")"
load_dotenv "$ENV_FILE"

echo "=== ALERT_EMAIL_TO ==="
grep -E '^(ALERT_EMAIL_TO|ADMIN_EMAIL)=' .env || echo "MISSING in .env"

# Ensure recipient for Mailhog (config, not a _fix script)
if ! grep -qE '^ALERT_EMAIL_TO=' .env 2>/dev/null; then
  echo "ALERT_EMAIL_TO=demo@citevision.local" >> .env
  echo "appended ALERT_EMAIL_TO"
fi
load_dotenv "$ENV_FILE"

echo "=== start Vite if down ==="
if ! curl -sf -o /dev/null http://127.0.0.1:5174/; then
  if [[ -x scripts/_start_vite.sh ]]; then
    bash scripts/_start_vite.sh || true
  elif [[ -f frontend/package.json ]]; then
    (
      cd frontend
      nohup npm run dev -- --host 127.0.0.1 --port 5174 >> ../logs/vite.log 2>&1 &
      echo $! > ../logs/vite.pid
    )
  fi
  for i in $(seq 1 40); do
    if curl -sf -o /dev/null http://127.0.0.1:5174/; then
      echo "Vite UP"
      break
    fi
    sleep 1
  done
fi
curl -sf -o /dev/null -w "vite=%{http_code}\n" http://127.0.0.1:5174/ || echo vite_still_down

echo "=== restart rules-engine to pick ALERT_EMAIL / sync rules ==="
if [[ -f scripts/_restart_rules_engine.sh ]]; then
  bash scripts/_restart_rules_engine.sh 2>&1 | tail -20
elif [[ -f scripts/_start-rules-engine.sh ]]; then
  bash scripts/_start-rules-engine.sh 2>&1 | tail -20
else
  echo "no rules restart script — validate_rule will sync"
fi

echo "=== rules before validate ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT id::text, name, is_enabled, left(definition::text,80) FROM rules ORDER BY name LIMIT 20;"

echo "=== T0 markers ==="
T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "T0=$T0"
echo "$T0" > /tmp/task1_t0.txt
docker exec citevision-v2-postgres psql -U citevision -d citevision -tAc "SELECT count(*) FROM alerts;" > /tmp/task1_alerts_before.txt
curl -sf "http://127.0.0.1:8025/api/v2/messages" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("total",0))' > /tmp/task1_mail_before.txt
echo "alerts_before=$(cat /tmp/task1_alerts_before.txt) mail_before=$(cat /tmp/task1_mail_before.txt)"

echo "=== validate_rule.sh speeding ==="
# Long window — 1hit can take many minutes
export SKIP_FRIGATE_REBUILD="${SKIP_FRIGATE_REBUILD:-0}"
bash scripts/validate_rule.sh speeding 2>&1 | tee /tmp/task1_validate_speeding.log
echo "validate_exit=$?"
