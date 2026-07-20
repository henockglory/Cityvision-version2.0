#!/usr/bin/env python3
"""Audit stockage: citevision Windows, citevision-v2 WSL, Docker, C:."""
import subprocess, os, json

def run(cmd, timeout=120):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip(), r.stderr.strip(), r.returncode

def du(path, depth=1):
    out, _, _ = run(f"du -h --max-depth={depth} {path} 2>/dev/null | sort -hr")
    return out

print("=" * 60)
print("AUDIT STOCKAGE CitéVision")
print("=" * 60)

# Disk
out, _, _ = run("df -h / /mnt/c 2>/dev/null")
print("\n## Disques")
print(out)

# WSL citevision-v2
print("\n## ~/citevision-v2 (WSL) — top niveaux")
print(du(os.path.expanduser("~/citevision-v2"), 2)[:2000])

# Windows citevision
print("\n## C:\\Users\\gheno\\citevision (Windows) — top niveaux")
print(du("/mnt/c/Users/gheno/citevision", 2)[:1500])

# Docker
print("\n## Docker")
out, _, _ = run("docker system df 2>/dev/null")
print(out or "Docker indisponible")

# Docker volumes via inspect (faster than du per volume)
out, _, rc = run("docker volume ls -q 2>/dev/null")
if rc == 0 and out:
    print("\n## Docker volumes (par nom)")
    vols = out.splitlines()[:30]
    for v in vols:
        if "citevision" in v.lower() or "postgres" in v.lower() or "minio" in v.lower():
            print(f"  {v}")

# VHDX on C:
print("\n## Fichiers .vhdx sur C:")
out, _, _ = run("find /mnt/c/Users/gheno/AppData/Local -name '*.vhdx' 2>/dev/null")
for f in (out or "").splitlines():
    sz, _, _ = run(f"du -sh '{f}' 2>/dev/null")
    if sz:
        print(f"  {sz}")

# Top C: user folders
print("\n## Top dossiers C:\\Users\\gheno")
out, _, _ = run("du -sh /mnt/c/Users/gheno/* 2>/dev/null | sort -hr | head -12")
print(out)

# Clips stats
clips = os.path.expanduser("~/citevision-v2/backend/data/clips")
if os.path.isdir(clips):
    n = len([f for f in os.listdir(clips) if os.path.isfile(os.path.join(clips, f))])
    total, _, _ = run(f"du -sh {clips}")
    print(f"\n## Clips preuves: {total} ({n} fichiers)")

# Duplicate venv
for p in ["~/citevision-v2/ai-engine/.venv", "~/citevision-v2/shared/.venv"]:
    p = os.path.expanduser(p)
    if os.path.isdir(p):
        sz, _, _ = run(f"du -sh {p}")
        print(f"  {p}: {sz}")
