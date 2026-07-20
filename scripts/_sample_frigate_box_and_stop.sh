#!/usr/bin/env bash
set -uo pipefail
curl -sS "http://127.0.0.1:5000/api/events?cameras=cv_8ed20433-57d5-4999-a6ab-0bea028b23a3&limit=3" -o /tmp/frigate_evs.json
python3 - <<'PY'
import json
from pathlib import Path
raw=Path("/tmp/frigate_evs.json").read_text()
print("bytes", len(raw))
evs=json.loads(raw) if raw else []
for e in evs[:3]:
    data=e.get("data") or {}
    print("id", str(e.get("id"))[:28], "label", e.get("label"))
    print("  box", data.get("box"))
    print("  region", data.get("region"))
PY

pkill -f '_validate_all_5.sh' 2>/dev/null || true
pkill -f 'validate_rule_dod.py' 2>/dev/null || true
pkill -f '_validate_rule_frigate_1hit.py' 2>/dev/null || true
sleep 1
echo remaining=$(pgrep -af 'validate_all|1hit|validate_rule_dod' | grep -v pgrep | wc -l)
