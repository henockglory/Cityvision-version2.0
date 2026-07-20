\pset border 2
\x on
\echo '=== ALL zones on speed cam 55694d53 ==='
SELECT z.id, z.name, z.zone_kind, z.behavior_config
FROM zones z WHERE z.camera_id='55694d53-8f58-4981-91b2-7c6cd528a25d';

\echo '=== camera metadata (calibration?) for 55694d53 ==='
SELECT metadata FROM cameras WHERE id='55694d53-8f58-4981-91b2-7c6cd528a25d';

\echo '=== fresh speeding detection_method + dist ==='
SELECT occurred_at,
       payload->'metadata'->>'detection_method' AS method,
       payload->'metadata'->>'distance_m' AS dist,
       payload->>'zone_id' AS zone
FROM events WHERE event_type='speeding' AND occurred_at > now() - interval '10 minutes'
ORDER BY occurred_at DESC LIMIT 6;
