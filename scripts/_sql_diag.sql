SELECT payload->>'event_type' AS et, count(*) 
FROM events 
WHERE payload->>'event_type' IN ('traffic_light_state','red_light_violation','speeding')
GROUP BY 1;

SELECT payload->>'event_type' AS et, payload->>'camera_id' AS cam, count(*)
FROM events 
WHERE payload->>'event_type' = 'vehicle_corridor' AND payload->>'speed_kmh' IS NOT NULL
GROUP BY 1,2
ORDER BY 3 DESC
LIMIT 5;
