#!/usr/bin/env python3
"""Find largest items on C: and D: drives."""
import os, subprocess

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
    return r.stdout.strip()

for drive in ["/mnt/c", "/mnt/d"]:
    if not os.path.exists(drive):
        continue
    print(f"\n{'='*50}")
    print(f"TOP 15 on {drive}")
    print('='*50)
    out = run(f"du -h --max-depth=2 {drive}/Users/gheno 2>/dev/null | sort -hr | head -15")
    print(out or "(scanning...)")

print("\n=== VHDX files ===")
out = run("find /mnt/c/Users/gheno/AppData/Local -name 'ext4.vhdx' 2>/dev/null")
for f in out.splitlines():
    if f:
        sz = run(f"du -sh '{f}' 2>/dev/null")
        print(f"  {sz}")

print("\n=== WSL internal usage ===")
print(run("df -h / 2>/dev/null | tail -1"))
