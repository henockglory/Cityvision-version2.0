#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
WIN=/mnt/c/Users/gheno/citevision
cd "$ROOT"
mkdir -p logs
LOG="$ROOT/logs/validate-red-fallback2.log"
exec > >(tee "$LOG") 2>&1
echo "=== START $(date -Is) ==="

pkill -f '_validate_rule_frigate_1hit|validate_rule.sh' 2>/dev/null || true
sleep 2

cp -f "$WIN/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py" \
  "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py"
sed -i 's/\r$//' "$ROOT/ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py"
cp -f "$WIN/scripts/_validate_rule_frigate_1hit.py" "$ROOT/scripts/_validate_rule_frigate_1hit.py"
sed -i 's/\r$//' "$ROOT/scripts/_validate_rule_frigate_1hit.py"

# Ensure DEMO_MODE exported for AI
set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a
export DEMO_MODE=1

bash scripts/_restart_ai.py
curl -sf http://127.0.0.1:8081/health >/dev/null || bash scripts/_restart_backend.sh
curl -sf http://127.0.0.1:8010/health >/dev/null || bash scripts/_start-rules-engine.sh
curl -sf http://127.0.0.1:8181/healthz >/dev/null || true
curl -sf http://127.0.0.1:5174/ >/dev/null || true

# Prove settings
python3 - <<'PY'
import sys
sys.path.insert(0,"/home/gheno/citevision-v2/ai-engine/src")
from citevision_ai.config import Settings
s=Settings()
print("demo_mode", s.demo_mode, "timeline", s.frigate_demo_timeline_align, "ocr", s.ocr_url if hasattr(s,"ocr_url") else getattr(s,"OCR_URL",None))
PY

export RULE_DURATION_SEC=420
export VALIDATE_MODE=wait
unset SKIP_FRIGATE_REBUILD

bash scripts/validate_rule.sh red_light
echo EC_red=$?

echo "=== SCORECARD ==="
for a in speeding red_light phone seatbelt counting; do
  latest=$(find validation-evidence/$a -name report.json 2>/dev/null | sort | tail -1)
  if [[ -n "${latest:-}" ]]; then
    python3 -c "import json,os;d=json.load(open('$latest'));print(d.get('result'), '$a', 'ui='+str(os.path.exists(os.path.join(os.path.dirname('$latest'),'ui.png'))))"
  else
    echo "NONE $a"
  fi
done
echo "=== DONE $(date -Is) ==="
