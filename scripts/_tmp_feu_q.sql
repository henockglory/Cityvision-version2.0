SELECT name, zone_kind, is_active,
       jsonb_array_length(polygon) AS pts,
       left(behavior_config::text, 160) AS cfg
FROM zones
WHERE camera_id = '8ed20433-57d5-4999-a6ab-0bea028b23a3'
ORDER BY zone_kind, name;

SELECT name, is_enabled, event_type, camera_ids::text
FROM rules
WHERE org_id = '74d51ead-97a7-4e41-a488-503a9b90c466'
  AND (name ILIKE '%feu%' OR event_type ILIKE '%red_light%' OR definition::text ILIKE '%red_light%')
ORDER BY name;

SELECT event_type, created_at
FROM events
WHERE camera_id = '8ed20433-57d5-4999-a6ab-0bea028b23a3'
  AND created_at > now() - interval '3 hours'
ORDER BY created_at DESC
LIMIT 20;
