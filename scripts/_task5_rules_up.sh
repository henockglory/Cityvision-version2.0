#!/usr/bin/env bash
cd /home/gheno/citevision-v2
if ! curl -sf http://127.0.0.1:8010/health >/dev/null 2>&1; then
  echo "rules-engine down — restart"
  if [ -x scripts/_restart_rules_engine.sh ]; then
    bash scripts/_restart_rules_engine.sh
  elif [ -f scripts/_restart_rules.py ]; then
    python3 scripts/_restart_rules.py
  else
    # best-effort from bin
    set -a; source .env; set +a
    setsid nohup ./rules-engine/bin/rules-engine >> logs/rules-engine.log 2>&1 &
    echo $! > logs/rules-engine.pid
  fi
  sleep 3
fi
curl -sf http://127.0.0.1:8010/health || curl -sf http://127.0.0.1:8010/ || echo still_down
pgrep -af rules-engine | head -3
