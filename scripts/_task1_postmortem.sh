#!/usr/bin/env bash
set -uo pipefail
cd ~/citevision-v2
# shellcheck disable=SC1091
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$PWD")"

echo "=== DEMO_RETENTION ==="
grep -E 'DEMO_RETENTION|FRIGATE_DEMO_RETENTION' .env || echo unset
python3 - <<'PY'
import os
print("DEMO_RETENTION_MINUTES", os.environ.get("DEMO_RETENTION_MINUTES","<unset>"))
print("FRIGATE_DEMO_RETENTION_MIN", os.environ.get("FRIGATE_DEMO_RETENTION_MIN","<unset>"))
PY

echo "=== AI log capture/speed since 14:05 ==="
grep -aE 'capture unavailable|speed evidence|frigate_track|retro capture|incomplete|semaphore|speeding' logs/ai-engine.log | tail -60

echo "=== post-run alerts/mail ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "SELECT count(*) FROM alerts;"
curl -sf "http://127.0.0.1:8025/api/v2/messages?limit=5" | python3 -c 'import sys,json;d=json.load(sys.stdin);print("mailhog",d.get("total"))'

echo "=== latest validate artefact ==="
ls -lt validation-evidence/speeding/ | head -5
LATEST=$(ls -td validation-evidence/speeding/*/ 2>/dev/null | head -1)
echo "LATEST=$LATEST"
if [[ -n "$LATEST" ]]; then
  cat "${LATEST}report.json" 2>/dev/null | python3 -m json.tool 2>/dev/null | head -80
fi
