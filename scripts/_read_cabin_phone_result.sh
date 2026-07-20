#!/usr/bin/env bash
set -uo pipefail
echo "=== nohup tail ==="
tail -80 /home/gheno/citevision-v2/logs/fix-cabin-phone.nohup
echo "=== phone reports ==="
find /home/gheno/citevision-v2/validation-evidence/phone -name report.json | sort | while read -r f; do
  python3 -c "import json;d=json.load(open('$f'));print('$f', d.get('result'))"
done
echo "=== procs ==="
pgrep -af 'fix-cabin|validate_rule|1hit|_restart_ai' | grep -v pgrep | head -8
