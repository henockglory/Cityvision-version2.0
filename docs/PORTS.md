# Port Reference

## Infrastructure (Docker Compose)

| Service | Port | Protocol | Description |
|---------|------|----------|-------------|
| PostgreSQL | 5432 | TCP | Primary database |
| Redis | 6379 | TCP | Cache / pub-sub |
| Mosquitto MQTT | 1883 | TCP | Detection/event messaging |
| Mosquitto WS | 9001 | TCP | MQTT over WebSocket |
| MinIO API | 9000 | HTTP | S3-compatible object storage |
| MinIO Console | 9002 | HTTP | MinIO web admin (mapped from 9001) |

## Application Services

| Service | Port | Protocol | Endpoint |
|---------|------|----------|----------|
| AI Engine | 8000 | HTTP | `GET /health`, `POST /analyze/frame` |
| Video Engine Health | 9000 | HTTP | `GET /health` (JSON) |

## MQTT Topics

| Topic | Direction | Description |
|-------|-----------|-------------|
| `cv/detections/{camera_id}` | Publish | Detection payloads |
| `cv/events/{camera_id}` | Publish (future) | Standalone event messages |
| `$SYS/broker/version` | Subscribe | Broker health check |

## Port Conflicts

- MinIO API (9000) and Video Engine health (9000) conflict if both run on host. In Docker, MinIO uses 9000; run video engine health on a different host port or inside container network.
- Recommended local dev: set `HEALTH_PORT=9010` for video engine when MinIO is on 9000.

## Environment Variables

See `.env.example` for all configurable ports.
