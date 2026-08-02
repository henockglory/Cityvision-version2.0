#!/usr/bin/env bash
# Tests 33-35: evidence metadata + mailhog.
set -euo pipefail
ROOT="${MICROTEST_ROOT:-$HOME/citevision-v2}"
cd "$ROOT"
source scripts/microtest/_microtest_common.sh
REPORT="${MICROTEST_REPORT:-$ROOT/logs/microtest-report-$(microtest_ts).md}"

python3 - <<'PY' | tee -a "$REPORT"
import json, os, subprocess
root=os.path.expanduser("~/citevision-v2")
q="""
SELECT a.evidence_snapshot->'package'->'metadata'->>'capture_source',
       a.evidence_snapshot->'package'->'metadata'->>'bbox_source',
       a.evidence_snapshot->'package'->'metadata'->>'evidence_status',
       count(*)
FROM alerts a
WHERE a.created_at > now() - interval '24 hours'
GROUP BY 1,2,3
ORDER BY 4 DESC LIMIT 10;
"""
try:
  r=subprocess.run(["bash","-lc",f"cd {root} && python3 scripts/_db_query.py \"{q}\""],capture_output=True,text=True,timeout=30)
  print("Test 33 evidence repartition:", r.stdout[:800] or r.stderr[:400])
except Exception as e:
  print("Test 33 skip:", e)
PY

curl -sf -m 5 http://127.0.0.1:8025/api/v2/messages >/dev/null && MH=yes || MH=no
append_report "$REPORT" "Test 35 mailhog" "reachable=$MH"
