#!/usr/bin/env python3
"""Compare Windows citevision vs any WSL citevision-v2 remnants."""
import os, subprocess
from pathlib import Path

WIN = Path("/mnt/c/Users/gheno/citevision")
WSL = Path.home() / "citevision-v2"

KEY_FILES = [
    "backend/internal/events/service.go",
    "backend/internal/handler/evidence.go",
    "ai-engine/src/citevision_ai/evidence/capture.py",
    "ai-engine/src/citevision_ai/analytics/zone_speed.py",
    "frontend/src/lib/demoFeed.ts",
    "scripts/restart-api-frontend.sh",
    ".env",
]

def mtime(p):
    try:
        return os.path.getmtime(p)
    except OSError:
        return None

print("=== Comparaison sources ===\n")
print(f"Windows: {WIN}")
print(f"  existe: {WIN.is_dir()}")
if WIN.is_dir():
    print(f"  modif récente (racine): {max(mtime(WIN/f) or 0 for f in os.listdir(WIN) if (WIN/f).is_file() or (WIN/f).is_dir())}")

print(f"\nWSL: {WSL}")
print(f"  existe: {WSL.is_dir()}")

win_newer = wsl_newer = equal = missing = 0
for rel in KEY_FILES:
    wp = WIN / rel
    sp = WSL / rel
    wt, st = mtime(wp), mtime(sp)
    if wt is None and st is None:
        missing += 1
        continue
    if wt is None:
        print(f"  WSL only: {rel}")
        wsl_newer += 1
        continue
    if st is None:
        print(f"  WIN only: {rel}")
        win_newer += 1
        continue
    if abs(wt - st) < 2:
        equal += 1
    elif wt > st:
        win_newer += 1
        print(f"  WIN newer: {rel} (+{int(wt-st)}s)")
    else:
        wsl_newer += 1
        print(f"  WSL newer: {rel} (+{int(st-wt)}s)")

print(f"\nRésumé: WIN plus récent={win_newer}, WSL plus récent={wsl_newer}, égaux={equal}, absent={missing}")
if win_newer >= wsl_newer:
    print("=> SOURCE RECOMMANDÉE: C:\\Users\\gheno\\citevision (Windows)")
else:
    print("=> SOURCE RECOMMANDÉE: ~/citevision-v2 (WSL)")

# git log on windows
r = subprocess.run("git -C /mnt/c/Users/gheno/citevision log -1 --format='%ci %s' 2>/dev/null", shell=True, capture_output=True, text=True)
if r.stdout.strip():
    print(f"\nDernier commit Windows: {r.stdout.strip()}")
