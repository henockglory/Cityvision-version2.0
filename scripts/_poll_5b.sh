#!/usr/bin/env bash
set -uo pipefail
echo "=== log tail ==="
tail -35 /home/gheno/citevision-v2/logs/validate-all-5b.log
echo "=== recent reports ==="
find /home/gheno/citevision-v2/validation-evidence -name report.json -mmin -45 | sort | while read -r f; do
  python3 -c "import json;d=json.load(open('$f'));print('$f', d.get('result'))"
done
echo "=== procs ==="
pgrep -af 'validate_all_5b|1hit|validate_rule_dod' | grep -v pgrep | head -6
