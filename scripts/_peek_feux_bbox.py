#!/usr/bin/env python3
import json, subprocess
sql = """
SELECT payload->'bbox', payload->'bbox_source',
       payload->'package'->'metadata'->'bbox',
       payload->'package'->'metadata'->>'bbox_source',
       payload->'package'->'metadata'->'ia_bbox'
FROM events WHERE event_type='red_light_violation'
ORDER BY ingested_at DESC LIMIT 1;
"""
r = subprocess.run(["docker","exec","citevision-v2-postgres","psql","-U","citevision","-d","citevision","-t","-A","-F|","-c",sql], capture_output=True, text=True)
print(r.stdout)
