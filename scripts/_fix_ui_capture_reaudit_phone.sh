#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cp -f "$WIN/scripts/capture_alerts_ui.mjs" "$ROOT/scripts/"
cp -f "$WIN/scripts/validate_rule_dod.py" "$ROOT/scripts/"
sed -i 's/\r$//' "$ROOT/scripts/capture_alerts_ui.mjs" "$ROOT/scripts/validate_rule_dod.py"

cd "$ROOT/frontend"
# Ensure chromium browser for @playwright/test
npx playwright install chromium 2>&1 | tail -15

# Smoke UI capture
export UI_URL=http://127.0.0.1:5174
export OUT_PNG=/tmp/cv_ui_smoke.png
export EMAIL=glory.henock@hologram.cd
export PASS='Hologram2026!'
node "$ROOT/scripts/capture_alerts_ui.mjs" && ls -la /tmp/cv_ui_smoke.png

# Re-audit phone (1hit already PASS — SKIP_1HIT)
cd "$ROOT"
export VALIDATE_MODE=audit
export SKIP_1HIT=1
bash scripts/validate_rule.sh phone
echo EXIT=$?
find validation-evidence/phone -name report.json | sort | tail -2 | while read -r f; do
  python3 -c "import json;d=json.load(open('$f'));print('$f', d.get('result'), 'ui', next((c for c in d.get('checks',[]) if c['id']=='7_ui_screenshot'),{}).get('ok'))"
  d=$(dirname "$f")
  ls -la "$d/ui.png" 2>/dev/null || echo "no ui.png in $d"
done
