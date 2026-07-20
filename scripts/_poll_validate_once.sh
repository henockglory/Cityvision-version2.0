#!/usr/bin/env bash
set -uo pipefail
f=/home/gheno/citevision-v2/validation-evidence/speeding/20260718T164956Z/report.json
python3 - <<PY
import json
from pathlib import Path
p=Path("$f")
d=json.loads(p.read_text())
print("result", d.get("result"))
print("alias", d.get("alias"))
for c in d.get("checks") or []:
    print(("OK" if c.get("ok") else "FAIL"), c.get("id"), c.get("detail","")[:120])
PY

echo "=== wait 90s ==="
sleep 90
echo "=== log ==="
tail -30 /home/gheno/citevision-v2/logs/validate-all-5.log
echo "=== procs ==="
pgrep -af '1hit|validate_rule_dod|validate_all' | grep -v pgrep | head -8
echo "=== artefacts ==="
find /home/gheno/citevision-v2/validation-evidence -name report.json | sort | while read -r r; do
  python3 -c "import json;d=json.load(open('$r'));print('$r', d.get('result'))"
done
