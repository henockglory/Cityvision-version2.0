#!/usr/bin/env python3
import time
from pathlib import Path

p = Path("/home/gheno/citevision-v2/logs/validate-3rules-tour-10min.log")
for i in range(40):
    t = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    lines = t.splitlines()
    print(f"--- poll {i} lines={len(lines)}")
    for ln in lines[-5:]:
        print(ln)
    if "Rapport:" in t:
        print("DONE")
        break
    time.sleep(60)
