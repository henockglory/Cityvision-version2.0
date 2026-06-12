#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PASS=0
FAIL=0

run_check() {
  local name="$1"
  shift
  if "$@"; then
    echo "[PASS] $name"
    PASS=$((PASS + 1))
  else
    echo "[FAIL] $name"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== L1: Repository structure ==="
run_check "Root README exists" test -f README.md
run_check "docker-compose.yml exists" test -f docker-compose.yml
run_check ".env exists" test -f .env
run_check ".env.example exists" test -f .env.example
run_check "Makefile exists" test -f Makefile
run_check "PROMPT-AGENT.md exists" test -f docs/PROMPT-AGENT.md

echo "=== L1: Service skeletons ==="
run_check "backend go.mod" test -f backend/go.mod
run_check "frontend package.json" test -f frontend/package.json
run_check "ai-engine pyproject.toml" test -f ai-engine/pyproject.toml
run_check "video-engine CMakeLists.txt" test -f video-engine/CMakeLists.txt

echo "=== L1: Shared schemas ==="
run_check "detection.json" test -f shared/schemas/detection.json
run_check "event.json" test -f shared/schemas/event.json
run_check "rule.json" test -f shared/schemas/rule.json

echo "=== L1: Infrastructure ==="
run_check "mosquitto.conf" test -f infrastructure/mosquitto.conf
run_check "init-minio.sh" test -f infrastructure/init-minio.sh

echo "=== L1: Documentation ==="
for doc in STATE DECISIONS ARCHITECTURE PORTS INSTALL OPERATIONS README; do
  run_check "docs/${doc}.md" test -f "docs/${doc}.md"
done

echo ""
echo "L1 summary: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
