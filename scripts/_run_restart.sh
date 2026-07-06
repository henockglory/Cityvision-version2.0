#!/bin/bash
set -euo pipefail
cd ~/citevision-v2
LOG="logs/restart-full.log"
echo "=== $(date) restart started ===" >> "$LOG"
bash scripts/restart-api-frontend.sh >> "$LOG" 2>&1
echo "=== $(date) restart finished exit=$? ===" >> "$LOG"
