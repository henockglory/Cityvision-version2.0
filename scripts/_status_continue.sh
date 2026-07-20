#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
echo "=== patch present? ==="
grep -n 'if cfg.get("lines")' "$ROOT/ai-engine/src/citevision_ai/pipeline.py" || echo MISSING_SPEEDONLY_FIX
grep -n '_OBSERVATION_RULE\|frigate LIVE\|observation rule' "$ROOT/scripts/_validate_rule_frigate_1hit.py" | head -20 || echo MISSING_1HIT
echo "=== latest artefacts ==="
ls -1dt "$ROOT/validation-evidence/counting"/*/ 2>/dev/null | head -3
ls -1dt "$ROOT/validation-evidence/red_light"/*/ 2>/dev/null | head -3
echo "=== AI spatial count cam ==="
curl -sf http://127.0.0.1:8001/cameras/9a3cd323-3820-46f0-aa5b-86c086a4a782/spatial; echo
echo "=== AI cams ==="
python3 - <<'PY'
import json,urllib.request
d=json.loads(urllib.request.urlopen("http://127.0.0.1:8001/cameras", timeout=5).read())
for c in d.get("cameras") or []:
    print(c.get("camera_id","")[:8], "fp", c.get("frames_processed"), "run", c.get("running"))
PY
echo "=== health ==="
for u in 8001/health 8081/health 5174/ 5000/api/version 8181/healthz; do
  code=$(curl -sf -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:$u" || echo 000)
  echo "$u=$code"
done
