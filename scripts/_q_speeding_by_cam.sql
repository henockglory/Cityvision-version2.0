SELECT camera_id::text, COUNT(*), MAX(occurred_at)::text
FROM events
WHERE event_type = 'speeding'
GROUP BY 1
ORDER BY 3 DESC;
