#!/usr/bin/env bash
set -euo pipefail
ROOT=~/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cp "$WIN/frontend/src/components/demo/DemoVideoPanel.tsx" "$ROOT/frontend/src/components/demo/DemoVideoPanel.tsx"
cp "$WIN/scripts/_sync_vite_frigate_env.py" "$ROOT/scripts/"
python3 "$ROOT/scripts/_sync_vite_frigate_env.py"
source "$ROOT/scripts/lib/env-utils.sh"
stop_from_pid "$ROOT/logs/frontend.pid" 2>/dev/null || true
pkill -f 'vite --host' 2>/dev/null || true
free_port 5174 2>/dev/null || true
sleep 2
start_bg frontend "$ROOT/frontend" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$ROOT/logs" "$ROOT/.env"
sleep 10
curl -sf http://127.0.0.1:5174/ >/dev/null && echo FRONTEND_OK
cat "$ROOT/frontend/.env"
