#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"

# Ensure vite
if ! curl -sf --max-time 2 http://127.0.0.1:5174/ >/dev/null; then
  (cd "$ROOT/frontend" && nohup npm run dev -- --host 127.0.0.1 --port 5174 > /tmp/citevision-vite.log 2>&1 &)
  sleep 4
fi

# Wait frigate
for i in $(seq 1 20); do
  timeout 4 curl -sf http://127.0.0.1:5000/api/version >/dev/null && break
  sleep 2
done

bash "$ROOT/scripts/health_check_all.sh" || exit 1

export RULE_DURATION_SEC=480
export VALIDATE_MODE=wait
export SKIP_FRIGATE_REBUILD=1

echo "########## RED_LIGHT $(date -Is) ##########"
bash "$ROOT/scripts/validate_rule.sh" red_light
echo EC_red=$?
latest=$(find "$ROOT/validation-evidence/red_light" -name report.json | sort | tail -1)
python3 -c "import json,os;d=json.load(open('$latest'));print('red_light',d.get('result'),'ui',os.path.exists('$(dirname "$latest")/ui.png'))"

echo "########## COUNTING $(date -Is) ##########"
bash "$ROOT/scripts/validate_rule.sh" counting
echo EC_count=$?
latest=$(find "$ROOT/validation-evidence/counting" -name report.json 2>/dev/null | sort | tail -1)
if [[ -n "${latest:-}" ]]; then
  python3 -c "import json,os;d=json.load(open('$latest'));print('counting',d.get('result'),'ui',os.path.exists('$(dirname "$latest")/ui.png'))"
else
  echo counting NONE
fi

echo "=== SCORECARD ==="
for a in speeding red_light phone seatbelt counting; do
  latest=$(find "$ROOT/validation-evidence/$a" -name report.json 2>/dev/null | sort | tail -1)
  if [[ -n "${latest:-}" ]]; then
    python3 -c "import json,os;d=json.load(open('$latest'));print(d.get('result'), '$a', 'ui='+str(os.path.exists('$(dirname "$latest")/ui.png')))"
  else
    echo "NONE $a"
  fi
done
