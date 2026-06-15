#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/env-utils.sh
source "$ROOT/scripts/lib/env-utils.sh"

echo "=== Citévision v2 WSL setup ==="
echo ""

if command -v apt-get &>/dev/null; then
  echo "[INFO] Installing system packages..."
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3.12 python3.12-venv python3-pip \
    build-essential cmake pkg-config \
    curl jq git rsync ffmpeg \
    ca-certificates gnupg lsb-release 2>/dev/null || true

  if ! command -v docker &>/dev/null; then
    echo "[INFO] Installing Docker Engine..."
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null || true
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  fi

  if ! command -v go &>/dev/null; then
    echo "[INFO] Installing Go 1.22..."
    curl -fsSL https://go.dev/dl/go1.22.5.linux-amd64.tar.gz | sudo tar -C /usr/local -xz
    grep -q '/usr/local/go/bin' ~/.bashrc 2>/dev/null || echo 'export PATH=$PATH:/usr/local/go/bin' >>~/.bashrc
    export PATH="$PATH:/usr/local/go/bin"
  fi

  if ! command -v node &>/dev/null || [[ "$(node -v 2>/dev/null || echo v0)" < "v20" ]]; then
    echo "[INFO] Installing Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nodejs
  fi

  sudo usermod -aG docker "$USER" 2>/dev/null || true
  sudo service docker start 2>/dev/null || true
fi

ensure_env_file "$ROOT" >/dev/null

if [[ ! -d ai-engine/.venv ]]; then
  python3.12 -m venv ai-engine/.venv
fi
# shellcheck disable=SC1091
source ai-engine/.venv/bin/activate
pip install --upgrade pip -q
( cd ai-engine && pip install -r requirements.txt -q )

if [[ ! -d frontend/node_modules ]]; then
  echo "[INFO] npm install frontend..."
  (cd frontend && npm install --silent)
fi

mkdir -p ai-engine/models logs

echo ""
echo "[OK] Setup complete"
echo ""
echo "If docker group was just added, run: newgrp docker"
echo "Then: bash scripts/start-linux.sh"
