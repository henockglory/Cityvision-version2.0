# Citévision v2

Multi-service video analytics platform with dedicated AI, rules, and video engines. Runs alongside v1 on non-colliding ports.

## Quick start

```bash
cp .env.example .env
make setup
make infra-up
make test-ai
make ai-dev   # http://localhost:8001/health
```

## Architecture

| Service | Port | Description |
|---------|------|-------------|
| PostgreSQL | 5433 | Primary database |
| Redis | 6380 | Cache |
| MQTT | 1884 | Event bus |
| MinIO | 9003 / 9004 | Object storage API / console |
| AI Engine | 8001 | YOLO ONNX + ByteTrack + events |
| Rules Engine | 8010 | ET/OU/NON rule evaluator |
| Video Engine | 9011 | RTSP ingest + dual pipeline health |

## Components

- `infra/` — Docker Compose (Postgres 17, Redis 7, Mosquitto, MinIO)
- `ai-engine/` — Python FastAPI detection pipeline
- `rules-engine/` — Go MQTT subscriber + declarative rules
- `video-engine/` — C++ FFmpeg RTSP ingest
- `shared/schemas/` — JSON schemas for detection, event, rule
- `shared/rule-catalog/` — Rule templates (catalog only)

## Validation

```bash
make validate   # phases 1–8
```

## Models

Place `yolov8n.onnx` in `ai-engine/models/`. Without the model, YOLO returns **empty detections** (no fake data).

Optional: InsightFace and PaddleOCR — disabled gracefully when packages or model paths are missing.

See [docs/PORTS.md](docs/PORTS.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
