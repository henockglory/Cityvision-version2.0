#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
for a in counting/20260719T093457Z red_light/20260719T093706Z; do
  echo "=== $a ==="
  python3 - <<PY
import json,os
p="$ROOT/validation-evidence/$a/report.json"
d=json.load(open(p))
print("result", d.get("result"))
for c in d.get("dod_checks") or []:
    print(" ", c.get("id"), c.get("ok"), c.get("detail","")[:120])
print("ui", os.path.exists("$ROOT/validation-evidence/$a/ui.png"))
PY
done
# also check 1hit logs in report.md
tail -40 "$ROOT/logs/validate-after-speedonly-fix.log" 2>/dev/null || true
grep -E 'RESULT:|HIT|observation|FINAL|EC_|PASS|FAIL|line_cross|counter' "$ROOT/logs/validate-after-speedonly-fix.log" 2>/dev/null | tail -40
