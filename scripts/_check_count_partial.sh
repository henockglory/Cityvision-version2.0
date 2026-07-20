#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
echo "=== procs ==="
pgrep -af 'validate_rule|1hit|fix_speedonly' | grep -v pgrep | head -10
echo "=== red artefact ==="
ls -la "$ROOT/validation-evidence/red_light/20260719T093706Z/" 2>/dev/null | head -20
echo "=== log tail ==="
tail -50 "$ROOT/logs/validate-after-speedonly-fix.log" 2>/dev/null
echo "=== counting rule actions ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT definition->'actions', definition->'evidence', definition->'bindings'->>'observation_mode'
   FROM rules WHERE name='Démo · Comptage véhicules';"
echo "=== recent counting alerts ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT a.id, a.created_at, left(coalesce(a.evidence_snapshot::text,''),120)
   FROM alerts a JOIN rules r ON r.id=a.rule_id
   WHERE r.name='Démo · Comptage véhicules'
   ORDER BY a.created_at DESC LIMIT 3;"
