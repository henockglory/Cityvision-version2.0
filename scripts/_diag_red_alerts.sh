#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/gheno/citevision-v2
cd "$ROOT"
source scripts/lib/env-utils.sh
load_dotenv "$(ensure_env_file "$ROOT")"
ORG=74d51ead-97a7-4e41-a488-503a9b90c466

echo "=== red_light events/alerts last 30m ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT 'event' AS kind, event_type AS t, count(*), max(ingested_at) AS last
FROM events WHERE org_id='$ORG'::uuid AND event_type IN ('red_light_violation','traffic_light_state')
  AND ingested_at > now() - interval '40 minutes'
GROUP BY 1,2
UNION ALL
SELECT 'alert', coalesce(r.name,'?'), count(*), max(a.created_at)
FROM alerts a LEFT JOIN rules r ON r.id=a.rule_id
WHERE a.org_id='$ORG'::uuid AND a.created_at > now() - interval '40 minutes'
GROUP BY 1,2
ORDER BY 4 DESC NULLS LAST;
"

echo "=== sample red_light event payload ==="
docker exec citevision-v2-postgres psql -U citevision -d citevision -c "
SELECT left(payload::text,200), left(evidence_snapshot::text,200), ingested_at
FROM events WHERE event_type='red_light_violation'
ORDER BY ingested_at DESC LIMIT 3;
"

echo "=== AI spatial red cam ==="
curl -sf http://127.0.0.1:8001/cameras/8ed20433-57d5-4999-a6ab-0bea028b23a3/spatial; echo

echo "=== rules-engine health ==="
curl -sf http://127.0.0.1:8010/health || echo rules_down
pgrep -af rules-engine | head -3
