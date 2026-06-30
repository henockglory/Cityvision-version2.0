#!/usr/bin/env bash
set -euo pipefail
WIN="/mnt/c/Users/gheno/citevision"
WSL="$HOME/citevision-v2"
cp "$WIN/scripts/monitor_feux_until_success.py" "$WSL/scripts/"
cp "$WIN/scripts/validate-demo-feux-monitor.sh" "$WSL/scripts/"
python3 "$WSL/scripts/fix-crlf.py" "$WSL/scripts/validate-demo-feux-monitor.sh"
cd "$WSL"
bash scripts/validate-demo-feux-monitor.sh 2>&1 | tee logs/feux-monitor-run.log
