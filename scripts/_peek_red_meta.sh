#!/usr/bin/env bash
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT left(payload::text,500) FROM events WHERE event_type='red_light_violation' ORDER BY ingested_at DESC LIMIT 1;"
echo '---'
docker exec citevision-v2-postgres psql -U citevision -d citevision -t -A -c \
  "SELECT payload->'metadata'->'light_zone_polygon' IS NOT NULL AS has_poly,
          payload->'light_zone_polygon' IS NOT NULL AS has_poly2,
          left(coalesce(payload->'metadata'::text, payload::text), 400)
   FROM events WHERE event_type='red_light_violation' ORDER BY ingested_at DESC LIMIT 1;" 2>&1 | head -20
