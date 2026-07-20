#!/usr/bin/env bash
set -uo pipefail
ART=/home/gheno/citevision-v2/validation-evidence/red_light/20260719T150923Z
echo "=== artefact ==="
ls -la "$ART"
echo "=== report.json ==="
python3 - <<'PY'
import json
from pathlib import Path
p=Path("/home/gheno/citevision-v2/validation-evidence/red_light/20260719T150923Z/report.json")
d=json.loads(p.read_text())
print("result=", d.get("result"))
print("alert_id=", d.get("alert_id"))
print("event_id=", d.get("event_id"))
for c in d.get("dod_checks") or []:
    print(f"  {c.get('id')}: ok={c.get('ok')} detail={c.get('detail')}")
# keys of interest
for k in ("evidence_status","capture_source","plate_status","assets","ui_png"):
    if k in d: print(k, d[k])
print("top_keys", sorted(d.keys())[:40])
PY
echo "=== ui.png ==="
ls -la "$ART"/ui.png 2>/dev/null || ls -la "$ART"/*.png 2>/dev/null || echo no_png
echo "=== health ==="
curl -sf http://127.0.0.1:8081/health; echo
curl -sf http://127.0.0.1:8001/health | python3 -c 'import sys,json;d=json.load(sys.stdin);print("ai",d.get("status"),d.get("demo_mode"),d.get("demo_relaxed_evidence"))'
curl -sf http://127.0.0.1:8010/health; echo
curl -sf http://127.0.0.1:5000/api/version; echo
