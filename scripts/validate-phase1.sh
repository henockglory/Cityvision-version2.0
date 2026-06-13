#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PASS=0; FAIL=0
check() { if "$@"; then echo "[PASS] $1"; PASS=$((PASS+1)); else echo "[FAIL] $1"; FAIL=$((FAIL+1)); fi; }
echo "=== Phase 1: Repository & infra ==="
check test -f README.md
check test -f Makefile
check test -f .env.example
check test -f infra/docker-compose.yml
check test -f infra/mosquitto.conf
check test -f infra/init-minio.sh
grep -q '5433' infra/docker-compose.yml && check true || check false
grep -q '6380' infra/docker-compose.yml && check true || check false
grep -q '1884' infra/docker-compose.yml && check true || check false
grep -q '9003' infra/docker-compose.yml && check true || check false
echo "Phase 1: PASS=$PASS FAIL=$FAIL"; [ "$FAIL" -eq 0 ]
