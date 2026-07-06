\pset border 2
\echo '=== fresh feu events (5 min) ==='
SELECT event_type, count(*), max(occurred_at)
FROM events
WHERE camera_id='8ed20433-57d5-4999-a6ab-0bea028b23a3'
  AND occurred_at > now() - interval '5 minutes'
GROUP BY 1 ORDER BY 2 DESC;

\echo '=== any traffic_light_state ever ==='
SELECT count(*) AS total_tls, max(occurred_at) AS latest,
       (SELECT payload->'metadata'->>'state' FROM events WHERE event_type='traffic_light_state' ORDER BY occurred_at DESC LIMIT 1) AS last_state
FROM events WHERE event_type='traffic_light_state';
