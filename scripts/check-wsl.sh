#!/usr/bin/env bash
set -euo pipefail

echo "==> Citévision v2 WSL check"

if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "[OK] Running under WSL"
else
  echo "[WARN] Not WSL — some scripts expect bash + Docker in Linux"
fi

command -v docker >/dev/null && echo "[OK] docker" || echo "[MISS] docker"
command -v python3 >/dev/null && echo "[OK] python3" || echo "[MISS] python3"
command -v go >/dev/null && echo "[OK] go" || echo "[MISS] go"
command -v node >/dev/null && echo "[OK] node" || echo "[MISS] node"

echo "Expected v2 ports (no v1 collision): PG 5433, Redis 6380, MQTT 1884, MinIO 9003/9004, AI 8001, Video 9011"
