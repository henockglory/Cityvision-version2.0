#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2

echo "=== reports ==="
find "$ROOT/validation-evidence" -name report.json | sort | while read -r f; do
  python3 - <<PY
import json
d=json.load(open("$f"))
print("--- $f")
print("  result=", d.get("result"), "alias=", d.get("alias"))
for c in d.get("checks") or []:
    mark="OK" if c.get("ok") else "FAIL"
    print(f"  {mark} {c.get('id')}: {str(c.get('detail',''))[:140]}")
PY
done

echo "=== latest alerts (30m) ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -F'|' -c "
SELECT a.created_at::text, left(a.id::text,8), coalesce(r.name,''),
  coalesce(a.evidence_snapshot->'package'->'metadata'->>'capture_source',''),
  coalesce(a.evidence_snapshot->'package'->>'evidence_status',''),
  coalesce(a.evidence_snapshot->'package'->'metadata'->>'missing_roles','')
FROM alerts a LEFT JOIN rules r ON r.id=a.rule_id
WHERE a.org_id='74d51ead-97a7-4e41-a488-503a9b90c466'::uuid
  AND a.created_at > now() - interval '90 minutes'
ORDER BY a.created_at DESC LIMIT 12;"

echo "=== rules-engine suppress tail ==="
grep -E 'suppressed|incomplete|capture|frigate|502|ensureEvidence' "$ROOT/logs/rules-engine.log" | tail -25

echo "=== validate log tail ==="
tail -20 "$ROOT/logs/validate-all-5.log"
