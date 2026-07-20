SELECT event_type, payload->>'demo' as is_demo, COUNT(*), MAX(occurred_at::text)
FROM events
WHERE camera_id='f691ef55-6791-495b-a35e-be215e7ac109'
AND occurred_at > NOW() - INTERVAL '30 minutes'
GROUP BY event_type, payload->>'demo'
ORDER BY COUNT(*) DESC;
