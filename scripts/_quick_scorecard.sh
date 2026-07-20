#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
echo '=== SCORECARD ==='
for a in speeding red_light phone seatbelt counting; do
  latest=$(find "$ROOT/validation-evidence/$a" -name report.json 2>/dev/null | sort | tail -1)
  if [[ -n "${latest:-}" ]]; then
    python3 -c "import json,os;d=json.load(open('$latest'));print(d.get('result'), '$a', 'ui='+str(os.path.exists(os.path.join(os.path.dirname('$latest'),'ui.png'))))"
  else
    echo "NONE $a"
  fi
done
echo '=== health ==='
curl -sf -o /dev/null -w 'ai=%{http_code}\n' --max-time 3 http://127.0.0.1:8001/health || echo 'ai=000'
curl -sf -o /dev/null -w 'api=%{http_code}\n' --max-time 3 http://127.0.0.1:8081/health || echo 'api=000'
curl -sf -o /dev/null -w 'ui=%{http_code}\n' --max-time 3 http://127.0.0.1:5174/ || echo 'ui=000'
curl -sf -o /dev/null -w 'frigate=%{http_code}\n' --max-time 3 http://127.0.0.1:5000/api/version || echo 'frigate=000'
curl -sf -o /dev/null -w 'ocr=%{http_code}\n' --max-time 3 http://127.0.0.1:8181/healthz || echo 'ocr=000'
echo '=== procs ==='
pgrep -af 'validate_rule|1hit|uvicorn|citevision-api|vite' | grep -v pgrep | head -12
echo '=== validate log tail ==='
tail -40 "$ROOT/logs/validate-red-count-now.log" 2>/dev/null || echo no_log
