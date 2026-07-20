#!/usr/bin/env bash
set -uo pipefail
pkill -f '_validate_all_5.sh' 2>/dev/null || true
pkill -f 'validate_rule_dod.py' 2>/dev/null || true
pkill -f '_validate_rule_frigate_1hit.py' 2>/dev/null || true
pkill -f '_sample_frigate_box' 2>/dev/null || true

timeout 10 curl -sf "http://127.0.0.1:5000/api/events?limit=3" -o /tmp/frigate_evs.json || echo CURL_FAIL
python3 <<'PY'
from pathlib import Path
import json
p=Path("/tmp/frigate_evs.json")
if not p.exists() or p.stat().st_size < 2:
    print("no events file")
else:
    evs=json.loads(p.read_text())
    print("n", len(evs))
    for e in evs[:3]:
        data=e.get("data") or {}
        print("box", data.get("box"), "label", e.get("label"), "cam", e.get("camera"))
PY
echo remaining=$(pgrep -af 'validate_all|1hit|validate_rule_dod' | grep -v pgrep | wc -l)
