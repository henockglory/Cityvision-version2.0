\pset border 2
SELECT now() AS db_now;
\echo '=== red_light_violation recent ==='
SELECT occurred_at, camera_id FROM events
WHERE event_type='red_light_violation'
ORDER BY occurred_at DESC LIMIT 8;
\echo '=== speeding recent (any time) ==='
SELECT occurred_at, payload->'metadata'->>'speed_kmh' AS kmh,
       payload->'metadata'->>'distance_m' AS dist
FROM events WHERE event_type='speeding'
ORDER BY occurred_at DESC LIMIT 8;
\echo '=== total counts all-time (demo types) ==='
SELECT event_type, count(*) FROM events
WHERE event_type IN ('red_light_violation','speeding','seatbelt_violation','phone_use_violation','line_cross')
GROUP BY 1 ORDER BY 2 DESC;
