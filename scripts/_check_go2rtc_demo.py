#!/usr/bin/env python3
import json, urllib.request, subprocess

def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())

streams = get("http://127.0.0.1:1984/api/streams")
for name in ["demo-74d51ead-aaea7c30", "demo-74d51ead-1a7dd0c0"]:
    print(f"\n=== {name} ===")
    print(json.dumps(streams.get(name), indent=2))

print("\n=== go2rtc logs ===")
subprocess.run(["docker", "logs", "citevision-v2-go2rtc", "--tail", "25"])

print("\n=== video file in container ===")
subprocess.run([
    "docker", "exec", "citevision-v2-go2rtc", "ls", "-la",
    "/videos/demo/74d51ead-97a7-4e41-a488-503a9b90c466/",
])
