#!/usr/bin/env bash
set -uo pipefail
tail -50 /home/gheno/citevision-v2/logs/validate-speeding-now.log
echo "=== procs ==="
pgrep -af 'validate_speeding|validate_rule|1hit' | grep -v pgrep | head -6
