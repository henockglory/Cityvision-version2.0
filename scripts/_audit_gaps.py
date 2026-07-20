#!/usr/bin/env python3
import json
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "docs" / "CHARTER-138-AUDIT.json"
if not p.is_file():
    p = Path.home() / "citevision-v2" / "docs" / "CHARTER-138-AUDIT.json"
d = json.loads(p.read_text(encoding="utf-8"))
print("counts:", d["counts"])
for r in d["rows"]:
    if r["status"] != "done":
        failed = [c for c in r["checks"] if not c["ok"]]
        print(f"{r['ref']} {r['status']} {r['passed']}/{r['total']} | {r.get('notes','')}")
        for c in failed:
            print(f"  FAIL: {c['name']}")
