#!/usr/bin/env python3
import subprocess, json
sql = "SELECT payload FROM events WHERE event_type='speeding' AND payload->'package'->'metadata'->>'capture_source'='frigate_track' ORDER BY ingested_at DESC LIMIT 1;"
r = subprocess.run(["docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-t","-A","-c",sql], capture_output=True, text=True)
print(json.dumps(json.loads(r.stdout.strip()), indent=2)[:4000])
