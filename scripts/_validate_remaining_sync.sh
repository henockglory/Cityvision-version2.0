#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"

cp -f "$WIN/scripts/validate_rule_dod.py" "$ROOT/scripts/"
cp -f "$WIN/scripts/_validate_rule_frigate_1hit.py" "$ROOT/scripts/"
cp -f "$WIN/scripts/capture_alerts_ui.mjs" "$ROOT/scripts/"
sed -i 's/\r$//' "$ROOT/scripts/"validate_rule_dod.py \
  "$ROOT/scripts/_validate_rule_frigate_1hit.py" \
  "$ROOT/scripts/capture_alerts_ui.mjs"
grep -n 'Non-port\|Comptage véhicules' "$ROOT/scripts/validate_rule_dod.py"

# Frigate up
if ! timeout 4 curl -sf http://127.0.0.1:5000/api/version >/dev/null; then
  docker restart citevision-v2-frigate
  for i in $(seq 1 30); do
    timeout 3 curl -sf http://127.0.0.1:5000/api/version >/dev/null && break
    sleep 2
  done
fi

bash scripts/health_check_all.sh || exit 1

export RULE_DURATION_SEC=420
export VALIDATE_MODE=wait
export SKIP_FRIGATE_REBUILD=1

for alias in seatbelt speeding red_light counting; do
  echo "########## VALIDATE $alias $(date -Is) ##########"
  bash scripts/validate_rule.sh "$alias"
  echo "EC_$alias=$?"
done

echo "=== FINAL ==="
find validation-evidence -name report.json | sort | while read -r f; do
  python3 -c "import json;d=json.load(open('$f'));print(d.get('result'), d.get('alias'), '$f')"
done
