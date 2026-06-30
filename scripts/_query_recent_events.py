import subprocess

q = """
SELECT event_type, count(1)
FROM events
WHERE ingested_at > NOW() - interval '3 minutes'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20;
"""
subprocess.run(
    ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", q.strip()],
    check=False,
)
