#!/usr/bin/env bash
docker exec citevision-v2-postgres psql -U postgres -d citevision -t -c \
  "SELECT event_type, demo, COUNT(*), MAX(created_at) FROM events \
   WHERE camera_id='f691ef55-6791-495b-a35e-be215e7ac109' \
   AND created_at > NOW() - INTERVAL '60 minutes' \
   GROUP BY event_type, demo ORDER BY COUNT(*) DESC;"
