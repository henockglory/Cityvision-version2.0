#!/bin/bash
set -euo pipefail
cd ~/citevision-v2
export PATH="$PATH:/usr/local/go/bin"
source scripts/lib/env-utils.sh
load_dotenv .env
start_bg backend "$PWD/backend" "$PWD/backend/bin/citevision-api" "$PWD/logs" "$PWD/.env"
sleep 3
curl -sf http://localhost:8081/health && echo " backend OK"
