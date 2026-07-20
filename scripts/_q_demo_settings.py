#!/usr/bin/env python3
import subprocess
sql = "SELECT source_mode, active_camera_id, active_go2rtc_src FROM demo_settings LIMIT 1;"
cmd = ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql]
print(subprocess.run(cmd, capture_output=True, text=True).stdout.strip())
