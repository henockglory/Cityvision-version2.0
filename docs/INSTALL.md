# Installation Guide

## Prerequisites

- **WSL2** (recommended on Windows) or Linux
- Docker and Docker Compose
- Python 3.12
- CMake 3.16+ and FFmpeg dev libraries (for video engine)

## WSL Setup (Recommended)

```bash
cd /mnt/c/Users/gheno/citevision   # or your clone path
bash scripts/setup-wsl.sh
```

This installs system packages, creates a Python venv, and downloads the YOLO model.

## Manual Setup

### 1. Environment

```bash
cp .env.example .env
# Edit .env with your values
```

### 2. Infrastructure

```bash
docker compose up -d postgres redis mosquitto minio minio-init
```

### 3. AI Engine

```bash
cd ai-engine
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
uvicorn citevision_ai.main:app --port 8000
```

Or via Docker:

```bash
docker compose --profile full up -d ai-engine
```

### 4. YOLO Model

```bash
bash scripts/download-yolo-model.sh
```

### 5. Video Engine

```bash
# Ubuntu/WSL
sudo apt-get install -y build-essential cmake pkg-config \
    libavformat-dev libavcodec-dev libavutil-dev libswscale-dev

make build-video
./video-engine/build/cv-video-engine
```

## Validation

```bash
make validate
# or
bash scripts/run-all-tests.sh
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| MQTT connection refused | Ensure Mosquitto is running: `docker compose ps` |
| YOLO model missing | Run `make download-model` |
| FFmpeg not found | Install dev packages listed above |
| Port 9000 in use | Change `HEALTH_PORT` or `MINIO_API_PORT` in `.env` |
