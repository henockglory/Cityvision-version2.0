#!/usr/bin/env bash
set -uo pipefail
echo "=== continue-phone.log ==="
tail -50 /home/gheno/citevision-v2/logs/continue-phone.log
echo "=== reports ==="
find /home/gheno/citevision-v2/validation-evidence/phone -name report.json | sort | while read -r f; do
  python3 -c "import json;d=json.load(open('$f'));print(d.get('result'), '$f')"
done
echo "=== procs ==="
pgrep -af 'continue_phone|validate_rule|1hit' | grep -v pgrep | head -6
