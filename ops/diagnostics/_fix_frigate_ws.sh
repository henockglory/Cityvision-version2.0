#!/usr/bin/env bash
set -euo pipefail
WIN=/mnt/c/Users/gheno/citevision
ROOT=~/citevision-v2
cp "$WIN/frontend/vite.config.ts" "$ROOT/frontend/vite.config.ts"
cp "$WIN/frontend/src/components/live/FrigateLivePlayer.tsx" "$ROOT/frontend/src/components/live/FrigateLivePlayer.tsx"
source "$ROOT/scripts/lib/env-utils.sh"
stop_from_pid "$ROOT/logs/frontend.pid" 2>/dev/null || true
pkill -f 'vite --host' 2>/dev/null || true
free_port 5174 2>/dev/null || true
sleep 2
start_bg frontend "$ROOT/frontend" "npm run dev -- --host 0.0.0.0 --port 5174 --strictPort" "$ROOT/logs" "$ROOT/.env"
sleep 10
curl -sf http://127.0.0.1:5174/ >/dev/null && echo FRONTEND_OK
curl -sI "http://127.0.0.1:5174/frigate/live?camera=cv_d2eb7076-c3b3-40fd-9b2c-0d119bb975c9" | head -8
