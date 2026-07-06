#!/usr/bin/env python3
"""Compare Windows citevision vs citevision-v2 freshness."""
import os, subprocess
from pathlib import Path

pairs = [
    ("backend/internal/events/service.go",),
    ("backend/internal/handler/evidence.go",),
    ("ai-engine/src/citevision_ai/evidence/capture.py",),
    ("frontend/src/pages/DemoCenter.tsx",),
    ("scripts/restart-api-frontend.sh",),
    (".env",),
]

bases = {
    "citevision": Path("/mnt/c/Users/gheno/citevision"),
    "citevision-v2": Path("/mnt/c/Users/gheno/citevision-v2"),
}

print("=== Comparaison citevision vs citevision-v2 (Windows) ===\n")
cv_newer = 0
cv2_newer = 0
for rel, in pairs:
    rel = rel[0]
    times = {}
    for name, base in bases.items():
        p = base / rel
        if p.exists():
            times[name] = p.stat().st_mtime
        else:
            times[name] = None
    t1, t2 = times.get("citevision"), times.get("citevision-v2")
    if t1 and t2:
        winner = "citevision" if t1 >= t2 else "citevision-v2"
        if winner == "citevision":
            cv_newer += 1
        else:
            cv2_newer += 1
        from datetime import datetime
        print(f"{rel}")
        print(f"  citevision:    {datetime.fromtimestamp(t1)}")
        print(f"  citevision-v2: {datetime.fromtimestamp(t2)}")
        print(f"  -> {winner} plus recent\n")
    else:
        print(f"{rel}: manquant dans {'citevision-v2' if not t2 else 'citevision'}\n")

print(f"Score: citevision={cv_newer} | citevision-v2={cv2_newer}")

# git log if available
for name, base in bases.items():
    if (base / ".git").exists():
        r = subprocess.run(["git", "-C", str(base), "log", "-1", "--format=%ci %s"],
                           capture_output=True, text=True)
        print(f"git {name}: {r.stdout.strip() or r.stderr.strip()}")
