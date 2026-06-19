# Port Reference — Citévision v2

Ports chosen to avoid collision with v1 (5432, 6379, 1883, 9000, 8000, 9010).

## Infrastructure (Docker Compose)

| Service | Host Port | Container | Protocol |
|---------|-----------|-----------|----------|
| PostgreSQL | **5433** | 5432 | TCP |
| Redis | **6380** | 6379 | TCP |
| Mosquitto MQTT | **1884** | 1883 | TCP |
| Mosquitto WS | **9002** | 9001 | TCP |
| MinIO API | **9003** | 9000 | HTTP |
| MinIO Console | **9004** | 9001 | HTTP |

## Application Services

| Service | Port | Endpoint |
|---------|------|----------|
| AI Engine | **8001** | `GET /health` |
| Rules Engine | **8010** | `GET /health` |
| Video Engine Health | **9011** | `GET /health` |

## MQTT Topics

| Topic | Direction | Description |
|-------|-----------|-------------|
| `cv/detections/{camera_id}` | Publish | Detection payloads |
| `cv/events/{camera_id}` | Publish | Analytics events |
| `cv/alerts/{camera_id}` | Publish | Rule-engine alerts |

## Environment

All ports configurable via `.env`. See `.env.example`.
