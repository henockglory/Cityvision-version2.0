#!/usr/bin/env bash
set -uo pipefail
cd ~/citevision-v2

echo "=== 108 in frigate config ==="
grep -n '192.168.1.108' infra/frigate-config/config.yml && echo PRESENT || echo ABSENT

echo
echo "=== per-camera record/snapshots from live config ==="
python3 - <<'PY'
from pathlib import Path
import yaml
data = yaml.safe_load(Path("infra/frigate-config/config.yml").read_text())
print("GLOBAL record:", data.get("record"))
print("GLOBAL snapshots:", data.get("snapshots"))
cams = data.get("cameras") or {}
for name, cfg in sorted(cams.items()):
    rec = (cfg or {}).get("record") or {}
    snap = (cfg or {}).get("snapshots") or {}
    print(f"{name}: record={rec} snapshots={snap}")
PY

echo
echo "=== abort-stats live ==="
curl -sf http://127.0.0.1:8001/evidence/abort-stats | python3 -m json.tool 2>/dev/null || echo "abort-stats unavailable"

echo
echo "=== AI health demo ==="
curl -sf http://127.0.0.1:8001/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print({k:d.get(k) for k in ("demo_mode","demo_mode_source","demo_relaxed_evidence","status")})' 2>/dev/null || echo down
