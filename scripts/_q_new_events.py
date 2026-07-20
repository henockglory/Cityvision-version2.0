import subprocess
sql = """
SELECT occurred_at, payload->>'speed_kmh', payload->>'bbox_ts',
       (payload ? 'evidence') as has_evidence,
       (SELECT count(*) FROM alerts a WHERE a.event_id = e.id) as alert_count
FROM events e
WHERE camera_id='37c7d7fa-12dc-450c-8c4b-ab63ed43a819' AND event_type='speeding'
  AND occurred_at > '2026-07-08 07:04:41+00'
ORDER BY occurred_at DESC;
"""
proc = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql],
    capture_output=True, text=True,
)
print(proc.stdout)
