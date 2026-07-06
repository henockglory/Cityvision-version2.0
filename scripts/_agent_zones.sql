\pset border 2
\echo '=== SPEED zone behavior_config (Zone_distance_parcourue) ==='
SELECT z.name, c.name AS cam, z.behavior_config
FROM zones z JOIN cameras c ON c.id=z.camera_id
WHERE z.name ILIKE '%distance%' OR z.behavior_config::text ILIKE '%speed_measurement%';

\echo '=== FEUX camera zones + behaviors ==='
SELECT z.name, z.zone_kind, z.behavior_config->>'behavior' AS behavior
FROM zones z
WHERE z.camera_id='8ed20433-57d5-4999-a6ab-0bea028b23a3';

\echo '=== org_demo_settings (active demo camera) ==='
SELECT org_id, active_camera_id FROM org_demo_settings;

\echo '=== fresh speeding detection_method ==='
SELECT payload->'metadata'->>'detection_method' AS method,
       payload->'metadata'->>'distance_m' AS dist,
       payload->'metadata'->>'speed_kmh' AS kmh
FROM events WHERE event_type='speeding' AND occurred_at > now() - interval '30 minutes'
ORDER BY occurred_at DESC LIMIT 5;
