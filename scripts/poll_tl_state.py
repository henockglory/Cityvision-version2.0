#!/usr/bin/env python3
import json, time, urllib.request
url = "http://127.0.0.1:8001/cameras/726ff8a1-8442-4bdb-96ad-ec40a2fbb424/spatial"
states = set()
for _ in range(20):
    d = json.loads(urllib.request.urlopen(url, timeout=5).read())
    s = d.get("traffic_light_state")
    states.add(s)
    print(s)
    time.sleep(2)
print("unique:", sorted(states))
