#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for name in ("CHARTER-138-AUDIT.json", "ROADMAP-138-STATUS.json"):
    p = ROOT / "docs" / name
    if not p.is_file():
        print(f"MISSING {p}")
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    print(f"\n=== {name} counts={d.get('counts')} ===")
    for r in d.get("rows", []):
        if r.get("status") != "done":
            print(f"  {r['ref']:8} {r['status']:8} {r.get('title','')[:50]} | {r.get('notes','')}")
