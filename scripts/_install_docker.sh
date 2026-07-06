#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list

apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# WSL: start dockerd if not running
if ! docker info >/dev/null 2>&1; then
  nohup dockerd > /tmp/dockerd.log 2>&1 &
  sleep 4
fi

docker compose version
usermod -aG docker gheno 2>/dev/null || true
echo DOCKER_COMPOSE_OK
