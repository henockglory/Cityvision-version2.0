#!/usr/bin/env bash
set -uo pipefail
cd ~/citevision-v2
# shellcheck disable=SC1091
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$PWD")"

if ! curl -sf -o /dev/null http://127.0.0.1:5174/; then
  (cd frontend && nohup npm run dev -- --host 127.0.0.1 --port 5174 >> ../logs/vite.log 2>&1 & echo $! > ../logs/vite.pid)
  for i in $(seq 1 40); do
    curl -sf -o /dev/null http://127.0.0.1:5174/ && break
    sleep 1
  done
fi

echo "=== validate_rule red_light ==="
bash scripts/validate_rule.sh red_light 2>&1 | tee /tmp/task5_validate_red.log
echo "exit=$?"

echo "=== AI log demo_ring ==="
grep -aE 'demo_ring_buffer|frigate miss — using' logs/ai-engine.log | tail -30
