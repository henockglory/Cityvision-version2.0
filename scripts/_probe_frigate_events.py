#!/usr/bin/env python3
import json
import urllib.request

for cam in ("", "cv_55694d53", "cv_f691ef55"):
    url = f"http://127.0.0.1:5000/api/events?limit=3"
    if cam:
        url += f"&camera={cam}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            evs = json.loads(r.read())
    except Exception as exc:
        print(cam or "all", "ERR", exc)
        continue
    print("===", cam or "all", "n=", len(evs) if isinstance(evs, list) else evs)
    for e in (evs or [])[:2]:
        if not isinstance(e, dict):
            continue
        data = e.get("data") if isinstance(e.get("data"), dict) else {}
        print(
            e.get("id", "")[:24],
            "cam=", e.get("camera"),
            "start=", e.get("start_time"),
            "label=", e.get("label"),
            "box=", data.get("box"),
        )
