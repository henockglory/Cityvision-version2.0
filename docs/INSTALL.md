# Installation — Citévision v2

## Prérequis

- WSL Ubuntu 24.04 (virtualisation activée)
- Docker Desktop + Compose v2
- Go 1.22+, Node 20+, Python 3.12+, CMake + FFmpeg

```bash
bash scripts/check-wsl.sh
```

## Installation

```bash
cd /home/gheno/citevision-v2
cp .env.example .env
bash scripts/setup-wsl.sh
make infra-up
```

## Démarrage

```bash
docker compose -f infra/docker-compose.yml up -d
cd backend && go run ./cmd/api          # :8081
cd rules-engine && go run ./cmd/rules-engine
cd ai-engine && uvicorn citevision_ai.main:app --port 8001
cd frontend && npm run dev              # :5174
```

Première visite : http://localhost:5174/setup

## Caméra test (.env local)

```
TEST_CAMERA_IP=192.168.1.108
TEST_CAMERA_USER=admin
TEST_CAMERA_PASSWORD=<secret>
```
