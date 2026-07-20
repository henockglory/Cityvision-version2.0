SELECT event_type, camera_id::text, COUNT(*), MAX(occurred_at)::text
FROM events
WHERE occurred_at > NOW() - INTERVAL '15 minutes'
GROUP BY 1, 2
ORDER BY 4 DESC
LIMIT 20;
