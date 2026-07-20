#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
echo "=== last 30 log lines ==="
tail -30 "$ROOT/logs/ai-engine.log"
echo "=== speeding mqtt/publish recent ==="
grep -E 'speeding|attach_evidence|evidence' "$ROOT/logs/ai-engine.log" | tail -20
echo "=== events last 5 min ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c "
SELECT count(*), max(ingested_at)
FROM events e JOIN cameras c ON c.id=e.camera_id
WHERE c.org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid
  AND e.event_type='speeding'
  AND e.ingested_at > now() - interval '5 minutes';
"
echo "=== rules active ==="
curl -sf http://127.0.0.1:8010/health
echo
echo "=== frigate record ==="
python3 - <<'PY'
from pathlib import Path
import re
text=Path("/home/gheno/citevision-v2/infra/frigate-config/config.yml").read_text()
cam="cv_55694d53-8f58-4981-91b2-7c6cd528a25d"
m=re.search(rf"{re.escape(cam)}:.*?record:\s*\n\s*enabled:\s*(true|false)", text, re.S)
print("record", m.group(1) if m else "?")
PY
curl -sf http://127.0.0.1:5000/api/version && echo
