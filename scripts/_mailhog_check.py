#!/usr/bin/env python3
import json, urllib.request
try:
    with urllib.request.urlopen("http://127.0.0.1:8025/api/v2/messages?limit=8", timeout=5) as r:
        msgs = json.loads(r.read()).get("items", [])
    print(f"Mailhog: {len(msgs)} messages récents")
    for m in msgs:
        subj = m.get("Content", {}).get("Headers", {}).get("Subject", ["?"])[0]
        print(f"  {m.get('Created')} | {subj}")
except Exception as e:
    print("Mailhog:", e)
