#!/usr/bin/env bash
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT active_video_id, active_camera_id, source_mode FROM org_demo_settings;"
docker exec citevision-v2-postgres psql -U citevision -d citevision -c \
  "SELECT v.name AS video, v.id AS video_id, v.go2rtc_src, c.id AS camera_id, c.name AS camera
   FROM org_demo_videos v
   LEFT JOIN cameras c ON c.metadata->>'demo_video_id' = v.id::text
   ORDER BY v.name;"
