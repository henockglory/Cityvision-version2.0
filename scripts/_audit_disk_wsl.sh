#!/usr/bin/env bash
set -uo pipefail
cd ~/citevision-v2

echo "=== fstrim.timer ==="
systemctl is-enabled fstrim.timer 2>&1 || true
systemctl is-active fstrim.timer 2>&1 || true
systemctl list-timers --all 2>&1 | grep -i fstrim || echo "no fstrim in timers"
systemctl status fstrim.timer --no-pager 2>&1 | head -20 || true

echo
echo "=== df ==="
df -h / /home 2>&1

echo
echo "=== du citevision-v2 ==="
du -sh /home/gheno/citevision-v2 2>&1
du -sh /home/gheno/citevision-v2/* 2>&1 | sort -hr | head -15

echo
echo "=== VHDX search ==="
find /mnt/c/Users/gheno/AppData/Local -iname '*.vhdx' 2>/dev/null | head -40
find /mnt/c/Users/gheno/AppData/Local/wsl -iname '*.vhdx' 2>/dev/null | head -20
ls -lh /mnt/c/Users/gheno/AppData/Local/Packages/*Ubuntu*/LocalState/*.vhdx 2>/dev/null || true
ls -lh /mnt/c/Users/gheno/AppData/Local/wsl/*/ext4.vhdx 2>/dev/null || true

echo
echo "=== wsl list ==="
wsl.exe -l -v 2>&1 || true

echo
echo "=== sparse check via wsl.exe --manage help ==="
wsl.exe --manage Ubuntu-24.04 --set-sparse 2>&1 | head -5 || true
# Don't actually set sparse - just check if we can query. Document if unknown.
echo "NOTE: no query API for sparse; check if previously set is unknown without Windows registry."
