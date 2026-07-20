#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
echo "=== artefacts ==="
for a in speeding red_light phone seatbelt counting; do
  latest=$(find "$ROOT/validation-evidence/$a" -name report.json 2>/dev/null | sort | tail -1)
  if [[ -n "$latest" ]]; then
    python3 -c "import json;d=json.load(open('$latest'));print('$a', d.get('result'), 'ui', __import__('os').path.exists('$(dirname "$latest")/ui.png'))"
  else
    echo "$a NONE"
  fi
done
echo "=== health ==="
for u in "ai=http://127.0.0.1:8001/health" "api=http://127.0.0.1:8081/health" "ui=http://127.0.0.1:5174/" "frigate=http://127.0.0.1:5000/api/version" "ocr=http://127.0.0.1:8181/healthz"; do
  name=${u%%=*}; url=${u#*=}
  code=$(curl -sf -o /dev/null -w '%{http_code}' --max-time 3 "$url" 2>/dev/null || echo 000)
  echo "$name=$code"
done
echo "=== procs ==="
pgrep -af 'uvicorn|citevision-api|rules-engine|vite|validate_rule|1hit|ocr' | grep -v pgrep | head -15
echo "=== OCR_URL ==="
grep OCR_URL "$ROOT/.env" 2>/dev/null || echo missing
echo "=== log tails ==="
tail -30 "$ROOT/logs/full-speeding-ocr.log" 2>/dev/null || echo no_full_log
tail -20 "$ROOT/logs/ocr-validate-speeding.log" 2>/dev/null || true
