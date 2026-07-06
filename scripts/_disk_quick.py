#!/usr/bin/env python3
import subprocess, os

def run(cmd, timeout=120):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()

print("=== VHDX sur C: ===")
for root in [
    "/mnt/c/Users/gheno/AppData/Local/wsl",
    "/mnt/c/Users/gheno/AppData/Local/Docker",
    "/mnt/c/Users/gheno/AppData/Local/Packages",
]:
    out = run(f"find {root} -name 'ext4.vhdx' 2>/dev/null")
    for f in out.splitlines():
        if f:
            print(f"  {run(f'du -sh \"{f}\" 2>/dev/null')}")

print("\n=== AppData\\Local (top 10) ===")
print(run("du -h --max-depth=1 /mnt/c/Users/gheno/AppData/Local 2>/dev/null | sort -hr | head -10"))

print("\n=== D: drive (top 10) ===")
if os.path.exists("/mnt/d"):
    print(run("du -h --max-depth=2 /mnt/d 2>/dev/null | sort -hr | head -10"))
else:
    print("  D: non monté dans WSL")

print("\n=== WSL usage interne ===")
print(run("df -h / | tail -1"))
print(run("du -sh ~/citevision-v2/backend/data/clips 2>/dev/null"))
print(run("docker exec citevision-v2-minio du -sh /data/citevision-evidence 2>/dev/null"))
