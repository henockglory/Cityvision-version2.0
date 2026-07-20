#!/usr/bin/env python3
import json, urllib.request, collections
ev = json.loads(urllib.request.urlopen("http://127.0.0.1:5000/api/events?limit=100", timeout=10).read())
print("total events:", len(ev))
print("by camera:", dict(collections.Counter(e.get("camera") for e in ev)))
for e in ev[:3]:
    print(e.get("camera"), e.get("label"), e.get("zones"))
