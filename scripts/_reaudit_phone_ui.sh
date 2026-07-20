#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cp -f /mnt/c/Users/gheno/citevision/scripts/capture_alerts_ui.mjs "$ROOT/scripts/"
sed -i 's/\r$//' "$ROOT/scripts/capture_alerts_ui.mjs"

cd "$ROOT/frontend"
export UI_URL=http://127.0.0.1:5174
export OUT_PNG=/tmp/cv_ui_smoke.png
export EMAIL=glory.henock@hologram.cd
export PASS='Hologram2026!'
node "$ROOT/scripts/capture_alerts_ui.mjs"
echo smoke_ec=$?
ls -la /tmp/cv_ui_smoke.png 2>/dev/null

cd "$ROOT"
export VALIDATE_MODE=audit SKIP_1HIT=1
bash scripts/validate_rule.sh phone
echo EXIT=$?
latest=$(find validation-evidence/phone -name report.json | sort | tail -1)
python3 -c "import json;d=json.load(open('$latest'));print('result',d.get('result'));
print('ui', [c for c in d.get('checks',[]) if 'ui' in c.get('id','')])"
ls -la "$(dirname "$latest")/ui.png" 2>/dev/null || echo no_ui_png
