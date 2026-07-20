#!/usr/bin/env bash
# Live validation bootstrap — stack-up + Vite :5174
set -euo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
export PATH="/usr/local/go/bin:$HOME/go/bin:$PATH"

echo "=== live bootstrap $(date -Is) ==="
bash "$ROOT/scripts/stack-up.sh" || {
  echo "stack-up exited non-zero — continue if partial"
}

# Frontend Vite on :5174 (required for validate_rule ui.png)
if curl -sf --max-time 2 http://127.0.0.1:5174/ >/dev/null 2>&1; then
  echo "[OK] frontend already on :5174"
else
  echo "starting frontend Vite :5174..."
  cd "$ROOT/frontend"
  if [[ ! -d node_modules ]]; then
    npm install --prefer-offline || npm install
  fi
  nohup npm run dev -- --host 127.0.0.1 --port 5174 > /tmp/citevision-vite.log 2>&1 &
  echo $! > /tmp/citevision-vite.pid
  for i in $(seq 1 30); do
    if curl -sf --max-time 2 http://127.0.0.1:5174/ >/dev/null 2>&1; then
      echo "[OK] frontend up :5174"
      break
    fi
    sleep 1
  done
fi

bash "$ROOT/scripts/health_check_all.sh" || true
echo "=== bootstrap done $(date -Is) ==="
