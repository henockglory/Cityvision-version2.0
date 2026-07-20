#!/usr/bin/env python3
import subprocess
sql = """
SELECT r.name, r.is_enabled, rb.camera_id::text, c.name AS cam_name
FROM rules r
LEFT JOIN rule_bindings rb ON rb.rule_id = r.id
LEFT JOIN cameras c ON c.id = rb.camera_id
WHERE r.name ILIKE '%vitesse%' OR r.name ILIKE '%speed%'
ORDER BY r.name;
"""
cmd = ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql]
print(subprocess.run(cmd, capture_output=True, text=True).stdout)
