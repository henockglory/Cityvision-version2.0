#!/usr/bin/env python3
import subprocess

subprocess.run(
    [
        "docker",
        "exec",
        "citevision-v2-postgres",
        "psql",
        "-U",
        "citevision",
        "-d",
        "citevision",
        "-c",
        "SELECT name, metadata->>'demo' AS demo, metadata->>'demo_video_id' AS vid FROM cameras WHERE org_id='e312f375-7442-4089-8022-ed232abc09e8' AND is_active ORDER BY name;",
    ],
    check=False,
)

subprocess.run(
    [
        "docker",
        "exec",
        "citevision-v2-postgres",
        "psql",
        "-U",
        "citevision",
        "-d",
        "citevision",
        "-c",
        "SELECT event_type, payload->>'demo' AS demo, count(1) FROM events GROUP BY 1,2 ORDER BY 1,2;",
    ],
    check=False,
)
