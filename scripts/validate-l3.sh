#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
grep -q "postgres:17" "$ROOT/docker-compose.yml"
grep -q "redis:7" "$ROOT/docker-compose.yml"
grep -q "eclipse-mosquitto" "$ROOT/docker-compose.yml"
grep -q "minio/minio" "$ROOT/docker-compose.yml"
echo "[PASS] L3 docker-compose services"
