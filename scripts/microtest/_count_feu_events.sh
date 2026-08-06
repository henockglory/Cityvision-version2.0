#!/usr/bin/env bash
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT count(*) FROM events WHERE event_type='red_light_violation' AND ingested_at > now() - interval '2 hours';"
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT count(*) FROM alerts a JOIN rules r ON r.id=a.rule_id WHERE r.name LIKE '%Feu%';"
