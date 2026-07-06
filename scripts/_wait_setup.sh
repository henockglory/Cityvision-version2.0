#!/bin/bash
while pgrep -f 'scripts/setup-wsl.sh' >/dev/null 2>&1; do
  echo "$(date +%H:%M:%S) setup en cours..."
  ps aux | grep -E 'pip|ensure-ai|export-yolo|npm' | grep -v grep | tail -2
  sleep 45
done
echo "=== SETUP TERMINE ==="
tail -20 ~/citevision-v2/logs/installer.log 2>/dev/null || true
tail -5 ~/citevision-v2/logs/setup-stdout.log 2>/dev/null || true
