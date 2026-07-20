#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
echo "=== artefacts (latest per alias) ==="
for alias in speeding red_light phone seatbelt counting; do
  latest=$(find "$ROOT/validation-evidence/$alias" -name report.json 2>/dev/null | sort | tail -1)
  if [[ -n "$latest" ]]; then
    python3 -c "import json;d=json.load(open('$latest'));print('$alias', d.get('result'), '$latest')"
    ls -la "$(dirname "$latest")/ui.png" 2>/dev/null | awk '{print "  ui.png", $5, "bytes"}' || echo "  no ui.png"
  else
    echo "$alias NO_ARTEFACT"
  fi
done
echo "=== health ==="
curl -sf -o /dev/null -w "ai=%{http_code} " http://127.0.0.1:8001/health || echo -n "ai=down "
curl -sf -o /dev/null -w "api=%{http_code} " http://127.0.0.1:8081/health || echo -n "api=down "
curl -sf -o /dev/null -w "ui=%{http_code} " http://127.0.0.1:5174/ || echo -n "ui=down "
curl -sf -o /dev/null -w "frigate=%{http_code}\n" http://127.0.0.1:5000/api/version || echo "frigate=down"
echo "=== procs ==="
pgrep -af 'validate_rule|1hit|uvicorn|citevision-api|vite' | grep -v pgrep | head -15
echo "=== remaining log tail ==="
tail -40 "$ROOT/logs/validate-remaining-sync.log" 2>/dev/null || echo no_sync_log
