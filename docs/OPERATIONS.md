# Operations Guide

## Starting Services

```bash
make start          # Infrastructure + AI engine
make ai-dev         # AI engine locally with hot reload
```

## Stopping Services

```bash
make stop
```

## Health Checks

```bash
# AI Engine
curl http://localhost:8000/health

# Video Engine
curl http://localhost:9000/health

# PostgreSQL
docker exec cv-postgres pg_isready -U citevision

# Redis
docker exec cv-redis redis-cli ping

# Mosquitto
mosquitto_sub -h localhost -t '$SYS/broker/version' -C 1
```

## Monitoring MQTT Detections

```bash
mosquitto_sub -h localhost -t 'cv/detections/#' -v
```

## Logs

```bash
docker compose logs -f mosquitto
docker compose logs -f ai-engine
docker compose logs -f postgres
```

## Backup

### PostgreSQL

```bash
docker exec cv-postgres pg_dump -U citevision citevision > backup.sql
```

### MinIO

Use MinIO Console at http://localhost:9002 or `mc mirror`:

```bash
mc alias set local http://localhost:9000 citevision <password>
mc mirror local/recordings ./backups/recordings
```

## Resource Budget

The AI engine automatically adjusts resolution based on registered camera count:

| Active Cameras | Resolution | Target FPS |
|----------------|------------|------------|
| 1 | 1920×1080 | 5 |
| 2–4 | 640×480 | 5 |
| 5–12 | 320×240 | 5 |

Check current budget: `curl http://localhost:8000/budget`

## Registering a Camera

```bash
curl -X POST http://localhost:8000/cameras/register \
  -H 'Content-Type: application/json' \
  -d '{"camera_id": "cam-001"}'
```

## Running Tests

```bash
make test
cd ai-engine && PYTHONPATH=src pytest tests/ -v
```

## Production Checklist

- [ ] Change all default passwords in `.env`
- [ ] Enable Mosquitto authentication and TLS
- [ ] Configure MinIO access policies
- [ ] Set up PostgreSQL backups
- [ ] Deploy video engine as systemd service
- [ ] Configure log aggregation
- [ ] Replace face/ANPR stubs with production models
