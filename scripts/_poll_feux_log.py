#!/usr/bin/env python3
import time
from pathlib import Path
p = Path("/home/gheno/citevision-v2/logs/validate-3rules-tour-feux.log")
for i in range(15):
    t = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    print(f"poll {i} lines={len(t.splitlines())}")
    for ln in t.splitlines()[-4:]:
        print(ln)
    if "Rapport:" in t:
        break
    time.sleep(60)
