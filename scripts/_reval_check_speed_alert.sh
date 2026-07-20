#!/usr/bin/env bash
set -uo pipefail
ART=/home/gheno/citevision-v2/validation-evidence/speeding/20260719T180742Z
python3 - <<PY
import json
from pathlib import Path
d=json.loads(Path("$ART/report.json").read_text())
print("result", d.get("result"), "alert", d.get("alert_id"))
for c in d.get("dod_checks") or []:
    print(c.get("id"), c.get("ok"), c.get("detail"))
PY
ls -la "$ART"
echo "=== mailhog ==="
curl -sf http://127.0.0.1:8025/api/v2/messages | python3 -c 'import sys,json;d=json.load(sys.stdin);print("total",d.get("total"));
items=d.get("items") or []
for m in items[:5]:
  print("-", m.get("Content",{}).get("Headers",{}).get("Subject"), m.get("Created"))'
echo "=== alert row ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT id, title, created_at, left(evidence_snapshot::text,120) FROM alerts WHERE id='e852cabf-5a65-440d-8fbe-35457c6d7482';"
