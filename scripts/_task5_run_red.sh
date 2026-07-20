#!/usr/bin/env bash
set -euo pipefail
cd /home/gheno/citevision-v2
export PATH="/usr/local/go/bin:$PATH"
export SKIP_FRIGATE_REBUILD=1
export HOME=/home/gheno

cp /mnt/c/Users/gheno/citevision/scripts/_restart_backend.py scripts/_restart_backend.py
sed -i 's/\r$//' scripts/_restart_backend.py
python3 scripts/_restart_backend.py

if ! curl -sf http://127.0.0.1:5174/ >/dev/null 2>&1; then
  echo "starting vite..."
  (cd frontend && setsid nohup npm run dev -- --host 127.0.0.1 --port 5174 >> ../logs/vite.log 2>&1 & echo $! > ../logs/vite.pid)
  sleep 4
fi

curl -sf http://127.0.0.1:8081/health >/dev/null && echo backend_ok
curl -sf http://127.0.0.1:8001/health >/dev/null && echo ai_ok
curl -sf http://127.0.0.1:5174/ >/dev/null && echo ui_ok || echo ui_warn

setsid bash -c '
  while true; do
    if ! curl -sf http://127.0.0.1:8081/health >/dev/null 2>&1; then
      echo "$(date -Is) watchdog restart backend" >> /home/gheno/citevision-v2/logs/watch-backend.log
      python3 /home/gheno/citevision-v2/scripts/_restart_backend.py >> /home/gheno/citevision-v2/logs/watch-backend.log 2>&1
    fi
    sleep 15
  done
' >/dev/null 2>&1 &
echo "watchdog_pid=$!"

stdbuf -oL -eL bash scripts/validate_rule.sh red_light 2>&1 | tee /tmp/task5_validate_red3.log
echo EXIT:$?
