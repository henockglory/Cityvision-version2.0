#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Citévision 2.0 WSL setup"

if command -v apt-get &>/dev/null; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq \
    python3.12 python3.12-venv python3-pip \
    build-essential cmake pkg-config \
    libavformat-dev libavcodec-dev libavutil-dev libswscale-dev \
    curl jq git docker.io docker-compose-plugin 2>/dev/null || true
fi

if [ ! -d "ai-engine/.venv" ]; then
  python3.12 -m venv ai-engine/.venv
fi

# shellcheck disable=SC1091
source ai-engine/.venv/bin/activate
pip install --upgrade pip
pip install -r ai-engine/requirements.txt
pip install -e ai-engine/

mkdir -p ai-engine/models logs

echo "==> Setup complete. Run: make infra-up && make download-model"
