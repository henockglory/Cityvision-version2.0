#!/usr/bin/env bash
set -euo pipefail
# Start native dockerd in WSL (no Docker Desktop, no systemd)
if docker info >/dev/null 2>&1; then
  echo "dockerd already running"
  docker ps --format '{{.Names}}' | head -15
  exit 0
fi
echo "starting dockerd..."
sudo rm -f /tmp/dockerd.log
sudo touch /tmp/dockerd.log
sudo chmod 666 /tmp/dockerd.log
sudo nohup dockerd >>/tmp/dockerd.log 2>&1 &
echo "dockerd pid=$!"
for i in $(seq 1 40); do
  if docker info >/dev/null 2>&1; then
    echo "docker_ok after ${i}s"
    docker ps -a --format '{{.Names}} {{.Status}}' | head -20
    exit 0
  fi
  echo "wait $i"
  sleep 2
done
echo "=== dockerd.log ==="
tail -40 /tmp/dockerd.log || true
exit 1
