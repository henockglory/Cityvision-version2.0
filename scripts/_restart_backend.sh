#!/bin/bash
set -euo pipefail
cd ~/citevision-v2
export PATH="$PATH:/usr/local/go/bin"
# shellcheck source=scripts/lib/env-utils.sh
source scripts/lib/env-utils.sh
load_dotenv .env
# Always stop stale API first — a replaced binary can keep serving as "(deleted)"
# and ignore new routes (e.g. surveillance-lists/.../entries/enroll → 404).
stop_from_pid "$PWD/logs/backend.pid"
pkill -f 'backend/bin/citevision-api' 2>/dev/null || true
free_port 8081
sleep 1
start_bg backend "$PWD/backend" "$PWD/backend/bin/citevision-api" "$PWD/logs" "$PWD/.env"
sleep 3
curl -sf http://localhost:8081/health && echo " backend OK"
