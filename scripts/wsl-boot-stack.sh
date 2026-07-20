#!/usr/bin/env bash
# Sprint 3 — start native dockerd + critical compose services after WSL boot.
# Called from /etc/wsl.conf [boot] command=... (runs as root) OR manually.
# Docker Desktop is FORBIDDEN.
set -uo pipefail

ROOT="${CITEVISION_ROOT:-/home/gheno/citevision-v2}"
LOG="${CITEVISION_BOOT_LOG:-/tmp/citevision-wsl-boot.log}"
COMPOSE_DIR="$ROOT/infra"
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

exec >>"$LOG" 2>&1
echo "=== citevision wsl-boot $(date -Is) ROOT=$ROOT ==="

if [[ ! -d "$ROOT" ]]; then
  echo "ROOT missing: $ROOT"
  exit 1
fi

# dockerd
if ! docker info >/dev/null 2>&1; then
  echo "starting dockerd..."
  mkdir -p /var/run
  rm -f /var/run/docker.pid
  nohup dockerd >>/tmp/dockerd.log 2>&1 &
  for i in $(seq 1 60); do
    if docker info >/dev/null 2>&1; then
      echo "docker_ok after ${i}s"
      break
    fi
    sleep 1
  done
fi

if ! docker info >/dev/null 2>&1; then
  echo "FAIL: dockerd not ready"
  tail -40 /tmp/dockerd.log || true
  exit 1
fi

cd "$COMPOSE_DIR"
# Critical infra (no AI/frontend — those are host processes)
docker compose up -d postgres redis mosquitto minio mailhog go2rtc 2>&1 || true
# Frigate is profiled — bring up if previously used
docker compose --profile frigate up -d frigate 2>&1 || true

echo "containers:"
docker ps --format '{{.Names}} {{.Status}}' | head -20
echo "=== boot done $(date -Is) ==="
exit 0
