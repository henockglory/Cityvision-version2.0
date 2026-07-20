#!/usr/bin/env bash
set -uo pipefail
echo "=== remaining2 tail ==="
tail -40 /home/gheno/citevision-v2/logs/validate-remaining2.out 2>/dev/null || tail -40 /home/gheno/citevision-v2/logs/validate-remaining.out
echo "=== latest PASS/PARTIAL ==="
find /home/gheno/citevision-v2/validation-evidence -name report.json -mmin -120 | sort | while read -r f; do
  python3 -c "import json;d=json.load(open('$f'));print(d.get('result'), d.get('alias'), '$f')"
done
echo "=== procs ==="
pgrep -af 'validate_remaining|validate_rule_dod|1hit' | grep -v pgrep | head -8
