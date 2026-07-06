\pset border 2
\echo '=== FRESH demo events (last 12 min) by type ==='
SELECT event_type, count(*) AS n, max(occurred_at) AS latest
FROM events
WHERE occurred_at > now() - interval '12 minutes'
GROUP BY event_type ORDER BY n DESC;

\echo '=== FRESH speeding metadata (last 20 min) ==='
SELECT occurred_at,
       payload->'metadata'->>'speed_kmh' AS kmh,
       payload->'metadata'->>'distance_m' AS dist_m,
       payload->'metadata'->>'elapsed_s' AS elapsed_s,
       payload->'metadata'->>'method' AS method
FROM events WHERE event_type='speeding' AND occurred_at > now() - interval '20 minutes'
ORDER BY occurred_at DESC LIMIT 10;

\echo '=== FRESH events on FEUX cam (last 12 min) ==='
SELECT event_type, count(*) FROM events
WHERE camera_id='8ed20433-57d5-4999-a6ab-0bea028b23a3'
  AND occurred_at > now() - interval '12 minutes'
GROUP BY 1 ORDER BY 2 DESC;

\echo '=== FRESH alerts (last 12 min) ==='
SELECT count(*) AS fresh_demo_alerts FROM alerts
WHERE (metadata->>'demo')='true' AND created_at > now() - interval '12 minutes';
