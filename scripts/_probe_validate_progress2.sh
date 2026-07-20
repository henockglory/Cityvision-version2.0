#!/usr/bin/env bash
set -uo pipefail

echo "=== Frigate latest events ==="
curl -sS "http://127.0.0.1:5000/api/events?limit=8" | python3 - <<'PY'
import json,sys,time
raw=sys.stdin.read()
evs=json.loads(raw)
now=time.time()
for e in evs[:8]:
    st=float(e.get("start_time") or 0)
    cam=str(e.get("camera") or "")[:32]
    lab=e.get("label")
    eid=str(e.get("id") or "")[:22]
    print(f"age={now-st:.0f}s cam={cam} label={lab} id={eid}")
PY

echo "=== artefacts ==="
find /home/gheno/citevision-v2/validation-evidence -name report.json 2>/dev/null | sort | while read -r f; do
  python3 - <<PY
import json
d=json.load(open("$f"))
print("$f", "result="+str(d.get("result")), "alias="+str(d.get("alias","")))
PY
done

echo "=== validate log tail ==="
tail -50 /home/gheno/citevision-v2/logs/validate-all-5.log

echo "=== procs ==="
pgrep -af 'validate_rule|1hit|validate_all' | grep -v pgrep | head -8
